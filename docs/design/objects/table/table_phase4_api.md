# Phase 4 — Table: API + hydration + graph traversal

**Owner**: backend / services
**Prereqs**: [Phase 3](./table_phase3_apply.md) merged.
**Scope**: `services/core_service/` and `packages/jain_kb_common/hydration/`. No UI.

## Goal

Expose Tables over HTTP so the UI (Phase 5) can fetch a table by natural_key, list tables for a parent, and see Tables as nodes in graph traversal.

## 1. Data-domain endpoint — `GET /v1/tables/{natural_key}`

`services/core_service/api/data/tables.py`:

Response model `TableResponse`:

```python
class TableResponse(BaseModel):
    natural_key: str
    pg_id: str
    source: str
    parent_natural_key: str
    parent_kind: str
    seq: int
    caption: list[LangText]
    source_url: str | None
    raw_html: str
    cells: list[list[str]]
    header_rows: int
    plaintext: str | None
    mentioned_keyword_natural_keys: list[str]
    mentioned_topic_natural_keys: list[str]
```

Loads Postgres `tables` row by natural_key → joins Mongo `tables` doc by `raw_html_doc_id`. 404 if absent.

Also add `GET /v1/tables?parent_natural_key=...` returning a minimal list `[{natural_key, seq, caption}]` ordered by `seq` (for "tables on this topic" sections in UI).

Register router in `services/core_service/api/data/__init__.py`.

## 2. Hydration

`packages/jain_kb_common/hydration/tables.py`:

```python
async def hydrate_tables_for_parent(pg, mongo, *, parent_natural_key: str) -> list[TableSummary]: ...
async def hydrate_table_full(pg, mongo, *, natural_key: str) -> TableResponse | None: ...
```

`TableSummary` = `{natural_key, seq, caption}`. Used by topic / keyword / gatha detail responses to attach a `tables: [TableSummary]` list.

Extend the existing `hydrate_*` helpers for topics and keywords (`hydrate_topic_extracts_hi`, etc.) to call `hydrate_tables_for_parent` and include the result on their response.

## 3. Navigation / graph traversal

`services/core_service/api/navigation/`:

- Add `Table` to the labels traversed in `landing` / `expand` / `preview` queries (right alongside `Gatha|GathaTeeka|...`).
- Add `CONTAINS_TABLE` to the edge-type list returned by `expand` / `preview`. Keep direction info.
- Extend the `EntityKind` literal — add `"table"` — and route Table nodes to it in the payload builder.
- `exclude_stubs` semantics: tables are never stubs from JainKosh (always created with full data), so they appear with `is_stub=false`. NJ-stubs (Phase 6+) would change this.

Default traversal includes Tables. UI handles whether to filter them.

## 4. Query service (optional in this phase)

`services/query_service/` — extend `GET /v1/topics/{nk}/full` and `GET /v1/keywords/{nk}/full` responses with `tables: [TableSummary]`. Wire via the same hydrator. No new endpoint.

## 5. Tests

`tests/services/data/test_tables.py` (new):

- `test_get_table_by_natural_key` — fixture loaded → 200 with full payload.
- `test_get_table_404` — unknown nk → 404.
- `test_list_tables_for_parent_returns_in_seq_order`.
- `test_get_table_joins_mongo_doc` — missing Mongo doc → returns row with empty cells + warning log (don't 500).

`tests/services/navigation/test_graph_includes_tables.py`:

- Seed Topic + Table + CONTAINS_TABLE → `landing(topic_nk)` returns the Table node with `entity_kind="table"`.
- `expand` returns the `CONTAINS_TABLE` edge.
- `exclude_stubs=true` still returns non-stub Tables.

`tests/services/query/` — extend an existing topic-full test to assert `tables[]` populated when fixture has a table.

`tests/common/hydration/test_hydration.py` — add `test_hydrate_tables_for_parent`.

```bash
export DATABASE_URL="postgresql+asyncpg://$(whoami)@localhost/jain_kb_test"
export NEO4J_PASSWORD=jainkb_password
python -m pytest tests/services/ tests/common/ -v
```

## 6. Doc updates

- [`docs/design/api/README.md`](../api/README.md) — new "Tables" section under data domain: `GET /v1/tables/{nk}` + `GET /v1/tables?parent_natural_key=...`. Update OpenAPI examples.
- [`docs/design/data_model/data_model_graph.md`](../data_model/data_model_graph.md) — Query Patterns section: add `Tables for a topic`:
  ```cypher
  MATCH (t:Topic {natural_key:$nk})-[:CONTAINS_TABLE]->(tbl:Table)
  RETURN tbl.natural_key, tbl.seq, tbl.caption_hi ORDER BY tbl.seq;
  ```
- [`docs/manual_testing/api/data/testing.md`](../../manual_testing/api/data/testing.md) — add manual `curl` examples for both new endpoints.
- [`README.md`](../../../README.md) (root) — extend Neo4j data-stores row to list `table` EntityKind in the UI mapping, and add Table label to the traversal label list.

## 7. Definition of Done

- [ ] Both endpoints return JSON shaped as spec; OpenAPI updated.
- [ ] Navigation graph payload includes `Table` nodes + `CONTAINS_TABLE` edges with `entity_kind="table"`.
- [ ] Topic/keyword full responses include `tables[]` summaries.
- [ ] All new tests pass; full `tests/services/` + `tests/common/` suite green.
- [ ] Docs updated.

## 8. Implementation notes

- **Hydration module** (`packages/jain_kb_common/jain_kb_common/hydration/tables.py`): Defines shared `TableSummary` and `TableResponse` Pydantic models. `hydrate_tables_for_parent` queries PG by `parent_natural_key` ordered by `seq`. `hydrate_table_full` fetches the PG row then the Mongo doc by `natural_key`; if Mongo doc is absent it returns an empty-cells response (logs warning, does not 500). `hydration/__init__.py` updated to re-export these.
- **API schemas** (`domains/data/schemas/tables.py`): Re-exports the same field shape as the hydration models. Thin wrappers used for FastAPI response typing.
- **Router** (`domains/data/routers/tables.py`): `GET /v1/tables/{natural_key}` → 200 or 404; `GET /v1/tables?parent_natural_key=...` → list ordered by seq; `parent_natural_key` is required (missing → 422). Both set `Cache-Control: public, max-age=60`.
- **Graph traversal** (`domains/navigation/routers/graph.py`): Added `Table` to `_label_to_kind` mapping → `"table"`. Added `CONTAINS_TABLE` to the edge-type union in both `landing` and `expand` Cypher strings. Added `OR s:Table / OR t:Table` to the node label filters in `landing`.
- **Mongo lookup strategy**: Fetches by `natural_key` field (not by `_id` ObjectId) for simplicity. Both PG and Mongo store `natural_key` as a unique index.
- **Query service** (§4): Deferred — not implemented in this phase.
- **Tests**: All 354 pre-existing tests still pass; 16 new tests added across `test_tables.py`, `test_graph_includes_tables.py`, and `test_hydration.py`.
