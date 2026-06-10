# NJ Tables — Phase 3: Apply + Neo4j edge

Persist the Phase-2 `ParsedTable`s for NJ into Postgres / Mongo / Neo4j, and emit a `CONTAINS_TABLE` edge from the owning `GathaTeekaBhaavarth` (or `KalashBhaavarth`) node to the new `Table` node.

Depends on: [Phase 1 — Schema](./nj_tables_phase1_schema.md), [Phase 2 — Parser](./nj_tables_phase2_parser.md)
Parent wiki: [../README.md](../../README.md) §7

---

## 1. Apply order

In `workers/ingestion/nj/apply.py` — `apply_nj_envelope()` (or wherever NJ writes are committed), after the bhaavarth document is written and **before** stub-edge linking:

```
for parsed_table in envelope.tables:                # carries table_type='index'
    1. upsert_table (Postgres)             → table_id
       fields: natural_key, source='nj', parent_natural_key,
               parent_kind, seq, table_type, caption, source_url,
               raw_html_doc_id = str(stable_id(natural_key))
    2. upsert_table (Mongo) with table_id, table_type, raw_html, cells, ...
    3. sync_table (Neo4j MERGE Table node) — props include table_type
    4. sync_contains_table_edge(
          parent_label='GathaTeekaBhaavarth' | 'KalashBhaavarth',
          parent_nk=parsed_table.parent_natural_key,
          table_nk=parsed_table.natural_key,
          source='nj',
       )
    5. For each mentioned_keyword_nk / topic_nk (typically empty for NJ):
          stub-link as today.
```

`PARENT_KIND_TO_LABEL` already contains `gatha_teeka_bhaavarth → GathaTeekaBhaavarth` and `kalash_bhaavarth → KalashBhaavarth` — reuse from `workers/ingestion/jainkosh/apply.py` (export it from a shared module or duplicate the literal map).

---

## 2. Envelope contracts

`workers/ingestion/nj/envelope.py` — `_NJ_CONTRACTS` add (already drafted in Phase 2 §4):

```python
"postgres:tables": { ... },
"mongo:tables":    { ... fields_replace: ["table_type","raw_html","cells","cell_refs","header_rows","plaintext","caption","mentioned_keyword_natural_keys","mentioned_topic_natural_keys"] ... },
"neo4j:Table":     { conflict_key:["key"], on_conflict:"merge",
                     fields_replace:["table_type","seq","caption_hi","parent_natural_key","parent_kind","pg_id","source"], ... },
```

---

## 3. `clear_dbs.py`

Already truncates `tables` (Postgres) and drops `tables` (Mongo) from Phase 5 of the JK rollout. No change needed — verify only.

---

## 4. Idempotency

- Re-running ingestion for the same gatha must not duplicate Table rows (UNIQUE on `natural_key`) nor duplicate `CONTAINS_TABLE` edges (MERGE).
- Changing `table_type` between runs (e.g. fixing a misclassification) **updates** the row (already in `fields_replace`).

---

## 5. Tests (`tests/ingestion/`)

`test_apply_nj_tables.py`:
- `test_apply_persists_nj_table_to_postgres` — row exists with `source='nj'`, `table_type='index'`, `parent_kind='gatha_teeka_bhaavarth'`.
- `test_apply_persists_nj_table_to_mongo` — doc has `cells`, `raw_html`, `table_type`.
- `test_apply_creates_contains_table_edge_from_bhaavarth_node` — Cypher:
  ```cypher
  MATCH (b:GathaTeekaBhaavarth {natural_key:$nk})-[:CONTAINS_TABLE]->(t:Table)
  RETURN t.natural_key, t.table_type
  ```
  returns the table once.
- `test_apply_nj_table_idempotent` — apply twice; PG row count = 1, edge count = 1.
- `test_kalash_bhaavarth_parent` — same flow for a secondary-kalash page table.

### Run

```bash
export DATABASE_URL=... MONGO_URL=... NEO4J_URL=...
python scripts/clear_dbs.py
python -m pytest tests/ingestion/test_apply_nj_tables.py -v
```

---

## 6. Manual smoke

```bash
python scripts/clear_dbs.py
NIKKYJAIN_LOCAL_PATH=/Users/anubhavjain/Coding/Jinvani/nikkyjain.github.io \
  python -m workers.ingestion.nj.cli parse --config parser_configs/nj/panchastikaya.yaml \
  --batch-offset 0 --batch-limit 10 --apply

psql jain_kb_dev -c \
  "SELECT natural_key, table_type, parent_kind FROM tables WHERE source='nj';"
cypher-shell -u neo4j -p jainkb_password \
  "MATCH (b:GathaTeekaBhaavarth)-[:CONTAINS_TABLE]->(t:Table) RETURN b.natural_key, t.natural_key LIMIT 5;"
```

Expected: one row + one edge per NJ table seen.

---

## 8. Implementation Notes

- Added `upsert_table_pg`, `upsert_table_mongo`, `sync_table`, `sync_contains_table_edge`, and `IngestionSource` imports to `workers/ingestion/nj/apply.py`.
- Added `_PARENT_KIND_TO_LABEL` dict (restricted to `gatha_teeka_bhaavarth` and `kalash_bhaavarth` — the only parent kinds NJ tables carry).
- Fixed a latent bug in `apply_nj_shastra_payload`: `pg.get("shastras", [{}])[0]` raised `IndexError` when `shastras` was explicitly `[]`. Fixed to `pg.get("shastras") or [{}]`.
- Added `mongo:tables` and `neo4j:Table` as separate top-level entries in `_NJ_CONTRACTS` in `envelope.py` (previously only `postgres:tables` entry referenced them in `stores`).
- Tests in `tests/ingestion/test_apply_nj_tables.py` use a synthetic minimal envelope (no real HTML parsing needed) so they run without the NJ HTML fixture files.
- All 5 tests pass; full suite (1192 tests) passes with no regressions.

## 7. Done when

- NJ apply writes Table to all three stores with `table_type='index'`.
- `CONTAINS_TABLE` edge exists from the correct bhaavarth node.
- Idempotency tests green.
- `GET /v1/tables/{nk}` (already shipped) returns the NJ table including `table_type`.
- Hydration (`hydrate_tables_for_parent`) returns the table when called with the bhaavarth NK — no code change needed; the existing helper queries by `parent_natural_key`.
