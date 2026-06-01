# JainKosh Ingestion

This document describes the ingestion pipeline that takes a parsed `WouldWriteEnvelope` from the JainKosh parser and writes it idempotently to Postgres, Mongo, and Neo4j.

The entry point is `apply_approved_keyword_payload` in `workers/ingestion/jainkosh/apply.py`. Everything below describes what the implementation does today.

---

## Architecture overview

```
Parser (HTML → WouldWriteEnvelope JSON)
         │
         ▼
apply_approved_keyword_payload(envelope, pg_session, mongo_db, neo4j_driver)
         │
         ├── Postgres (single transaction) ─── keywords, topics, keyword_aliases
         │         commit
         ├── Mongo ────────────────────────── keyword_definitions, topic_extracts, raw_html_snapshots
         └── Neo4j ────────────────────────── Keyword, Topic nodes; stub nodes; edges
```

Postgres commits before Mongo/Neo4j writes. If a downstream write fails, the queue row stays in `approved` and retrying `apply_approved_keyword_payload` with the same envelope heals it — every write is `ON CONFLICT DO NOTHING` or `MERGE`.

All Devanagari strings are NFC-normalized at the apply boundary (`unicodedata.normalize('NFC', s)`), even though the parser already does this.

---

## Postgres schema

### `topics` table (`packages/jain_kb_common/jain_kb_common/db/postgres/topics.py`)

The `Topic` model has these columns relevant to JainKosh ingestion:

| Column | Type | Notes |
|---|---|---|
| `topic_path` | `TEXT` | Dot-separated path, e.g. `द्रव्य.चेतन-द्रव्य` |
| `parent_topic_id` | `UUID → topics.id` | `ON DELETE SET NULL`; `NULL` for root topics |
| `is_leaf` | `BOOLEAN NOT NULL DEFAULT true` | False if this topic has children |
| `is_synthetic` | `BOOLEAN NOT NULL DEFAULT false` | True for parser-generated synthetic topics |

Indexes:
- `idx_topics_parent_topic` on `parent_topic_id`
- `idx_topics_keyword_path` on `(parent_keyword_id, topic_path)`

Constraint: `natural_key NOT LIKE 'jainkosh:%' AND natural_key NOT LIKE 'nj:%'`

### `upsert_keyword_alias` (`jain_kb_common/db/postgres/upserts.py`)

```python
async def upsert_keyword_alias(
    session, *, keyword_id: uuid.UUID, alias: str, source: str
) -> None
```

Conflict target: `(keyword_id, alias_text)` — backed by migration `0013_keyword_alias_unique.py`.

---

## Mongo schema (`jain_kb_common/db/mongo/schemas.py`)

### `keyword_definitions` collection

```
KeywordDefinition
  natural_key       str
  keyword_id        str | None        # injected at apply time from Postgres
  source_url        str
  page_sections     list[KeywordPageSection]
  redirect_aliases  list[str]
  ingestion_run_id  str | None
  parser_version    str

KeywordPageSection
  section_index     int
  section_kind      str
  h2_text           str | None
  definitions       list[DefinitionItem]
  subsection_tree   list[SubsectionTreeNode]
  index_relations   list[IndexRelationItem]
  extra_blocks      list[dict]

DefinitionItem
  definition_index  int
  blocks            list[dict]        # opaque; matches parser Block shape

SubsectionTreeNode
  natural_key       str
  topic_path        str | None
  heading           list[LangText]
  is_leaf           bool
  is_synthetic      bool
  children          list[SubsectionTreeNode]

IndexRelationItem
  label_text        str | None
  target_keyword    str | None
  target_topic_path str | None
  is_self           bool
  target_exists     bool
  source_topic_path str | None
```

### `topic_extracts` collection

`TopicExtract` has these additional fields beyond the base model:

```
topic_path                  str | None
parent_natural_key          str | None
parent_keyword_natural_key  str
is_leaf                     bool = True
is_synthetic                bool = False
parser_version              str
```

### Mongo indexes (`jain_kb_common/db/mongo/indexes.py`)

```python
await db[TOPIC_EXTRACTS].create_index(
    [("parent_keyword_natural_key", 1), ("topic_path", 1)],
    name="topic_kw_path",
)
await db[TOPIC_EXTRACTS].create_index("parent_natural_key", name="parent_natural_key")
```

---

## Neo4j schema

### Real-sync functions (`jain_kb_common/db/neo4j/upserts.py`)

All real-sync functions unconditionally set `is_stub = false, stub_source = null` so that a previously stubbed node is upgraded in a single MERGE round-trip.

| Function | Node/Edge written |
|---|---|
| `sync_keyword` | `Keyword` node |
| `sync_topic` | `Topic` node |
| `sync_has_topic_edge` | `(Keyword)-[:HAS_TOPIC]->(Topic)` |
| `sync_part_of_edge` | `(Topic)-[:PART_OF]->(Topic)` |
| `sync_related_to_edge` | `(src)-[:RELATED_TO]->(tgt)` (label-parameterised) |
| `sync_shastra` | `Shastra` node |
| `sync_teeka` | `Teeka` node + `IN_SHASTRA` edge |
| `sync_publication` | `Publication` node + `IN_TEEKA` edge |
| `sync_kalash` | `Kalash` node + `IN_TEEKA` / `HAS_KALASH` edges |
| `sync_gatha` | `Gatha` node + `IN_SHASTRA` edge |
| `sync_gatha_teeka` | `GathaTeeka` node + `HAS_GATHA_TEEKA` edge |
| `sync_gatha_teeka_bhaavarth` | `GathaTeekaBhaavarth` node + `HAS_BHAAVARTH` edge |
| `sync_kalash_bhaavarth` | `KalashBhaavarth` node + `HAS_BHAAVARTH` edge |

All edge helpers (`sync_has_topic_edge`, `sync_part_of_edge`, `sync_related_to_edge`) use `MERGE` on both endpoints with a stub-coalesce safety net, so a missing endpoint never silently drops the edge.

### Constraints and indexes (`jain_kb_common/db/neo4j/constraints.py`)

Uniqueness constraints on `natural_key` exist for all node labels. Per-label `is_stub` indexes exist for: `Keyword`, `Topic`, `Gatha`, `GathaTeeka`, `GathaTeekaBhaavarth`, `Kalash`, `KalashBhaavarth`, `Page`. The `topic_kw_path` composite index covers `(parent_keyword_natural_key, topic_path)` on `Topic`.

Audit query for un-filled stubs:
```cypher
MATCH (n {is_stub: true}) RETURN labels(n)[0] AS label, count(*) ORDER BY count(*) DESC
```

---

## Stub node pattern (`jain_kb_common/db/neo4j/stubs.py`)

When `apply_approved_keyword_payload` encounters cross-page edge targets (topics or keywords not in the current envelope) or lazy reference nodes (Gatha, GathaTeeka, …), it creates **stub nodes** so edges always land. A later real ingestion upgrades the stub by setting `is_stub = false`.

### Stub triggers

| Situation | Action |
|---|---|
| Edge target has `is_stub_seed: true` (cross-page Topic or Keyword resolved at envelope-build time) | Write stub |
| Node has `lazy: true` (reference-emitted lazy node — Gatha, GathaTeeka, etc.) | Write stub |
| Edge endpoint missing despite the above (belt-and-braces) | Edge helpers MERGE the endpoint with stub coalesce |
| Edge has `target_exists: false` (JainKosh redlink) | Skip edge entirely; no stub |

### `sync_stub_node`

```python
async def sync_stub_node(
    driver, *, label: str, natural_key: str, props: dict,
    stub_source: str = "jainkosh_ingestion", database: str = "jainkb",
) -> None
```

Cypher pattern — `coalesce` ensures real nodes are never clobbered:

```cypher
MERGE (n:Topic {natural_key: $nk})
SET n.updated_at = datetime(),
    n.created_at = coalesce(n.created_at, datetime()),
    n.is_stub = coalesce(n.is_stub, true),
    n.stub_source = coalesce(n.stub_source, $stub_source),
    n.display_text_hi = coalesce(n.display_text_hi, $display_text_hi),
    ...
```

The label is validated against a per-label allow-list before interpolation into the Cypher string to prevent injection. Unknown labels raise `ValueError`.

Per-label stub props:

| Label | Stub props written |
|---|---|
| `Keyword` | `display_text` |
| `Topic` | `display_text_hi`, `topic_path`, `parent_keyword_natural_key` |
| `Gatha` | `shastra_natural_key`, `gatha_number` |
| `GathaTeeka` | `shastra_natural_key`, `teeka_natural_key`, `gatha_number` |
| `GathaTeekaBhaavarth` | `shastra_natural_key`, `teeka_natural_key`, `publisher_id`, `gatha_number` |
| `Kalash` | `teeka_natural_key`, `kalash_number` |
| `KalashBhaavarth` | `shastra_natural_key`, `teeka_natural_key`, `publisher_id`, `kalash_number` |
| `Page` | `shastra_natural_key`, `teeka_natural_key`, `publisher_id`, `page_number` |

### `sync_reference_edge`

Handles `MENTIONS_TOPIC` and `CONTAINS_DEFINITION` edge types. MERGEs both endpoints with stub coalesce before MERGing the edge. Both `edge_type` and labels are validated against allow-lists.

---

## The apply function (`workers/ingestion/jainkosh/apply.py`)

### Signature

```python
async def apply_approved_keyword_payload(
    *,
    envelope: dict,
    pg_session: AsyncSession,
    mongo_db,
    neo4j_driver,
    ingestion_run_id: uuid.UUID | None = None,
    neo4j_database: str = "jainkb",
) -> None
```

### Execution order

**1. NFC-normalize** the entire envelope dict recursively.

**2. Postgres (single transaction)**

1. `upsert_keyword(natural_key, display_text, source_url, definition_doc_ids=[stable_id(nk)])` → `keyword_id`
2. Topologically sort `would_write.postgres.topics` (parents before children, via DFS on `parent_topic_natural_key`). For each topic:
   - Resolve `parent_keyword_id` (uses in-memory map for the current keyword; queries Postgres for cross-keyword parents).
   - Resolve `parent_topic_id` from the in-memory `topic_id_map` built so far (parent is guaranteed to have been inserted already due to topo sort).
   - Call `upsert_topic(...)` with `topic_path`, `is_leaf`, `is_synthetic`.
3. For each alias in `would_write.postgres.keyword_aliases`: `upsert_keyword_alias(keyword_id, alias, source)`.
4. `await pg_session.commit()`

**3. Mongo (after Postgres commit)**

1. `upsert_keyword_definition(natural_key, doc)` — injects `keyword_id` and `ingestion_run_id` before writing.
2. For each topic extract: `upsert_topic_extract(natural_key, doc)` — injects `ingestion_run_id` and `parent_keyword_natural_key` if missing.
3. If raw HTML snapshots are present: `upsert_raw_html_snapshot(natural_key, doc)`.

**4. Neo4j**

1. `sync_keyword(natural_key, pg_id, display_text, source_url)` — sets `is_stub = false`.
2. For each topic (same topo order as Postgres): `sync_topic(...)` — sets `is_stub = false`.
3. For each node in `neo4j.nodes` with `is_stub_seed: true` or `lazy: true`: `sync_stub_node(label, natural_key, props)`.
4. For each edge in `neo4j.edges`:
   - `HAS_TOPIC` → `sync_has_topic_edge`
   - `PART_OF` → `sync_part_of_edge`
   - `RELATED_TO` (only when `target_exists` is not false) → `sync_related_to_edge`
   - `MENTIONS_TOPIC` / `CONTAINS_DEFINITION` → `sync_reference_edge`

---

## Envelope conventions

Stub seeds are derived at envelope-build time in `envelope.py`, not at apply time:

- **Same-keyword self-reference Topics**: emit a stub-seed node with `"key": heading_based_natural_key`. The actual key is known at parse time from the current envelope's topic tree.
- **Cross-page Topic refs** (`target_keyword != current keyword`): emit a stub-seed node with `"resolve_key": "{parent_keyword}:{topic_path_with_colons}"` (e.g. `"स्वभाว:2"`). The `key` field is absent; the ingestion layer resolves the actual key at apply time (see §Cross-page topic stub resolution below).
- **Cross-page Keyword refs**: emits `{"label": "Keyword", "key": kw, "is_stub_seed": True, "props": {"display_text": kw}}`.
- **Lazy nodes** (Gatha, GathaTeeka, etc.): tagged `lazy: true` with derived props from `_derive_props`.
- **`_dedupe`** collapses `(label, key or resolve_key)` duplicates; if a node appears as both real and stub-seed, the real copy wins.
- **Redlinks** (`target_exists: false`): edges are dropped at envelope time; no stub is emitted.

---

## Cross-page topic stub resolution

Cross-page Topic stubs carry `resolve_key` instead of `key` (e.g. `"स्वभाव:2"`) because the heading text of the target topic is only available in that keyword's own HTML page.

**At apply time** (`apply_approved_keyword_payload`):

After the Postgres commit, `_resolve_topic_stubs` runs:

1. Finds all stub nodes with `resolve_key` and `is_stub_seed: true`.
2. For each, queries Postgres: `SELECT topics.natural_key FROM topics JOIN keywords ON topics.parent_keyword_id = keywords.id WHERE keywords.natural_key = $parent_kw AND topics.topic_path = $path`.
3. If found → replace `resolve_key` with the actual heading-based `key` (e.g. `"स्वभाव:स्वभाव-व-शक्ति-निर्देश"`). The RELATED_TO edge target is updated to match.
4. If not found (target keyword not yet ingested) → use `resolve_key` itself as the fallback `key`. A placeholder stub is written to Neo4j (same as before this feature).

**Why a second ingestion pass may be needed:**

When two keywords cross-reference each other (A → B and B → A), a single sequential pass resolves only the direction where the target was processed earlier. Use `--resolve-pass` in `ingest_goldens_apply.py` to run a second application of all envelopes; by then all keywords are in Postgres and all stubs resolve correctly. The second pass is fully idempotent (MERGE / ON CONFLICT DO NOTHING).

**No infinite loops:** `_resolve_topic_stubs` only issues `SELECT` queries to Postgres — it never triggers recursive ingestion calls. There is no risk of cycles or loops.

---

## Tests

| Test file | Coverage |
|---|---|
| `workers/ingestion/jainkosh/tests/unit/test_goldens.py` | Parser golden output for आत्मा, द्रव्य, पर्याय, वस्तु, गुण, स्वभाव |
| `workers/ingestion/jainkosh/tests/unit/test_parsing_features.py` | Parser unit tests for specific HTML features |

Integration tests for `apply_approved_keyword_payload` live under `tests/ingestion/` (outside the worker directory) and cover:
- Full-envelope idempotency (apply twice → zero net DB changes)
- Parent-first topic tree linkage (`parent_topic_id` populated)
- Alias deduplication
- Stub creation and upgrade for cross-page references
- Lazy node writes (GathaTeeka etc. with `is_stub = true`)
- Redlink suppression

Test fixtures: HTML files in `workers/ingestion/jainkosh/tests/fixtures/`. Goldens: JSON files in `workers/ingestion/jainkosh/tests/golden/`.
