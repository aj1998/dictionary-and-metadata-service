# Schema Sync Spec — New Entity Types & Reference Edge Support

> This document consolidates all schema changes required to support the new
> entity types surfaced by the JainKosh parser (reference edge creation spec,
> `jainkosh/reference_edge_creation_spec.md`) and the related node hierarchy
> (`Teeka`, `Publication`, `Kalash`, `GathaTeeka`, etc.).
>
> **Prerequisite**: `jainkosh/schema_updates.md` covers the `topics` table
> hierarchy columns (`topic_path`, `parent_topic_id`, `is_leaf`, `is_synthetic`)
> and migration `0010_topics_hierarchy.py`. Those changes are assumed complete
> (or co-applied with this spec). This spec adds everything beyond that.
>
> **Migration sequence after this spec**: `0010` (topics hierarchy) → `0011`
> (publications) → `0012` (kalashas).

---

## 1. Scope

### In scope

- **Postgres**: two new tables (`publications`, `kalashas`).
- **MongoDB**: six new collections + corrections to `keyword_definitions`
  reference objects + minor corrections to `topic_extracts`.
- **Neo4j**: seven new node labels, two new structural edge types, one new
  content edge type, expansion of `MENTIONS_TOPIC` source labels.
- **`edge_types.yaml`**: add `IN_TEEKA`, `IN_PUBLICATION`, `CONTAINS_DEFINITION`;
  update `MENTIONS_TOPIC` and `IN_SHASTRA`.
- **`constraints.py`**: uniqueness constraints + indexes for all new labels.
- **`upserts.py`**: `sync_teeka`, `sync_publication`, `sync_kalash` (Postgres-
  backed); lazy-MERGE helpers for pure graph nodes.
- **`envelope.py`**: emit node objects for Postgres-backed labels; emit lazy
  node stubs for pure graph nodes.
- **Doc update tasks** listed at the end.

### Out of scope

- API layer changes (routes / response shapes).
- Admin UI changes.
- Golden regeneration (separate follow-up after code changes).
- Embedding / vector search.

---

## 2. Why these changes

The reference edge emission code (`reference_edges.py`, implemented) writes
edges whose `from.label` values include `GathaTeeka`, `GathaTeekaBhaavarth`,
`Kalash`, `KalashBhaavarth`, and `Page`. These node labels do not yet exist in
the schema. The parser golden files (`द्रव्य.json`) already emit such edges,
so the sync layer will create orphaned edges unless the nodes are created first
or lazily via `MERGE`.

Additionally:

- `Teeka` has a Postgres table but no Neo4j node, breaking traversal paths
  like `GathaTeeka → Teeka → Shastra`.
- `Publication` is a new concept (specific printed edition of a teeka) that
  has no representation anywhere yet.
- `Kalash` (special verse by teekakar) needs Postgres + Mongo backing because
  we store its text.
- The `keyword_definitions` Mongo collection stores `references` objects with
  only `{text, raw_html}` but the parser now produces fully resolved references
  with `resolved_fields`, `shastra_name`, `teeka_name`, and `inline_reference`;
  the schema must reflect the actual output.

---

## 3. Node taxonomy (complete picture)

| Label | Backed by | Key format | Parent edge → Parent label |
|-------|-----------|------------|----------------------------|
| `Shastra` | Postgres `shastras` | `<shastra_nk>` | — (root) |
| `Teeka` | Postgres `teekas` | `<teeka_nk>` | `IN_SHASTRA → Shastra` |
| `Publication` | Postgres `publications` (NEW) | `<teeka_nk>:<publisher_id>` | `IN_TEEKA → Teeka` |
| `Gatha` | Postgres `gathas` | `<shastra>:गाथा:<n>` | `IN_SHASTRA → Shastra` |
| `GathaTeeka` | Graph-only (lazy MERGE) | `<shastra>:<teeka>:गाथा:टीका:<n>` | `IN_TEEKA → Teeka` |
| `GathaTeekaBhaavarth` | Graph-only (lazy MERGE) | `<shastra>:<teeka>:<pub_id>:गाथा:टीका:भावार्थ:<n>` | `IN_PUBLICATION → Publication` |
| `Kalash` | Postgres `kalashas` (NEW) | `<teeka_nk>:कलश:<n>` | `IN_TEEKA → Teeka` |
| `KalashBhaavarth` | Graph-only (lazy MERGE) | `<shastra>:<teeka>:<pub_id>:कलश:भावार्थ:<n>` | `IN_PUBLICATION → Publication` |
| `Page` | Graph-only (lazy MERGE) | `<shastra>:<teeka>:<pub_id>:पृष्ठ:<n>` | `IN_PUBLICATION → Publication` |

> "Graph-only (lazy MERGE)" means the node is created via `MERGE` during edge
> sync — no Postgres row, no Mongo doc. Properties are derived entirely from
> the key segments.

---

## 4. Postgres changes

### 4.1 New table: `publications`

A Publication is a specific printed edition of a Teeka, identified by the
teeka and the publisher.

```sql
CREATE TABLE publications (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  natural_key   TEXT NOT NULL UNIQUE,          -- '<teeka_nk>:<publisher_id>'
  teeka_id      UUID NOT NULL REFERENCES teekas(id) ON DELETE CASCADE,
  publisher_id  TEXT NOT NULL,                 -- from publishers.json
  publisher     JSONB,                         -- [{lang, script, text}] display name
  public_url    TEXT,
  publisher_url TEXT,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_publications_teeka ON publications(teeka_id);
```

**Natural key format**: `<teeka.natural_key>:<publisher_id>`.
Example: `pravachansaar:amritchandra:anantkirti-granthmala`.

**`publisher_id`** must match an entry in
`parser_configs/_manual_configs/publishers.json`. The value
`"publisher_to_be_added"` is allowed in the table (parser emits it when
publisher is unknown); admin can update it once the entry is added.

**SQLAlchemy model** — add to `packages/jain_kb_common/jain_kb_common/db/postgres/`:

```
publications.py     # Publication model (analogous to teekas.py)
```

### 4.2 New table: `kalashas`

A Kalash is a special summary/commentary verse (गाथा-equivalent) composed by
the teekakar, embedded in the teeka. It has its own text content stored in
Mongo.

```sql
CREATE TABLE kalashas (
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  natural_key           TEXT NOT NULL UNIQUE,      -- '<teeka_nk>:कलश:<n>'
  teeka_id              UUID NOT NULL REFERENCES teekas(id) ON DELETE CASCADE,
  kalash_number         TEXT NOT NULL,             -- '3' or '3-4' for ranges
  sanskrit_doc_id       TEXT,                      -- mongo kalash_sanskrit._id
  hindi_doc_id          TEXT,                      -- mongo kalash_hindi._id
  bhaavarth_doc_ids     JSONB NOT NULL DEFAULT '[]'::jsonb,  -- [mongo kalash_bhaavarth_hindi._id, ...] one per publication
  created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_kalashas_teeka ON kalashas(teeka_id);
```

**Natural key format**: `<teeka.natural_key>:कलश:<n>`.
Example: `pravachansaar:amritchandra:कलश:3`.

Note: the natural_key for the Neo4j `Kalash` node uses the format
`<shastra>:<teeka>:कलश:<n>` (segments from the Reference), which aligns with
the teeka's natural_key structure.

**SQLAlchemy model** — add `kalashas.py` alongside `gathas.py`.

### 4.3 `topics` table (from `schema_updates.md`)

Already specified in `jainkosh/schema_updates.md §2.1–2.2`. Repeated here for
completeness:

```sql
ALTER TABLE topics
  ADD COLUMN topic_path        TEXT,
  ADD COLUMN parent_topic_id   UUID REFERENCES topics(id) ON DELETE SET NULL,
  ADD COLUMN is_leaf           BOOLEAN NOT NULL DEFAULT true,
  ADD COLUMN is_synthetic      BOOLEAN NOT NULL DEFAULT false;

ALTER TABLE topics
  ADD CONSTRAINT topics_natural_key_no_source_prefix
  CHECK (natural_key NOT LIKE 'jainkosh:%' AND natural_key NOT LIKE 'nj:%');

CREATE INDEX idx_topics_parent_topic  ON topics(parent_topic_id);
CREATE INDEX idx_topics_keyword_path  ON topics(parent_keyword_id, topic_path);
```

### 4.4 Migration plan

```
migrations/versions/
├── 0010_topics_hierarchy.py     # topics columns + check constraint (per schema_updates.md)
├── 0011_publications.py         # publications table
└── 0012_kalashas.py             # kalashas table
```

**`0011_publications.py`**:
- `CREATE TABLE publications`
- `CREATE INDEX idx_publications_teeka`

**`0012_kalashas.py`**:
- `CREATE TABLE kalashas`
- `CREATE INDEX idx_kalashas_teeka`

---

## 5. MongoDB changes

### 5.1 Correction: `keyword_definitions` — `references` objects

**Current schema** (in `03_data_model_mongo.md` and in the actual parser output
the parser now generates full `Reference` objects):

```json
"references": [
  {"text": "धवला पुस्तक 13/5,5,50/282/9",
   "raw_html": "<span class=\"GRef\">धवला...</span>"}
]
```

**Corrected schema** (matches `Reference` Pydantic model in `models.py`):

```json
"references": [
  {
    "text": "धवला पुस्तक 13/5,5,50/282/9",
    "raw_html": "<span class=\"GRef\">धवला...</span>",
    "resolved_fields": [
      {"field": "पुस्तक", "value": 13},
      {"field": "गाथा", "value": 199}
    ],
    "shastra_name": "धवला",
    "teeka_name": "",
    "inline_reference": false
  }
]
```

New fields per reference object:

| Field | Type | Notes |
|-------|------|-------|
| `resolved_fields` | `list[{field: str, value: int\|str}]` | Parsed numeric/range fields from reference text |
| `shastra_name` | `str \| null` | Canonical shastra name from registry; `null` if unresolved |
| `teeka_name` | `str` | Teeka segment; empty string when absent |
| `inline_reference` | `bool` | True if this reference appears inline (not as standalone GRef) |

**Where this applies**: Every `references[]` array inside:
- `keyword_definitions.page_sections[].definitions[].blocks[].references`
- `keyword_definitions.page_sections[].subsection_tree[*].blocks[].references`
  (bodies live in `topic_extracts.blocks[].references`)
- `topic_extracts.blocks[].references`

**No index changes** — `references` is not queried directly.

### 5.2 Correction: `keyword_definitions` — `subsection_tree`

Remove `blocks` from the inline `subsection_tree` summary (bodies are in
`topic_extracts`). The tree node shape should be:

```json
{
  "natural_key": "द्रव्य:द्रव्य-के-भेद-व-लक्षण",
  "topic_path": "1",
  "heading": [{"lang": "hin", "script": "Deva", "text": "द्रव्य के भेद व लक्षण"}],
  "is_leaf": false,
  "is_synthetic": false,
  "children": [...]
}
```

No `blocks` field — blocks live exclusively in `topic_extracts`.

### 5.3 New collection: `gatha_teeka_sanskrit`

Sanskrit text of a teeka's commentary on a specific gatha (the source-language
original that the teekakar quotes).

```json
{
  "_id": "ObjectId(...)",
  "natural_key": "pravachansaar:amritchandra:गाथा:टीका:115:sanskrit",
  "gatha_teeka_natural_key": "pravachansaar:amritchandra:गाथा:टीका:115",
  "teeka_natural_key": "pravachansaar:amritchandra",
  "gatha_number": "115",
  "text": [{"lang": "san", "script": "Deva", "text": "..."}],
  "ingestion_run_id": "uuid",
  "created_at": ISODate(...),
  "updated_at": ISODate(...)
}
```

**Indexes**: `{natural_key: 1}` UNIQUE; `{gatha_teeka_natural_key: 1}`.

### 5.4 New collection: `gatha_teeka_hindi`

Hindi anvayartha/commentary of a teeka on a specific gatha (teeka prose, not
the bhaavarth of a publication).

```json
{
  "natural_key": "pravachansaar:amritchandra:गाथा:टीका:115:hindi",
  "gatha_teeka_natural_key": "pravachansaar:amritchandra:गाथा:टीका:115",
  "teeka_natural_key": "pravachansaar:amritchandra",
  "gatha_number": "115",
  "text": [{"lang": "hin", "script": "Deva", "text": "..."}],
  "ingestion_run_id": "uuid",
  "created_at": ISODate(...),
  "updated_at": ISODate(...)
}
```

**Indexes**: `{natural_key: 1}` UNIQUE; `{gatha_teeka_natural_key: 1}`.

### 5.5 New collection: `gatha_teeka_bhaavarth_hindi`

Hindi bhaavarth (meaning expansion) for a GathaTeeka as published in a specific
Publication.

```json
{
  "natural_key": "pravachansaar:amritchandra:anantkirti-granthmala:गाथा:टीका:भावार्थ:115",
  "gatha_teeka_bhaavarth_natural_key": "pravachansaar:amritchandra:anantkirti-granthmala:गाथा:टीका:भावार्थ:115",
  "publication_natural_key": "pravachansaar:amritchandra:anantkirti-granthmala",
  "gatha_teeka_natural_key": "pravachansaar:amritchandra:गाथा:टीका:115",
  "publisher_id": "anantkirti-granthmala",
  "gatha_number": "115",
  "text": [{"lang": "hin", "script": "Deva", "text": "..."}],
  "ingestion_run_id": "uuid",
  "created_at": ISODate(...),
  "updated_at": ISODate(...)
}
```

**Indexes**: `{natural_key: 1}` UNIQUE; `{publication_natural_key: 1}`;
`{gatha_teeka_natural_key: 1}`.

### 5.6 New collection: `kalash_sanskrit`

Sanskrit text of a kalash verse.

```json
{
  "natural_key": "pravachansaar:amritchandra:कलश:3:sanskrit",
  "kalash_natural_key": "pravachansaar:amritchandra:कलश:3",
  "teeka_natural_key": "pravachansaar:amritchandra",
  "kalash_number": "3",
  "text": [{"lang": "san", "script": "Deva", "text": "..."}],
  "ingestion_run_id": "uuid",
  "created_at": ISODate(...),
  "updated_at": ISODate(...)
}
```

**Indexes**: `{natural_key: 1}` UNIQUE; `{kalash_natural_key: 1}`.

### 5.7 New collection: `kalash_hindi`

Hindi commentary of a kalash.

```json
{
  "natural_key": "pravachansaar:amritchandra:कलश:3:hindi",
  "kalash_natural_key": "pravachansaar:amritchandra:कलश:3",
  "teeka_natural_key": "pravachansaar:amritchandra",
  "kalash_number": "3",
  "text": [{"lang": "hin", "script": "Deva", "text": "..."}],
  "ingestion_run_id": "uuid",
  "created_at": ISODate(...),
  "updated_at": ISODate(...)
}
```

**Indexes**: `{natural_key: 1}` UNIQUE; `{kalash_natural_key: 1}`.

### 5.8 New collection: `kalash_bhaavarth_hindi`

Hindi bhaavarth for a kalash as published in a specific Publication.

```json
{
  "natural_key": "pravachansaar:amritchandra:anantkirti-granthmala:कलश:भावार्थ:3",
  "kalash_bhaavarth_natural_key": "pravachansaar:amritchandra:anantkirti-granthmala:कलश:भावार्थ:3",
  "publication_natural_key": "pravachansaar:amritchandra:anantkirti-granthmala",
  "kalash_natural_key": "pravachansaar:amritchandra:कलश:3",
  "publisher_id": "anantkirti-granthmala",
  "kalash_number": "3",
  "text": [{"lang": "hin", "script": "Deva", "text": "..."}],
  "ingestion_run_id": "uuid",
  "created_at": ISODate(...),
  "updated_at": ISODate(...)
}
```

**Indexes**: `{natural_key: 1}` UNIQUE; `{publication_natural_key: 1}`;
`{kalash_natural_key: 1}`.

### 5.9 Updated `ensure_indexes()` checklist

Add all six new collections to `packages/jain_kb_common/jain_kb_common/db/mongo/indexes.py`.
Add collection name constants to `collections.py`:

```python
GATHA_TEEKA_SANSKRIT = "gatha_teeka_sanskrit"
GATHA_TEEKA_HINDI = "gatha_teeka_hindi"
GATHA_TEEKA_BHAAVARTH_HINDI = "gatha_teeka_bhaavarth_hindi"
KALASH_SANSKRIT = "kalash_sanskrit"
KALASH_HINDI = "kalash_hindi"
KALASH_BHAAVARTH_HINDI = "kalash_bhaavarth_hindi"
```

Add Pydantic v2 schemas to `schemas.py` for all six.

---

## 6. Neo4j changes

### 6.1 New node labels — properties

| Label | Identifier property | Stored properties | Source of truth |
|-------|--------------------|--------------------|-----------------|
| `Teeka` | `natural_key` | `pg_id`, `shastra_natural_key`, `teekakar_natural_key` (nullable), `updated_at`, `created_at` | Postgres `teekas` |
| `Publication` | `natural_key` | `pg_id`, `teeka_natural_key`, `publisher_id`, `updated_at`, `created_at` | Postgres `publications` |
| `Kalash` | `natural_key` | `pg_id`, `teeka_natural_key`, `kalash_number`, `updated_at`, `created_at` | Postgres `kalashas` |
| `GathaTeeka` | `natural_key` | `shastra_natural_key`, `teeka_natural_key`, `gatha_number`, `updated_at` | Graph-only (lazy) |
| `GathaTeekaBhaavarth` | `natural_key` | `shastra_natural_key`, `teeka_natural_key`, `publisher_id`, `gatha_number`, `updated_at` | Graph-only (lazy) |
| `KalashBhaavarth` | `natural_key` | `shastra_natural_key`, `teeka_natural_key`, `publisher_id`, `kalash_number`, `updated_at` | Graph-only (lazy) |
| `Page` | `natural_key` | `shastra_natural_key`, `teeka_natural_key`, `publisher_id`, `page_number`, `updated_at` | Graph-only (lazy) |

"Graph-only (lazy)" nodes carry no `pg_id` — they are created via `MERGE` the
first time an edge references them.

### 6.2 New structural edge types

| Type | Direction | From → To | Properties | Meaning |
|------|-----------|-----------|------------|---------|
| `IN_TEEKA` | directed | `GathaTeeka → Teeka`, `Kalash → Teeka`, `Publication → Teeka` | — | Structural: node belongs to this teeka |
| `IN_PUBLICATION` | directed | `GathaTeekaBhaavarth → Publication`, `KalashBhaavarth → Publication`, `Page → Publication` | — | Structural: node belongs to this publication |

Update existing `IN_SHASTRA`:
- Add `Teeka` to the `from` list (currently only `Gatha`).
- Edge: `Teeka -[IN_SHASTRA]-> Shastra` (synced in `sync_teeka`).

### 6.3 New content edge type

`CONTAINS_DEFINITION` (directed) — from reference-source node to `Keyword`:

| From labels | To | Properties |
|-------------|-----|------------|
| `Gatha`, `GathaTeeka`, `GathaTeekaBhaavarth`, `Kalash`, `KalashBhaavarth`, `Page` | `Keyword` | `weight: float`, `source: str`, `pankti: int?`, `block_index: int` (see improvements spec) |

This edge is emitted by `build_reference_edges` when context is `definition`
(per `reference_edge_creation_spec.md §1.2`).

### 6.4 Updated `MENTIONS_TOPIC` from-labels

Expand from `[Gatha]` to:
`[Gatha, GathaTeeka, GathaTeekaBhaavarth, Kalash, KalashBhaavarth, Page]`

### 6.5 Constraints & indexes

```cypher
// Uniqueness — new labels
CREATE CONSTRAINT teeka_natural_key IF NOT EXISTS
  FOR (n:Teeka) REQUIRE n.natural_key IS UNIQUE;

CREATE CONSTRAINT publication_natural_key IF NOT EXISTS
  FOR (n:Publication) REQUIRE n.natural_key IS UNIQUE;

CREATE CONSTRAINT gatha_teeka_natural_key IF NOT EXISTS
  FOR (n:GathaTeeka) REQUIRE n.natural_key IS UNIQUE;

CREATE CONSTRAINT gatha_teeka_bhaavarth_natural_key IF NOT EXISTS
  FOR (n:GathaTeekaBhaavarth) REQUIRE n.natural_key IS UNIQUE;

CREATE CONSTRAINT kalash_natural_key IF NOT EXISTS
  FOR (n:Kalash) REQUIRE n.natural_key IS UNIQUE;

CREATE CONSTRAINT kalash_bhaavarth_natural_key IF NOT EXISTS
  FOR (n:KalashBhaavarth) REQUIRE n.natural_key IS UNIQUE;

CREATE CONSTRAINT page_natural_key IF NOT EXISTS
  FOR (n:Page) REQUIRE n.natural_key IS UNIQUE;

// Lookup indexes for Postgres-backed nodes
CREATE INDEX teeka_pg_id IF NOT EXISTS FOR (n:Teeka) ON (n.pg_id);
CREATE INDEX publication_pg_id IF NOT EXISTS FOR (n:Publication) ON (n.pg_id);
CREATE INDEX kalash_pg_id IF NOT EXISTS FOR (n:Kalash) ON (n.pg_id);

// Composite topic index (from schema_updates.md §4.1)
CREATE INDEX topic_kw_path IF NOT EXISTS
  FOR (n:Topic) ON (n.parent_keyword_natural_key, n.topic_path);
```

### 6.6 Sync algorithms

#### `sync_teeka`

```python
async def sync_teeka(
    driver: AsyncDriver,
    *,
    natural_key: str,
    pg_id: str,
    shastra_natural_key: str,
    teekakar_natural_key: str | None = None,
    database: str = "jainkb",
) -> None:
    async with driver.session(database=database) as session:
        await session.run(
            """
            MERGE (t:Teeka {natural_key: $nk})
            SET t.pg_id = $pg_id,
                t.shastra_natural_key = $snk,
                t.teekakar_natural_key = $teekakar,
                t.updated_at = datetime(),
                t.created_at = coalesce(t.created_at, datetime())
            WITH t
            MATCH (s:Shastra {natural_key: $snk})
            MERGE (t)-[:IN_SHASTRA]->(s)
            """,
            nk=natural_key, pg_id=pg_id,
            snk=shastra_natural_key, teekakar=teekakar_natural_key,
        )
```

#### `sync_publication`

```python
async def sync_publication(
    driver: AsyncDriver,
    *,
    natural_key: str,
    pg_id: str,
    teeka_natural_key: str,
    publisher_id: str,
    database: str = "jainkb",
) -> None:
    async with driver.session(database=database) as session:
        await session.run(
            """
            MERGE (p:Publication {natural_key: $nk})
            SET p.pg_id = $pg_id,
                p.teeka_natural_key = $tnk,
                p.publisher_id = $pub_id,
                p.updated_at = datetime(),
                p.created_at = coalesce(p.created_at, datetime())
            WITH p
            MATCH (t:Teeka {natural_key: $tnk})
            MERGE (p)-[:IN_TEEKA]->(t)
            """,
            nk=natural_key, pg_id=pg_id, tnk=teeka_natural_key, pub_id=publisher_id,
        )
```

#### `sync_kalash`

```python
async def sync_kalash(
    driver: AsyncDriver,
    *,
    natural_key: str,
    pg_id: str,
    teeka_natural_key: str,
    kalash_number: str,
    database: str = "jainkb",
) -> None:
    async with driver.session(database=database) as session:
        await session.run(
            """
            MERGE (k:Kalash {natural_key: $nk})
            SET k.pg_id = $pg_id,
                k.teeka_natural_key = $tnk,
                k.kalash_number = $num,
                k.updated_at = datetime(),
                k.created_at = coalesce(k.created_at, datetime())
            WITH k
            MATCH (t:Teeka {natural_key: $tnk})
            MERGE (k)-[:IN_TEEKA]->(t)
            """,
            nk=natural_key, pg_id=pg_id, tnk=teeka_natural_key, num=kalash_number,
        )
```

#### Lazy-MERGE for pure graph nodes

Pure graph nodes (`GathaTeeka`, `GathaTeekaBhaavarth`, `KalashBhaavarth`,
`Page`) are created by the graph-write layer when an edge targets them. Use a
helper:

```python
async def ensure_lazy_node(
    session,
    label: str,
    natural_key: str,
    props: dict,
    parent_edge_type: str,      # "IN_TEEKA" | "IN_PUBLICATION"
    parent_label: str,          # "Teeka" | "Publication"
    parent_natural_key: str,
) -> None:
    await session.run(
        f"""
        MERGE (n:{label} {{natural_key: $nk}})
        SET n += $props,
            n.updated_at = datetime(),
            n.created_at = coalesce(n.created_at, datetime())
        WITH n
        MERGE (parent:{parent_label} {{natural_key: $parent_nk}})
        MERGE (n)-[:{parent_edge_type}]->(parent)
        """,
        nk=natural_key, props=props, parent_nk=parent_natural_key,
    )
```

This is called from `envelope.py` / graph-write layer before (or alongside)
emitting the reference edge.

#### `envelope.py` — node emission for new labels

`build_neo4j_fragment` currently only emits `Keyword` and `Topic` nodes.
Extend to also emit node objects for each unique source node in reference
edges:

```python
# After calling build_reference_edges for a block:
for edge in ref_edges:
    src = edge["from"]
    label = src["label"]
    key = src["key"]
    if label in LAZY_NODE_LABELS:  # GathaTeeka, GathaTeekaBhaavarth, KalashBhaavarth, Page
        node_objects.add_lazy(label, key, _derive_props(label, key))
    # Postgres-backed nodes (Gatha, Teeka, Kalash) already in nodes[] from their sync path
```

`LAZY_NODE_LABELS = {"GathaTeeka", "GathaTeekaBhaavarth", "KalashBhaavarth", "Page"}`

`_derive_props(label, key)` extracts properties by splitting the key on `:`
according to the format table in §3.

The lazy node objects appear in `would_write.neo4j.nodes` with a `lazy: true`
flag so the sync layer knows to use `ensure_lazy_node` rather than a typed
`sync_*` function.

---

## 7. `edge_types.yaml` changes

Full updated file. Replace the existing
`parser_configs/_meta/edge_types.yaml`:

```yaml
# Canonical edge type registry for the Neo4j graph.
# schema_check.py rejects graph writes that use unlisted types.
# To add a new type: append it here (no migration required).

edge_types:
  - name: IS_A
    direction: directed
    from: [Topic, Keyword]
    to: [Topic, Keyword]
    description: Hyponym/hypernym (e.g. अंतरात्मा IS_A आत्मा)

  - name: PART_OF
    direction: directed
    from: [Topic]
    to: [Topic]
    description: Sub-topic of another topic. Created from topic_path hierarchy.

  - name: RELATED_TO
    direction: undirected
    from: [Topic, Keyword]
    to: [Topic, Keyword]
    description: Soft association (stored as two reciprocal directed edges)

  - name: ALIAS_OF
    direction: directed
    from: [Alias]
    to: [Keyword]
    description: Synonym / variant spelling

  - name: MENTIONS_KEYWORD
    direction: directed
    from: [Topic]
    to: [Keyword]
    description: Topic body mentions this keyword (used to seed queries)

  - name: HAS_TOPIC
    direction: directed
    from: [Keyword]
    to: [Topic]
    description: Keyword JainKosh page yielded this topic

  - name: MENTIONS_TOPIC
    direction: directed
    from: [Gatha, GathaTeeka, GathaTeekaBhaavarth, Kalash, KalashBhaavarth, Page]
    to: [Topic]
    description: Source node cites a topic (heading or extracted reference)

  - name: CONTAINS_DEFINITION
    direction: directed
    from: [Gatha, GathaTeeka, GathaTeekaBhaavarth, Kalash, KalashBhaavarth, Page]
    to: [Keyword]
    description: Source node appears in the definition body of this keyword

  - name: IN_SHASTRA
    direction: directed
    from: [Gatha, Teeka]
    to: [Shastra]
    description: Structural membership — node belongs to this shastra

  - name: IN_TEEKA
    direction: directed
    from: [GathaTeeka, Kalash, Publication]
    to: [Teeka]
    description: Structural membership — node belongs to this teeka

  - name: IN_PUBLICATION
    direction: directed
    from: [GathaTeekaBhaavarth, KalashBhaavarth, Page]
    to: [Publication]
    description: Structural membership — node belongs to this publication
```

---

## 8. Code files to create / modify

| File | Action | What to do |
|------|--------|-----------|
| `packages/jain_kb_common/jain_kb_common/db/postgres/publications.py` | CREATE | `Publication` SQLAlchemy model |
| `packages/jain_kb_common/jain_kb_common/db/postgres/kalashas.py` | CREATE | `Kalash` SQLAlchemy model + `bhaavarth_doc_ids` |
| `packages/jain_kb_common/jain_kb_common/db/postgres/__init__.py` | MODIFY | Export new models |
| `packages/jain_kb_common/jain_kb_common/db/postgres/upserts.py` | MODIFY | Add `upsert_publication`, `upsert_kalash` |
| `packages/jain_kb_common/jain_kb_common/db/mongo/collections.py` | MODIFY | Add 6 new collection name constants |
| `packages/jain_kb_common/jain_kb_common/db/mongo/schemas.py` | MODIFY | Add Pydantic models for 6 new collections + correct `Reference` shape |
| `packages/jain_kb_common/jain_kb_common/db/mongo/indexes.py` | MODIFY | Add `ensure_indexes` calls for 6 new collections |
| `packages/jain_kb_common/jain_kb_common/db/mongo/upserts.py` | MODIFY | Add upsert functions for 6 new collections |
| `packages/jain_kb_common/jain_kb_common/db/neo4j/constraints.py` | MODIFY | Add 7 new `CREATE CONSTRAINT` + 3 new `CREATE INDEX` statements |
| `packages/jain_kb_common/jain_kb_common/db/neo4j/upserts.py` | MODIFY | Add `sync_teeka`, `sync_publication`, `sync_kalash`, `ensure_lazy_node` |
| `parser_configs/_meta/edge_types.yaml` | MODIFY | Full replacement per §7 |
| `migrations/versions/0010_topics_hierarchy.py` | CREATE | Per `schema_updates.md §2.4` |
| `migrations/versions/0011_publications.py` | CREATE | `publications` table |
| `migrations/versions/0012_kalashas.py` | CREATE | `kalashas` table |
| `workers/ingestion/jainkosh/envelope.py` | MODIFY | Emit lazy node objects for pure-graph node labels |

---

## 9. Original doc update tasks

These docs must be updated to reflect the new schema. Update them after the
code changes are complete.

| Doc | What to update |
|-----|---------------|
| `docs/design/data_model_postgres.md` | Add `publications` and `kalashas` tables + DDL. Add migration entries `0011`, `0012`. Apply `topics` updates from `schema_updates.md §5.1`. Add `upsert_publication` and `upsert_kalash` examples. |
| `docs/design/03_data_model_mongo.md` | Correct `keyword_definitions.references` object shape (§5.1). Correct `subsection_tree` to remove `blocks` (§5.2). Add all 6 new collections (§5.3–5.8). Add updated `ensure_indexes()` list. |
| `docs/design/04_data_model_graph.md` | Add 7 new node labels to the "Node labels" table (§6.1). Add `IN_TEEKA`, `IN_PUBLICATION`, `CONTAINS_DEFINITION` to "Edge types" table. Expand `IN_SHASTRA` from-list, `MENTIONS_TOPIC` from-list. Add new Cypher constraints block (§6.5). Add `sync_teeka`, `sync_publication`, `sync_kalash`, `ensure_lazy_node` to the "Sync algorithm" section. Update "Driver layout" to list the new functions. |
| `docs/design/jainkosh/schema_updates.md` | Add a "Status" note: Postgres topics hierarchy is subsumed into migration `0010`. Point forward to this spec for new entities. |
| `docs/design/00_overview.md` | In the "Topic Knowledge Graph" bullet: mention `Teeka`, `Publication`, `Kalash`, and the new edge types. In "Graph" row of Data Stores table: update the edge-type list. |

---

## 10. Migration order (implementation)

Apply in this order when wiring the ingestion pipeline:

1. Run `0010_topics_hierarchy.py` (topics hierarchy columns + check constraint).
2. Run `0011_publications.py` (publications table).
3. Run `0012_kalashas.py` (kalashas table).
4. On `dictionary-service` / `metadata-service` startup, `ensure_indexes()`
   creates the six new Mongo collections' indexes.
5. On service startup, `ensure_constraints()` creates the 7 new Neo4j
   constraints and 3 new indexes.
6. Update `edge_types.yaml` (no migration — schema_check reads it at runtime).
7. Parser runs are now safe: reference edges can resolve to the correct node
   labels, and lazy nodes are created via `MERGE`.

Because no data is in production yet, this is a zero-downtime cold start.

---

## 11. Definition of Done

### Postgres
- [ ] `publications` table exists with `idx_publications_teeka` index.
- [ ] `kalashas` table exists with `idx_kalashas_teeka` index.
- [ ] `topics` has `topic_path`, `parent_topic_id`, `is_leaf`, `is_synthetic`, and CHECK constraint.
- [ ] Migrations `0010`–`0012` exist and are idempotent (run twice → same result).
- [ ] `Publication` and `Kalash` SQLAlchemy models pass `mypy --strict`.
- [ ] `upsert_publication`, `upsert_kalash` follow the idempotent upsert pattern.

### MongoDB
- [ ] `keyword_definitions` Pydantic schema validates the corrected `references` shape (with `resolved_fields`, `shastra_name`, `teeka_name`, `inline_reference`).
- [ ] All 6 new collection schemas exist in `schemas.py` and validate sample fixtures.
- [ ] `ensure_indexes()` creates all indexes on startup without error.
- [ ] `stable_id` / `natural_key` upserts proven idempotent for new collections.

### Neo4j
- [ ] `ensure_constraints()` creates all 7 new `UNIQUE` constraints and 3 new `pg_id` indexes without error.
- [ ] `sync_teeka`, `sync_publication`, `sync_kalash` all idempotent (proven by rerunning on same input).
- [ ] `ensure_lazy_node` creates node + structural edge in one round trip; idempotent.
- [ ] `edge_types.yaml` passes `schema_check.validate_edge_type` for all 10 edge types.
- [ ] Smoke test: ingest 1 JainKosh keyword with references → graph has `GathaTeeka`, `Page` nodes, `MENTIONS_TOPIC` and `CONTAINS_DEFINITION` edges.

### Docs
- [ ] All five docs listed in §9 updated.
