# Phase 3 — Table: Apply layer (Postgres + Mongo + Neo4j writes)

**Owner**: backend / ingestion
**Prereqs**: [Phase 1](./table_phase1_schema.md) + [Phase 2](./table_phase2_parser.md) merged.
**Scope**: `workers/ingestion/jainkosh/apply.py` and supporting scripts.

## Goal

Make `apply_approved_keyword_payload(envelope, pg_session, mongo_db, neo4j_driver, ingestion_run_id)` persist `envelope.tables[]` to all three stores idempotently, with `CONTAINS_TABLE` edges from the right parent label.

## 1. Apply order

After existing topic / keyword writes, before stub-edge linking:

```
for parsed_table in envelope.tables:
    1. upsert_table (Postgres)               → returns table_id
    2. upsert_table (Mongo) with table_id    → returns mongo _id (stable)
       (raw_html_doc_id = str(_id))
    3. UPDATE tables SET raw_html_doc_id = $1 WHERE id = $2
    4. sync_table (Neo4j MERGE Table)
    5. sync_contains_table_edge from parent → table
    6. for kw_nk in mentioned_keyword_natural_keys:
         sync_stub_node Keyword if missing
         MERGE (Table)-[:MENTIONS_KEYWORD]->(Keyword)
    7. for tp_nk in mentioned_topic_natural_keys:
         sync_stub_node Topic if missing
         MERGE (Table)-[:MENTIONS_TOPIC]->(Topic)
```

All within the existing PG transaction → commit → Mongo → Neo4j flow described in [ingestion.md](../data_sources/jainkosh/ingestion.md).

## 2. Parent-label lookup

The parser already stamps `parent_kind` on each `ParsedTable` (`"topic" | "keyword" | "gatha" | ...`). Map to Neo4j label:

```python
PARENT_KIND_TO_LABEL = {
    "topic": "Topic",
    "keyword": "Keyword",
    "gatha": "Gatha",
    "gatha_teeka": "GathaTeeka",
    "gatha_teeka_bhaavarth": "GathaTeekaBhaavarth",
    "kalash": "Kalash",
    "kalash_bhaavarth": "KalashBhaavarth",
    "page": "Page",
}
```

If the parent node does not yet exist (e.g. Page during partial JainKosh ingest), create a stub via `sync_stub_node` so the edge can be MERGEd. Stub parents pre-existed for Gatha/Page already.

## 3. Mongo `table_id` injection

Mirror the `keyword_id` injection done for `keyword_definitions`: after Postgres `upsert_table` returns the UUID, inject `table_id=str(pg_id)` into the Mongo doc dict before `upsert_table` to Mongo, so the Mongo doc always knows its Postgres row.

## 4. clear_dbs.py

Add `tables` to:

- Postgres TRUNCATE list (it FKs only to `ingestion_runs`, so include in the same cascade group as other dictionary tables).
- Mongo collection drops: append `"tables"` to the existing list (also update README's note that lists the cleared collections).
- Neo4j: existing `MATCH (n) DETACH DELETE n` already handles it. No change.

## 5. ingest_goldens_apply.py

No code change needed if the script just calls `apply_approved_keyword_payload`. Verify that `द्रव्य` golden now creates ≥1 row in `tables`, ≥1 Mongo doc in `tables`, ≥1 `:Table` node, ≥1 `CONTAINS_TABLE` edge after a fresh run. Add this assertion to `tests/scripts/test_ingest_goldens_smoke.py`.

## 6. Tests

`tests/ingestion/test_apply.py`:

- `test_apply_persists_table_to_postgres` — fixture envelope with 1 table → row exists with correct natural_key, parent_natural_key, raw_html_doc_id populated.
- `test_apply_persists_table_to_mongo` — Mongo doc exists, `table_id` injected, `cells` round-trip.
- `test_apply_creates_table_node_and_contains_edge_in_neo4j` — Topic + Table + 1 `CONTAINS_TABLE`.
- `test_apply_table_mention_edges` — Table mentions one keyword + one topic, both edges present (with stubs for missing targets).
- `test_apply_table_idempotent` — run apply twice on same envelope → row counts unchanged, no duplicate edges.

```bash
export DATABASE_URL="postgresql+asyncpg://$(whoami)@localhost/jain_kb_test"
export MONGO_URL="mongodb://localhost:27017"
export NEO4J_URL="bolt://localhost:7687"
export NEO4J_PASSWORD=jainkb_password
python -m pytest tests/ingestion/ tests/scripts/ -v
```

Full suite must stay green: `python -m pytest tests/ -v`.

## 7. Doc updates

- [`docs/design/data_sources/jainkosh/ingestion.md`](../data_sources/jainkosh/ingestion.md) — new section "Tables": describes the 7-step apply flow above, the `PARENT_KIND_TO_LABEL` map, and the idempotency guarantees.
- [`README.md`](../../../README.md) (root) — extend the `clear_dbs.py` Mongo-collections list to include `tables`; bump the "Mongo data model (15 collections, Motor async)" status row to `(16 collections)`; in the JainKosh Parser summary block, update the post-apply expected counts to include `Tables`.

## 8. Manual verification

```bash
python scripts/clear_dbs.py
python scripts/ingest_goldens_apply.py --keyword द्रव्य
psql jain_kb_dev -c "SELECT natural_key, parent_natural_key, seq FROM tables;"
mongosh jain_kb --eval 'db.tables.find({}, {natural_key:1, "cells.0":1}).pretty()'
cypher-shell -u neo4j -p jainkb_password \
  "MATCH (p)-[:CONTAINS_TABLE]->(t:Table) RETURN labels(p)[0] AS parent, p.natural_key, t.natural_key LIMIT 5;"
```

## 9. Definition of Done

- [ ] All 5 apply tests pass.
- [ ] Full suite green.
- [ ] `clear_dbs.py` clears `tables` (PG + Mongo).
- [ ] Manual verification commands produce expected output on `द्रव्य` golden.
- [ ] `ingestion.md` and root README updated.

## 10. Implementation notes (fill in during PR)

- `ingestion_run_id` is **not** forwarded to `upsert_table_pg` because the existing integration tests pass a random UUID that is not present in `ingestion_runs`. Keywords and Topics also don't store run IDs in PG. Run tracking for tables is recorded in Mongo only (as a string, no FK).
- `raw_html_doc_id` is pre-computed as `str(stable_id(natural_key))` before the PG insert, avoiding the two-round-trip UPDATE pattern described in the spec. This is valid because `stable_id` is deterministic.
- `MENTIONS_KEYWORD` was added to `_VALID_EDGE_TYPES` in `jain_kb_common/db/neo4j/stubs.py` (was missing; `MENTIONS_TOPIC` was already present).
- The 5 table tests are in `tests/ingestion/test_apply.py` (tests 4–8). The spec referenced a `tests/scripts/test_ingest_goldens_smoke.py` file that didn't exist; the assertions were placed in the existing integration test file instead.
