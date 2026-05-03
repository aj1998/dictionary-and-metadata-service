# Phase 1 — Schema deltas + apply-on-approve layer

**Goal**: take a parser `WouldWriteEnvelope` JSON and write it idempotently
to Postgres + Mongo + Neo4j. No HTTP, no Celery, no fetching. Pure functions
+ DB writes only.

When this phase is done, an integration test can: load a sample
envelope (e.g., produced by the parser from
`samples/sample_html_jainkosh_pages/आत्मा.html`) and call
`apply_approved_keyword_payload(envelope)` twice, observing zero net DB
changes after the second call.

---

## 1.1 Postgres migration `0010_topics_hierarchy`

File: `migrations/versions/0010_topics_hierarchy.py`

Add to `topics`:

```sql
ALTER TABLE topics
  ADD COLUMN topic_path        TEXT,
  ADD COLUMN parent_topic_id   UUID REFERENCES topics(id) ON DELETE SET NULL,
  ADD COLUMN is_leaf           BOOLEAN NOT NULL DEFAULT true,
  ADD COLUMN is_synthetic      BOOLEAN NOT NULL DEFAULT false;

CREATE INDEX idx_topics_parent_topic ON topics(parent_topic_id);
CREATE INDEX idx_topics_keyword_path ON topics(parent_keyword_id, topic_path);

ALTER TABLE topics
  ADD CONSTRAINT topics_natural_key_no_source_prefix
  CHECK (natural_key NOT LIKE 'jainkosh:%' AND natural_key NOT LIKE 'nj:%');
```

`downgrade()` drops them in reverse.

### SQLAlchemy model update

In `packages/jain_kb_common/jain_kb_common/db/postgres/topics.py`, add:

```python
topic_path: Mapped[str | None] = mapped_column(Text, nullable=True)
parent_topic_id: Mapped[uuid.UUID | None] = mapped_column(
    UUID(as_uuid=True),
    ForeignKey("topics.id", ondelete="SET NULL"),
    nullable=True,
)
is_leaf: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
is_synthetic: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
```

Update `__table_args__` with the two new indexes + the CHECK constraint.

### `upsert_topic` signature update

`packages/jain_kb_common/jain_kb_common/db/postgres/upserts.py`. Add the
four new kwargs (`topic_path`, `parent_topic_id`, `is_leaf`,
`is_synthetic`) — all optional with safe defaults. Mirror them in the
`set_={…}` dict on conflict.

---

## 1.2 New helper: `upsert_keyword_alias`

In `jain_kb_common/db/postgres/upserts.py`:

```python
async def upsert_keyword_alias(
    session, *, keyword_id: uuid.UUID, alias: str, source: str
) -> None:
    stmt = pg_insert(KeywordAlias).values(
        keyword_id=keyword_id, alias=alias, source=source,
    ).on_conflict_do_nothing(index_elements=[KeywordAlias.keyword_id, KeywordAlias.alias])
    await session.execute(stmt)
```

Confirm the unique index on `(keyword_id, alias)` exists in
`0005_keywords_aliases.py`. If not, add a new tiny migration
`0011_keyword_alias_unique.py` for it.

---

## 1.3 Mongo schema doc updates

Edit `docs/design/03_data_model_mongo.md` per `schema_updates.md` §3 —
this is doc-only, but the Pydantic models in
`packages/jain_kb_common/jain_kb_common/db/mongo/schemas.py` must match.

### Pydantic model edits

`KeywordDefinition` (collection `keyword_definitions`):

```python
class DefinitionItem(BaseModel):
    definition_index: int
    blocks: list[dict]  # opaque; matches parser's Block.dict()

class SubsectionTreeNode(BaseModel):
    natural_key: str
    topic_path: str | None
    heading: list[LangText]
    is_leaf: bool
    is_synthetic: bool
    children: list["SubsectionTreeNode"] = []

class IndexRelationItem(BaseModel):
    label_text: str | None = None
    target_keyword: str | None = None
    target_topic_path: str | None = None
    is_self: bool = False
    target_exists: bool = True
    source_topic_path: str | None = None

class PageSection(BaseModel):
    section_index: int
    section_kind: str
    h2_text: str | None = None
    definitions: list[DefinitionItem] = []
    subsection_tree: list[SubsectionTreeNode] = []
    index_relations: list[IndexRelationItem] = []
    extra_blocks: list[dict] = []

class KeywordDefinition(BaseModel):
    natural_key: str
    keyword_id: str | None = None
    source_url: str
    page_sections: list[PageSection]
    redirect_aliases: list[str] = []
    ingestion_run_id: str | None = None
    parser_version: str
    # created_at / updated_at managed by upsert helper
```

`TopicExtract` — additive fields:

```python
topic_path: str | None
parent_natural_key: str | None
parent_keyword_natural_key: str
is_leaf: bool = True
is_synthetic: bool = False
parser_version: str
```

### Index updates

`jain_kb_common/db/mongo/indexes.py` — add to `ensure_indexes(db)`:

```python
await db[TOPIC_EXTRACTS].create_index(
    [("parent_keyword_natural_key", 1), ("topic_path", 1)],
    name="topic_kw_path",
)
await db[TOPIC_EXTRACTS].create_index("parent_natural_key", name="parent_natural_key")
```

---

## 1.4 Neo4j updates

`jain_kb_common/db/neo4j/upserts.py::sync_topic`: the `SET` clause must
also write `topic_path` and `is_leaf`:

```cypher
MERGE (t:Topic {natural_key: $nk})
SET t.pg_id = $pg_id,
    t.display_text_hi = $display,
    t.source = $source,
    t.parent_keyword_natural_key = $parent_keyword,
    t.topic_path = $topic_path,
    t.is_leaf = $is_leaf,
    t.updated_at = datetime(),
    t.created_at = coalesce(t.created_at, datetime())
```

Add `sync_part_of_edge(driver, child_nk, parent_nk)`:

```cypher
MATCH (child:Topic {natural_key: $c}), (parent:Topic {natural_key: $p})
MERGE (child)-[r:PART_OF]->(parent)
SET r.weight = coalesce(r.weight, 1.0), r.source = 'jainkosh'
```

`constraints.py::ensure_constraints` — add (idempotent):

```cypher
CREATE INDEX topic_kw_path IF NOT EXISTS
  FOR (n:Topic) ON (n.parent_keyword_natural_key, n.topic_path)
```

Verify `parser_configs/_meta/edge_types.yaml` includes `PART_OF`. If not,
add it.

Add `sync_related_to_edge(driver, source_nk, target_nk, weight=1.0)` for
`देखें` cross-references (covers index-level and inline `देखें`,
self-links). Skip emission entirely when `target_exists=false` (parser
already suppresses these in the envelope per fix-spec-002).

---

## 1.5 The apply function

New file: `workers/ingestion/jainkosh/apply.py`.

```python
async def apply_approved_keyword_payload(
    *,
    envelope: dict,                # WouldWriteEnvelope.dict()
    pg_session: AsyncSession,
    mongo_db,
    neo4j_driver,
    ingestion_run_id: uuid.UUID | None = None,
) -> None:
    """
    Idempotently apply one keyword's would_write payload to all three stores.
    Called from:
      - Phase 3 admin approve action
      - Phase 3 idempotency test (called twice in a row)
    Must be safe to retry: every write uses ON CONFLICT / MERGE.
    """
```

Algorithm:

1. **Postgres, in one transaction**:
   1. `upsert_keyword(natural_key, display_text, source_url, definition_doc_ids=[stable_id(nk)])` → `keyword_id`.
   2. Walk `would_write.postgres.topics` sorted by `topic_path` ascending
      (root first; treat `None` as root). For each topic row:
      - Resolve `parent_keyword_id` from `parent_keyword_natural_key`.
      - Resolve `parent_topic_id` from `parent_topic_natural_key` (lookup
        `topics.natural_key` — relies on parents already inserted; the
        sort guarantees this).
      - Call `upsert_topic(...)` with `topic_path`, `is_leaf`,
        `is_synthetic` from the row.
   3. For each alias in `would_write.postgres.keyword_aliases`, call
      `upsert_keyword_alias(keyword_id=keyword_id, alias=…, source=…)`.

2. **Mongo**, after the Postgres tx commits:
   1. `upsert_keyword_definition(natural_key=…, doc=…)` with the
      envelope's `would_write.mongo.keyword_definitions` doc, injecting
      `keyword_id` and `ingestion_run_id`.
   2. For each item in `would_write.mongo.topic_extracts`:
      `upsert_topic_extract(natural_key=…, doc=…)`.
   3. If the envelope carries a raw HTML pointer (Phase 2 will populate
      it), call `upsert_raw_html_snapshot(...)`. Phase 1 may pass `None`
      and skip.

3. **Neo4j**:
   1. `sync_keyword(...)`.
   2. For every topic (parents-first again): `sync_topic(...)`.
   3. For every non-root topic with a `parent_topic_natural_key`:
      `sync_part_of_edge(child, parent)`.
   4. For every entry in `would_write.neo4j.edges` of type `RELATED_TO`:
      `sync_related_to_edge(source_nk, target_nk)`. (`PART_OF` edges
      may also appear in the envelope — apply them if present and skip
      step 3 when so. Pick one source-of-truth per orchestrator: prefer
      the envelope's edge list.)

4. NFC-normalize every Devanagari string at the boundary. The parser
   already does this; re-assert with `unicodedata.normalize('NFC', s)`
   on each string in the doc before writing.

Constraints / invariants:

- Calling `apply_approved_keyword_payload` twice with the same envelope
  produces zero net DB changes after the second call (verified by the
  Phase 3 e2e test, but Phase 1 should already satisfy it).
- The Postgres tx and Mongo/Neo4j writes are *not* in one global
  transaction — Mongo and Neo4j writes happen after Postgres commits.
  If a downstream write fails, the queue row stays in `approved` and
  a retry call to the same function will heal (idempotent). Surface
  errors; do not swallow.

---

## 1.6 Tests

`tests/ingestion/test_apply.py` (new):

1. `test_apply_idempotent_full_envelope` — load a parser-produced envelope
   for `आत्मा`, call `apply_approved_keyword_payload` twice, assert:
   - row counts in `keywords`, `topics`, `keyword_aliases` match between
     run 1 and run 2;
   - `keyword_definitions` and `topic_extracts` doc counts match;
   - Neo4j node counts match;
   - `topics.updated_at` *may* advance, but no new rows.
2. `test_apply_topics_parents_first` — assert every topic with a
   `parent_topic_natural_key` ends up with `parent_topic_id` populated
   (tree fully linked).
3. `test_apply_alias_dedup` — call apply twice with the same envelope;
   `keyword_aliases` row count for the keyword does not grow.

Use the existing `samples/sample_html_jainkosh_pages/आत्मा.html` and
parse it once at fixture-time via `parse_keyword_html` →
`build_envelope` to get a deterministic fixture.

---

## 1.7 Definition of Done — Phase 1

- [ ] Migration `0010_topics_hierarchy.py` runs on a fresh DB and on a
      DB at `0009`.
- [ ] `Topic` SQLAlchemy model has the four new columns and matches the
      migration.
- [ ] `upsert_topic` accepts the new kwargs and the existing tests still
      pass.
- [ ] `upsert_keyword_alias` exists and is unique-constraint backed.
- [ ] Pydantic Mongo models match the new shape from `schema_updates.md` §3.
- [ ] `ensure_indexes` creates the two new indexes on `topic_extracts`.
- [ ] `sync_topic` writes `topic_path` and `is_leaf`; `sync_part_of_edge`
      and `sync_related_to_edge` exist; `topic_kw_path` index created.
- [ ] `edge_types.yaml` includes `PART_OF`.
- [ ] `apply_approved_keyword_payload` exists and is callable from a
      Python REPL given a session/db/driver triple and an envelope dict.
- [ ] All three tests in `test_apply.py` pass; calling the apply
      function twice with the same envelope produces zero net diff.
- [ ] Existing test suite (~129 parser tests + DB tests) still green.
