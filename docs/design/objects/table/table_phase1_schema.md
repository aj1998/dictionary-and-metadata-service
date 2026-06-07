# Phase 1 — Table: Schema (Postgres + Mongo + Neo4j)

**Owner**: backend
**Prereqs**: none
**Scope**: data-layer only. No parser, no apply, no UI in this phase.

## Goal

Stand up the storage schema for the new `Table` entity in all three stores, with idempotent upserts and indexes wired in, and update the parent data-model docs.

## 1. Postgres — `tables` index row

Add a new table `tables` mirroring the pattern used by [`gathas`](../data_model/data_model_postgres.md#gathas) and [`kalashas`](../data_model/data_model_postgres.md#kalashas).

```sql
CREATE TABLE tables (
  id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  natural_key            TEXT NOT NULL UNIQUE,
  source                 ingestion_source NOT NULL,
  parent_natural_key     TEXT NOT NULL,                  -- naturalKey of the parent (Topic/Keyword/Gatha/...)
  parent_kind            TEXT NOT NULL,                  -- 'topic' | 'keyword' | 'gatha' | 'gatha_teeka' | 'gatha_teeka_bhaavarth' | 'kalash' | 'kalash_bhaavarth' | 'page'
  seq                    INT  NOT NULL,                  -- 1-indexed position within parent in source order
  caption                JSONB,                          -- [{lang, script, text}] — preceding heading or first cell
  source_url             TEXT,                           -- deep-link including anchor
  raw_html_doc_id        TEXT NOT NULL,                  -- Mongo `tables` _id (stable, see §2)
  graph_node_id          TEXT,                           -- Neo4j naturalKey (= this.natural_key)
  ingestion_run_id       UUID REFERENCES ingestion_runs(id) ON DELETE SET NULL,
  created_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (parent_natural_key, seq)
);

CREATE INDEX idx_tables_parent ON tables(parent_natural_key);
CREATE INDEX idx_tables_source ON tables(source);
CREATE INDEX idx_tables_run    ON tables(ingestion_run_id);
```

### naturalKey

```
table:<source>:<parent_natural_key>:<seq:02d>
```

Examples:
- `table:jainkosh:द्रव्य:षट्द्रव्य-विभाजन:द्रव्य-के-या-वस्तु-के-एक-दो-आदि-भेदों-की-अपेक्षा-विभाग:01`
- `table:jainkosh:आत्मा:02`

### Alembic migration

Add `migrations/0020_tables.py` (next free version after `0019_teeka_chapters.py`). Pure DDL: create table, create indexes. No data backfill. Down-migration drops the table.

### SQLAlchemy model

`packages/jain_kb_common/jain_kb_common/db/postgres/tables.py` — `Table` model + `upsert_table(session, *, natural_key, source, parent_natural_key, parent_kind, seq, caption, source_url, raw_html_doc_id, ingestion_run_id) -> uuid.UUID` (idempotent via `ON CONFLICT (natural_key) DO UPDATE SET ... RETURNING id`).

Add import in `packages/jain_kb_common/jain_kb_common/db/postgres/__init__.py`.

## 2. Mongo — `tables` collection

Long-form raw HTML + parsed cell matrix. Schema in `packages/jain_kb_common/jain_kb_common/db/mongo/schemas.py`:

```python
class TableDoc(BaseModel):
    natural_key: str
    table_id: str | None           # Postgres tables.id (injected at apply time)
    source: str                    # ingestion_source value
    parent_natural_key: str
    parent_kind: str
    seq: int
    source_url: str | None
    caption: list[LangText] = []
    raw_html: str
    cells: list[list[str]] = []    # parsed 2D string matrix (NFC-normalized, '' for missing cells)
    header_rows: int = 0           # number of leading rows that are <th>-headers
    mentioned_keyword_natural_keys: list[str] = []
    mentioned_topic_natural_keys: list[str] = []
    plaintext: str | None = None   # whitespace-normalized concatenation of cells, for text search
    ingestion_run_id: str | None = None
    parser_version: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
```

Collection constant `TABLES = "tables"` in `db/mongo/collections.py`.

`db/mongo/upserts.py`:

```python
async def upsert_table(db, *, natural_key: str, doc: dict) -> ObjectId:
    _id = stable_id(natural_key)
    doc = {**doc, "natural_key": natural_key, "updated_at": datetime.utcnow()}
    await db[TABLES].update_one(
        {"_id": _id},
        {"$set": doc, "$setOnInsert": {"created_at": datetime.utcnow()}},
        upsert=True,
    )
    return _id
```

`db/mongo/indexes.py` — register in `ensure_indexes()`:

```python
await db[TABLES].create_index("natural_key", unique=True)
await db[TABLES].create_index([("parent_natural_key", 1), ("seq", 1)])
await db[TABLES].create_index("ingestion_run_id")
await db[TABLES].create_index([("plaintext", "text"), ("caption.text", "text")], default_language="none")
```

## 3. Neo4j — `Table` node + `CONTAINS_TABLE` edge

### Node

Label `Table`. Identifier `natural_key`. Stored properties:

```
pg_id, source, parent_natural_key, parent_kind, seq, caption_hi, is_stub, created_at, updated_at
```

(Heavy fields — raw_html, cells, plaintext — stay in Mongo and are fetched via `pg_id`/`natural_key`.)

### Constraints + indexes

In `packages/jain_kb_common/jain_kb_common/db/neo4j/constraints.py`:

```cypher
CREATE CONSTRAINT table_natural_key IF NOT EXISTS FOR (n:Table) REQUIRE n.natural_key IS UNIQUE;
CREATE INDEX table_pg_id IF NOT EXISTS FOR (n:Table) ON (n.pg_id);
CREATE INDEX table_is_stub IF NOT EXISTS FOR (n:Table) ON (n.is_stub);
CREATE INDEX table_parent IF NOT EXISTS FOR (n:Table) ON (n.parent_natural_key);
```

### Edge type

Append to `parser_configs/_meta/edge_types.yaml`:

```yaml
- name: CONTAINS_TABLE
  from: [Topic, Keyword, Gatha, GathaTeeka, GathaTeekaBhaavarth, Kalash, KalashBhaavarth, Page]
  to:   [Table]
  properties: [weight, source]
```

`MENTIONS_KEYWORD` and `MENTIONS_TOPIC` already exist; extend their `from:` lists to include `Table`.

### Upsert

`packages/jain_kb_common/jain_kb_common/db/neo4j/upserts.py` — `sync_table(neo4j, pg_table_row)`; uses `MERGE` + `ON CREATE SET created_at=datetime()`, mirrors `sync_topic` semantics. Add `sync_contains_table_edge(neo4j, *, parent_label, parent_nk, table_nk, source)`.

### Stub helper

In `db/neo4j/stubs.py`, add a `Table` branch to `sync_stub_node()` so other ingestors can create a stub Table referenced before its full row exists.

## 4. Tests (this phase)

- `tests/db/postgres/test_idempotent_upsert.py` — add `test_upsert_table_idempotent` (insert, re-insert, assert row count = 1 and fields overwritten).
- `tests/db/mongo/test_mongo_upsert.py` — add `test_upsert_table_doc_idempotent` (stable_id round-trip, indexes created).
- `tests/db/neo4j/test_neo4j_graph.py` — add `test_table_constraints_and_contains_edge` (create Topic + Table, MERGE `CONTAINS_TABLE`, re-run, assert one edge).

Run:

```bash
export DATABASE_URL="postgresql+asyncpg://$(whoami)@localhost/jain_kb_test"
export MONGO_URL="mongodb://localhost:27017"
export NEO4J_URL="bolt://localhost:7687"
export NEO4J_USER=neo4j
export NEO4J_PASSWORD=jainkb_password
python -m pytest tests/db/ -v
```

## 5. Doc updates (do these in the same PR)

- [`docs/design/data_model/data_model_postgres.md`](../data_model/data_model_postgres.md) — add a `tables` section right after `kalashas`, list `0020_tables.py` in the migration plan, add `tables.py` to the SQLAlchemy model layout, append `upsert_table` to the DoD checklist.
- [`docs/design/data_model/data_model_mongo.md`](../data_model/data_model_mongo.md) — add collection `17. tables` after `kalash_word_meanings`, add row to the Reference Resolution table mapping `Postgres tables.raw_html_doc_id → Mongo tables._id`.
- [`docs/design/data_model/data_model_graph.md`](../data_model/data_model_graph.md) — add `Table` to the Node labels table, add `CONTAINS_TABLE` to the Edge types table, extend `MENTIONS_KEYWORD` / `MENTIONS_TOPIC` rows to include `Table` as a valid `from:`, add the new Cypher constraints/indexes block, add `Table` to DoD smoke-test.
- [`README.md`](../../../README.md) (root) — extend the Neo4j row in §Data Stores to mention `Table` label and `CONTAINS_TABLE` edge; add `tables` to the Mongo collections cleared by `clear_dbs.py` in §Scripts.

## 6. Definition of Done

- [ ] `alembic upgrade head` succeeds; `tables` row visible in Postgres.
- [ ] `ensure_indexes()` creates the `tables` collection + 4 indexes.
- [ ] `ensure_constraints()` creates the `Table` constraint + 3 indexes.
- [ ] `edge_types.yaml` lists `CONTAINS_TABLE`; `schema_check.py` accepts it.
- [ ] All three DB-layer tests pass; existing tests unaffected.
- [ ] Parent docs updated as in §5.

## 7. Implementation notes

- Added `datetime` import to `mongo/schemas.py` (was missing, needed by `TableDoc`).
- Added `import jain_kb_common.db.postgres.tables` to `tests/conftest.py` so SQLAlchemy metadata picks up the `Table` model and `create_all()` creates the `tables` table in test runs.
- `alembic upgrade head` requires an initialized database (previous migrations applied). The new migration `0020_tables.py` follows the same pure-DDL pattern as `0019_teeka_chapters.py` and includes a `set_updated_at` trigger consistent with the other tables.
- The unique constraint `(parent_natural_key, seq)` is defined inline in the DDL (not as a separate `CREATE UNIQUE INDEX`) to match the spec's SQL.
- `_VALID_LABELS` in `neo4j/upserts.py` was extended to include `"Table"` so `sync_contains_table_edge` can use it for label validation.
