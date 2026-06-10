# NJ Tables — Phase 1: Schema (`table_type`)

Adds a typed-category field to the existing `Table` entity so consumers can distinguish a plain index/ToC table (NJ shastra pages) from richer special tables (future). Required by all later phases.

Parent wiki: [docs/design/objects/table/README.md](../../README.md)

---

## 1. Allowed values

```
TableType = Literal["index", "general"]
```

- `"index"` — a structural index/ToC inside a teeka/bhaavarth (e.g. *सारिणी* tables on NJ pages). Phase 2 emits this for every NJ-parsed table.
- `"general"` — default for every existing JainKosh table (backfill value).

The list is closed but extendable in code only — no enum at the Postgres level (use `TEXT` + CHECK constraint so future values are a one-line change).

---

## 2. Postgres

### Migration `migrations/versions/0022_tables_table_type.py`

```python
def upgrade():
    op.add_column(
        "tables",
        sa.Column("table_type", sa.Text(), nullable=False, server_default="general"),
    )
    op.create_check_constraint(
        "tables_table_type_check",
        "tables",
        "table_type IN ('index','general')",
    )
    op.create_index("idx_tables_type", "tables", ["table_type"])

def downgrade():
    op.drop_index("idx_tables_type", table_name="tables")
    op.drop_constraint("tables_table_type_check", "tables")
    op.drop_column("tables", "table_type")
```

`server_default="general"` ensures all existing JK rows are backfilled in-place — no data migration script needed.

### Model `packages/jain_kb_common/jain_kb_common/db/postgres/tables.py`

- Add `table_type: Mapped[str] = mapped_column(sa.Text, nullable=False, server_default="general")`.
- Extend `upsert_table(...)` signature with `table_type: str = "general"` and include it in the `INSERT` + `ON CONFLICT DO UPDATE SET` clauses.

---

## 3. MongoDB

`TableDoc` in `packages/jain_kb_common/jain_kb_common/db/mongo/schemas.py`:

```python
table_type: Literal["index", "general"] = "general"
```

Add to `$set` in `upsert_table` (Mongo upsert). No index needed for v1.

---

## 4. Neo4j

`Table` node in `packages/jain_kb_common/jain_kb_common/db/neo4j/upserts.py`:

- Add `table_type` to the prop set inside `sync_table(...)` MERGE-SET.
- Add index in `constraints.py`:
  ```cypher
  CREATE INDEX table_type IF NOT EXISTS FOR (n:Table) ON (n.table_type);
  ```

---

## 5. Parser model

`ParsedTable` in `workers/ingestion/jainkosh/models.py` (also used by NJ in Phase 2 — it lives in the shared models module or gets duplicated under NJ; **decision**: move `ParsedTable` to `packages/jain_kb_common/.../models.py` shared layer, or copy verbatim into `workers/ingestion/nj/models.py`. Phase 1 deliverable: keep it where it is and add the field there; Phase 2 imports it.):

```python
table_type: Literal["index", "general"] = "general"
```

`WouldWriteEnvelope.tables` already serialises this through `model_dump()`.

---

## 6. Apply

`workers/ingestion/jainkosh/apply.py` — when calling `upsert_table` (PG) and `upsert_table` (Mongo) and `sync_table` (Neo4j), forward `parsed_table.table_type`. JK parser keeps default `"general"`.

---

## 7. API

- `services/core_service/domains/data/schemas/tables.py` — add `table_type: str` to `TableResponse` and `TableSummary`.
- `services/core_service/domains/data/services/tables.py` — select the column from PG, return in payload.

---

## 8. UI

`ui/src/lib/types.ts`:

```ts
export type TableType = "index" | "general";

export interface TableSummary { /* ... */ tableType: TableType; }
export interface TableFull    { /* ... */ tableType: TableType; }
```

API client maps `table_type` → `tableType`.

---

## 9. Tests

- `tests/db/test_postgres_tables.py` — add `test_upsert_table_table_type_default_and_override`.
- `tests/db/test_mongo_tables.py` — round-trip `table_type="index"`.
- `tests/db/test_neo4j_tables.py` — MERGE preserves `table_type`.
- `tests/services/data/test_tables.py` — response includes `table_type`.
- `ui/src/__tests__/api/data.test.ts` — snake→camel mapping.

### Run

```bash
alembic upgrade head
export DATABASE_URL=... MONGO_URL=... NEO4J_URL=...
python -m pytest tests/db/ tests/services/data/test_tables.py -v
cd ui && pnpm test
```

---

## 10. Manual verification

```bash
psql jain_kb_dev -c "SELECT natural_key, table_type FROM tables LIMIT 5;"
# All existing rows → 'general'
```

---

## 11. Implementation Notes (2026-06-10)

- Migration `migrations/versions/0022_tables_table_type.py` adds the column, CHECK constraint (`table_type IN ('index','general')`), and `idx_tables_type` index. Existing JK row backfilled to `'general'` via `DEFAULT 'general'`.
- `Table` SQLAlchemy model gains `table_type` (server_default `"general"`) and an index entry in `__table_args__`.
- `upsert_table` (PG) accepts `table_type: str = "general"`, writes it on INSERT and on the `ON CONFLICT DO UPDATE SET` branch.
- Mongo `TableDoc` schema adds `table_type: str = "general"`. JK apply layer (`workers/ingestion/jainkosh/apply.py`) forwards `t.get("table_type", "general")` into PG upsert, Mongo upsert doc, and Neo4j `sync_table`.
- `sync_table` (Neo4j) sets `t.table_type = $table_type` on MERGE; new constraint `table_type` index added in `constraints.py`.
- `ParsedTable` (in `workers/ingestion/jainkosh/models.py`) gets `table_type: Literal["index","general"] = "general"`.
- Hydration helpers (`jain_kb_common.hydration.tables.TableSummary` and `TableResponse`) and the duplicate service-side schemas (`services/core_service/domains/data/schemas/tables.py`) both now expose `table_type: str = "general"`.
- UI types: `TableType = 'index' | 'general'`; `TableSummary.tableType` and `TableFull.tableType` added. No api-client mapping change needed — the existing modal already falls back to snake_case via raw access; Phase 4 will consume `(raw as any).table_type ?? table.tableType`.
- Test added: `tests/db/postgres/test_idempotent_upsert.py::test_upsert_table_table_type_index` (and the existing JK idempotent test asserts default = `"general"`).
- Test DB does **not** run alembic — schema is created by `Base.metadata.create_all`, so the model's `server_default` covers it. Dev DB was migrated cleanly (`alembic upgrade head`: 0021 → 0022).

## 12. Done when

- `alembic upgrade head` is green; `alembic downgrade -1` cleans up.
- All existing JK ingestion runs still apply cleanly with `table_type='general'`.
- API + UI types compile; field appears in `GET /v1/tables/{nk}` responses.
- No Phase 2/3/4 work is started before this phase merges.
