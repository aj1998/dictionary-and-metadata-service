# JainKosh Parser — Schema Updates

> Concrete edits to the existing schema docs (`02_data_model_postgres.md`,
> `03_data_model_mongo.md`, `04_data_model_graph.md`) needed to support
> the new JainKosh parser as defined in
> [`parsing_rules.md`](./parsing_rules.md) and
> [`parser_spec.md`](./parser_spec.md).
>
> **Two schemas already exist as code (Postgres model 02 and Graph
> model 04 are implemented; see commit log: `486e7ce` and `5393915`).
> Mongo (03) is not yet implemented. So:**
>
> - **Postgres**: ALTER existing tables via a new Alembic migration.
> - **Mongo**: update the design doc; no DB to alter yet.
> - **Neo4j**: ADD properties / relationship type via an idempotent
>   `ensure_constraints()` update.
>
> No design decision is broken by this change — these are *additive*
> fields and one new edge type.

---

## 1. Why these changes

The old design assumed:

1. One keyword has **at most one** `keyword_definitions` doc with
   exactly one optional intro paragraph per section. We now know
   keywords have **multiple definitions per section** (e.g., आत्मा's
   SiddhantKosh has ~5 definitions; PuranKosh has multiple
   `<p id="N">` numbered definitions).
2. Topic natural keys had a `jainkosh:` source prefix. We're dropping
   that — natural keys are now `<keyword>:<slug>:<slug>:…`. The
   source is recorded separately in `topics.source`.
3. Topics were flat. They are actually **hierarchical** with a numeric
   `topic_path` (`1.1.3`, `II.3.3`). Cross-page references like
   `देखें X - 1.2` must resolve to a specific topic by `(keyword,
   topic_path)` pair, so we add `topic_path` and `parent_topic_id`
   columns.
4. Topics had no `is_leaf` flag; we want to distinguish leaf topics
   (queryable bodies) from container topics (heading-only).
5. The graph used `HAS_TOPIC` as the only Keyword→Topic edge. We
   need `PART_OF` for Topic→Topic parent edges as well (already
   defined in 04, but not yet wired for jainkosh).

---

## 2. Postgres changes (doc `02_data_model_postgres.md`)

### 2.1 `topics` table — add 4 columns

```sql
ALTER TABLE topics
  ADD COLUMN topic_path        TEXT,
  ADD COLUMN parent_topic_id   UUID REFERENCES topics(id) ON DELETE SET NULL,
  ADD COLUMN is_leaf           BOOLEAN NOT NULL DEFAULT true,
  ADD COLUMN is_synthetic      BOOLEAN NOT NULL DEFAULT false;

CREATE INDEX idx_topics_parent_topic     ON topics(parent_topic_id);
CREATE INDEX idx_topics_keyword_path     ON topics(parent_keyword_id, topic_path);
```

Notes:
- `topic_path` is **opaque text**, e.g. `"1.1.3"` or `"II.3.3"`. It is
  unique only within a `(parent_keyword_id, topic_path)` tuple, so we
  add a *non-unique* index — multiple keywords can each have their
  own `1.1` topic.
- `parent_topic_id` is the in-tree parent; `parent_keyword_id` (already
  present) remains the keyword whose page emitted the topic. For a
  top-level topic (`topic_path = "1"`), `parent_topic_id IS NULL` and
  `parent_keyword_id` points at the keyword.
- `is_leaf`: true for topics that have no children. Toggled on writes;
  not derived live (queries filter on it).
- `is_synthetic`: true if the parser had to invent the parent because
  it wasn't declared in the HTML. Useful for admin review.

### 2.2 `topics.natural_key` format change

Old format: `jainkosh:आत्मा:बहिरात्मादि-3-भेद`

New format: `आत्मा:बहिरात्मादि-3-भेद` (no source prefix; source lives
in `topics.source`).

Migration plan:
- This is a **format change for new rows only**. Existing rows (none
  yet — Mongo isn't live; Neo4j is empty for jainkosh) are not in
  production data, so no rewrite is needed.
- Update `02_data_model_postgres.md` example block accordingly.
- Add a migration assertion: `topics.natural_key` MUST NOT start with
  `'jainkosh:'`. Implemented as a `CHECK` constraint to catch parser
  regressions early:

```sql
ALTER TABLE topics
  ADD CONSTRAINT topics_natural_key_no_source_prefix
  CHECK (natural_key NOT LIKE 'jainkosh:%' AND natural_key NOT LIKE 'nj:%');
```

### 2.3 `keyword_definitions` reference

The `keywords.definition_doc_ids JSONB` column is already an array of
Mongo ids — **no change**. Multiple definitions per section are stored
*inside* the single `keyword_definitions` Mongo doc (see §3).

### 2.4 New migration

```
migrations/0010_topics_hierarchy.py
  - ALTER topics ADD topic_path / parent_topic_id / is_leaf / is_synthetic
  - CREATE indexes idx_topics_parent_topic, idx_topics_keyword_path
  - ADD CHECK topics_natural_key_no_source_prefix
  - (no data migration; tables empty)
```

Numbering: existing migration sequence (per `02_data_model_postgres.md`
§"Migration plan") ends at `0009_query_logs.py`. New migration is
`0010_topics_hierarchy.py`.

### 2.5 Idempotent upsert function update

The example `upsert_keyword(...)` in `02_data_model_postgres.md` stays.
Add `upsert_topic(...)`:

```python
async def upsert_topic(session, *, natural_key: str, topic_path: str | None,
                       display_text: list[dict],
                       parent_topic_natural_key: str | None,
                       parent_keyword_natural_key: str,
                       source: str = "jainkosh",
                       is_leaf: bool, is_synthetic: bool = False) -> uuid.UUID:
    parent_topic_id = await fetch_topic_id_by_nk(session, parent_topic_natural_key) \
                      if parent_topic_natural_key else None
    parent_keyword_id = await fetch_keyword_id_by_nk(session, parent_keyword_natural_key)
    stmt = pg_insert(Topic).values(
        natural_key=natural_key,
        topic_path=topic_path,
        display_text=display_text,
        source=source,
        parent_topic_id=parent_topic_id,
        parent_keyword_id=parent_keyword_id,
        is_leaf=is_leaf,
        is_synthetic=is_synthetic,
    ).on_conflict_do_update(
        index_elements=[Topic.natural_key],
        set_={
            "topic_path": topic_path,
            "display_text": display_text,
            "parent_topic_id": parent_topic_id,
            "parent_keyword_id": parent_keyword_id,
            "is_leaf": is_leaf,
            "is_synthetic": is_synthetic,
            "updated_at": func.now(),
        },
    ).returning(Topic.id)
    return (await session.execute(stmt)).scalar_one()
```

When upserting a tree, the orchestrator must walk it **parents-first**
so `parent_topic_id` resolves correctly.

### 2.6 Optional: `keyword_definition_count` view

For admin UI dashboards:

```sql
CREATE VIEW v_keyword_topic_counts AS
SELECT
  k.id AS keyword_id,
  k.natural_key AS keyword_nk,
  count(t.*)             AS total_topics,
  count(t.*) FILTER (WHERE t.is_leaf) AS leaf_topics,
  count(t.*) FILTER (WHERE t.is_synthetic) AS synthetic_topics
FROM keywords k
LEFT JOIN topics t ON t.parent_keyword_id = k.id
GROUP BY k.id, k.natural_key;
```

Optional, not part of Definition of Done.

---

## 3. Mongo changes (doc `03_data_model_mongo.md`)

Mongo has not been implemented yet, so this is a **doc-only update**.
Apply these edits to `03_data_model_mongo.md` directly.

### 3.1 `keyword_definitions` collection — schema rewrite

OLD (in `03_data_model_mongo.md`):

```json
"page_sections": [
  {
    "section_index": 0,
    "section_kind": "siddhantkosh",
    "heading": [...],
    "subsections": [
      {
        "subsection_index": 1,
        "heading": [...],
        "is_topic_seed": true,
        "topic_natural_key": "jainkosh:आत्मा:बहिरात्मादि-3-भेद",
        "blocks": [...]
      }
    ]
  }
]
```

NEW:

```json
{
  "_id": "...",
  "natural_key": "आत्मा",
  "keyword_id": "<uuid>",
  "source_url": "https://www.jainkosh.org/wiki/आत्मा",
  "page_sections": [
    {
      "section_index": 0,
      "section_kind": "siddhantkosh",
      "h2_text": "सिद्धांतकोष से",

      "definitions": [
        {
          "definition_index": 1,
          "blocks": [
            {"kind":"reference","references":[{"text":"धवला पुस्तक 13/5,5,50/282/9"}]},
            {"kind":"sanskrit_text","text_devanagari":"…","hindi_translation":"…",
             "references":[{"text":"धवला पुस्तक 13/5,5,50/282/9"}]}
          ]
        },
        {"definition_index": 2, "blocks":[ ... ]},
        {"definition_index": 3, "blocks":[ ... ]},
        {"definition_index": 4, "blocks":[ ... ]},
        {"definition_index": 5, "blocks":[ ... ]}
      ],

      "subsection_tree": [
        {
          "natural_key": "आत्मा:आत्मा-के-बहिरात्मादि-3-भेद",
          "topic_path": "2",
          "heading": [{"lang":"hin","script":"Deva","text":"आत्मा के बहिरात्मादि 3 भेद"}],
          "is_leaf": true,
          "is_synthetic": false,
          "children": []
        }
      ],

      "index_relations": [
        {"label_text":"…","target_keyword":"वह वह नाम","target_topic_path":null,
         "is_self":false,"target_exists":false,"source_topic_path":null}
      ],

      "extra_blocks": []
    },
    {
      "section_index": 1,
      "section_kind": "puraankosh",
      "definitions": [
        {"definition_index": 1, "blocks":[{"kind":"hindi_text","text_devanagari":"(1) अतति इति …","references":[...]}]},
        {"definition_index": 2, "blocks":[{"kind":"hindi_text","text_devanagari":"(2) सौधर्मेंद्र द्वारा …","references":[...]}]}
      ],
      "subsection_tree": [],
      "index_relations": [],
      "extra_blocks": []
    }
  ],
  "redirect_aliases": [],
  "ingestion_run_id": "uuid",
  "parser_version": "jainkosh.rules/1.0.0",
  "created_at": ISODate(...),
  "updated_at": ISODate(...)
}
```

Differences from the old design:

| Field             | Change                                                                |
|-------------------|------------------------------------------------------------------------|
| `definitions`     | **NEW**. Array of `{definition_index, blocks[]}`. Replaces single `intro` paragraph. |
| `subsection_tree` | **NEW**. Recursive tree of `{natural_key, topic_path, heading, is_leaf, is_synthetic, children[]}`. Replaces flat `subsections[]`. **Bodies live in `topic_extracts`**, not here. |
| `index_relations` | **NEW**. From the leading `<ol>`/`<ul>` index. |
| `extra_blocks`    | **NEW**. Section-level tables (parsing_rules §6.5). |
| `parser_version`  | **NEW**. e.g. `"jainkosh.rules/1.0.0"`. |

The `subsection_tree` here is a **summary** (no blocks, no
references). The actual body of each topic lives in `topic_extracts`
keyed by `natural_key`. This avoids duplication and keeps
`keyword_definitions` small.

### 3.2 `topic_extracts` collection — add fields

OLD:

```json
{
  "natural_key": "jainkosh:आत्मा:बहिरात्मादि-3-भेद",
  "heading": [...],
  "blocks": [...],
  "extracted_keyword_natural_keys": [...],
  ...
}
```

NEW (additive):

```json
{
  "natural_key": "आत्मा:आत्मा-के-बहिरात्मादि-3-भेद",
  "topic_path": "2",
  "parent_natural_key": null,
  "parent_keyword_natural_key": "आत्मा",
  "is_leaf": true,
  "is_synthetic": false,

  "heading": [{"lang":"hin","script":"Deva","text":"आत्मा के बहिरात्मादि 3 भेद"}],
  "blocks": [
    {"kind":"reference","references":[{"text":"मोक्षपाहुड़ / मूल या टीका गाथा 4"}]},
    {"kind":"prakrit_text","text_devanagari":"…","hindi_translation":"…","references":[…]},
    {"kind":"see_also","target_keyword":"वह वह नाम","target_topic_path":null,"is_self":false,"target_url":"/w/index.php?title=…&action=edit&redlink=1","target_exists":false}
  ],
  "extracted_keyword_natural_keys": ["आत्मा","बहिरात्मा","अंतरात्मा","परमात्मा"],
  "source": "jainkosh",
  "source_url": "https://www.jainkosh.org/wiki/आत्मा#2",
  "ingestion_run_id": "uuid",
  "parser_version": "jainkosh.rules/1.0.0",
  "created_at": ISODate(...),
  "updated_at": ISODate(...)
}
```

New fields: `topic_path`, `parent_natural_key`, `parent_keyword_natural_key`,
`is_leaf`, `is_synthetic`, `parser_version`.

Indexes — add:

```
{ "parent_keyword_natural_key": 1, "topic_path": 1 }   // for `देखें X - 1.2` resolution
{ "parent_natural_key": 1 }                             // for tree walks
```

### 3.3 Block kind names — stable list

The block kinds that can appear inside `definitions[].blocks[]` and
`topic_extracts.blocks[]`:

```
"reference"            // standalone GRef block (rare; usually attached to source/hindi)
"sanskrit_text"
"sanskrit_gatha"
"prakrit_text"
"prakrit_gatha"
"hindi_text"
"hindi_gatha"
"see_also"
"table"
```

Drop `extracted_keyword_natural_keys` from the v1 parser output (it's
empty until an admin/AI step adds it). Keep the field in the schema
for future use.

### 3.4 `raw_html_snapshots` collection — unchanged

No change.

---

## 4. Neo4j changes (doc `04_data_model_graph.md`)

### 4.1 `Topic` node — add 2 properties

```cypher
// On every sync_topic call:
MERGE (t:Topic {natural_key: $nk})
SET t.pg_id = $pg_id,
    t.display_text_hi = $display,
    t.source = $source,
    t.parent_keyword_natural_key = $parent_keyword,
    t.topic_path = $topic_path,                 // NEW
    t.is_leaf = $is_leaf,                       // NEW
    t.updated_at = datetime()
ON CREATE SET t.created_at = datetime()
```

`topic_path` enables fast Cypher resolution for cross-references
(`MATCH (t:Topic {parent_keyword_natural_key: $kw, topic_path: $p})`).

Add an index for the resolution lookup:

```cypher
CREATE INDEX topic_kw_path IF NOT EXISTS
  FOR (n:Topic) ON (n.parent_keyword_natural_key, n.topic_path);
```

### 4.2 `PART_OF` edge — already defined; needs wiring

`04_data_model_graph.md` already lists `PART_OF` as a Topic→Topic
edge (parent direction). Update its description:

```
| PART_OF | directed | Topic → Topic | weight, source | Child topic is a sub-topic of its parent (e.g. 'जीव-के-भेद' PART_OF 'जीव'). Created automatically from topic_path hierarchy. |
```

The jainkosh sync emits `PART_OF` from every non-root topic to its
parent topic.

### 4.3 `RELATED_TO` for `देखें` cross-references

Already defined in 04. Clarify in the doc:

- Source for index-level `<ul>` `देखें`: depends on the source location
  per parsing_rules §4.2.
- Source for inline `देखें`: the topic that contains the body block.
- Target: the resolved Topic (if `target_topic_path` is set) or the
  Keyword (if only `target_keyword` is set).

### 4.4 Edge for self-link `mw-selflink-fragment`

This produces a `RELATED_TO` edge whose source and target are
**both Topics under the same Keyword**. No new edge type.

### 4.5 Update `parser_configs/_meta/edge_types.yaml`

`edge_types.yaml` currently exists. Verify it lists:

```yaml
- IS_A
- PART_OF
- RELATED_TO
- ALIAS_OF
- MENTIONS_KEYWORD
- HAS_TOPIC
- MENTIONS_TOPIC
- IN_SHASTRA
```

If `PART_OF` is missing, add it. The graph layer's `schema_check.py`
rejects writes with unlisted edge types.

### 4.6 No new constraints

The existing `topic_natural_key UNIQUE` already keys topics
uniquely. `topic_path` is non-unique by design (every keyword has its
own `1`, `2`, etc.).

---

## 5. Cross-doc edits (what to actually change)

### 5.1 `docs/design/02_data_model_postgres.md`

- In `### topics` table block: insert the four new columns and the
  CHECK constraint (per §2.1, §2.2).
- In `### topics` after the CREATE INDEX lines: add the two new indexes.
- In `## Migration plan` list: add `0010_topics_hierarchy.py`.
- In `## Sample upsert pattern`: add `upsert_topic` example (per §2.5).
- Update the example `topics.natural_key` value to the new format
  (drop `jainkosh:` prefix).

### 5.2 `docs/design/03_data_model_mongo.md`

- Replace the `### 6. keyword_definitions` block with the new shape
  (per §3.1).
- Replace the `### 7. topic_extracts` block with the new shape
  (per §3.2).
- Add the indexes from §3.2.

### 5.3 `docs/design/04_data_model_graph.md`

- In the `## Node labels` table for `Topic`: add `topic_path` and
  `is_leaf` to "Stored properties".
- In the `## Edge types` table for `PART_OF`: amend description per §4.2.
- In `## Constraints & indexes` Cypher block: add the
  `topic_kw_path` composite index.
- In `## Sync from Postgres > Sync algorithm (incremental) > sync_topic`:
  add `topic_path` and `is_leaf` to the SET clause.
- Add a "PART_OF emission" subsection right after the `MENTIONS_KEYWORD`
  loop:

```python
if pg_topic_row.parent_topic_natural_key:
    await neo4j.run("""
        MATCH (child:Topic {natural_key: $c}), (parent:Topic {natural_key: $p})
        MERGE (child)-[r:PART_OF]->(parent)
        SET r.weight = coalesce(r.weight, 1.0), r.source = 'jainkosh'
    """, c=pg_topic_row.natural_key, p=pg_topic_row.parent_topic_natural_key)
```

### 5.4 `docs/design/08_ingestion_jainkosh.md`

- In its parser config YAML example: add the new fields for the
  rule-driven parser (or, simpler: replace the in-doc YAML with a
  pointer to `parser_configs/jainkosh.yaml`).
- Replace the inline "Source structure" rules with:

```
> See [`jainkosh/parsing_rules.md`](./jainkosh/parsing_rules.md)
> for the canonical parsing rules. The parser implementation is
> specified in [`jainkosh/parser_spec.md`](./jainkosh/parser_spec.md).
```

- Replace the inline `KeywordExtract` Pydantic example with a link to
  `jainkosh/parser_spec.md` §4.

### 5.5 `docs/design/jainkosh/structure.md`

- Replace contents with a one-line pointer to `parsing_rules.md`
  (the original `structure.md` is now superseded).

---

## 6. Migration order (when implementing)

When the parser is wired into the orchestrator (a later stage), apply
in this order:

1. **Postgres**: run `0010_topics_hierarchy.py` Alembic migration.
2. **Mongo**: when `dictionary-service` first starts, its
   `ensure_indexes()` step creates the new indexes on
   `keyword_definitions` and `topic_extracts`.
3. **Neo4j**: `ensure_constraints()` runs the new
   `CREATE INDEX topic_kw_path` (idempotent).
4. **Parser run**: now safe to ingest jainkosh keywords.

Because no jainkosh data is in production yet, this is a
**zero-downtime cold start**.

---

## 7. Definition of Done (schema updates)

- [ ] `02_data_model_postgres.md` updated with the four new `topics`
      columns, the CHECK constraint, the two new indexes, and the
      migration entry.
- [ ] `0010_topics_hierarchy.py` migration added under `migrations/`.
- [ ] `tests/db/postgres/test_topics_hierarchy.py` exercises a tree
      insert and verifies `parent_topic_id` chain + `is_leaf` on every
      ancestor and leaf.
- [ ] `03_data_model_mongo.md` updated with new
      `keyword_definitions` and `topic_extracts` shapes + indexes.
- [ ] `04_data_model_graph.md` updated with `topic_path`, `is_leaf`,
      composite index, and the `PART_OF` sync snippet.
- [ ] `parser_configs/_meta/edge_types.yaml` includes `PART_OF`.
- [ ] `08_ingestion_jainkosh.md` no longer contains the inline
      "Source structure" rules; instead links to
      `jainkosh/parsing_rules.md` and `jainkosh/parser_spec.md`.
- [ ] `jainkosh/structure.md` is replaced or removed.

This is a doc-and-migrations effort. No service code changes are
needed *except* the orchestrator's `upsert_topic` call site (added at
the same time as it wires the parser into the pipeline — out of scope
for parser-only stage).
