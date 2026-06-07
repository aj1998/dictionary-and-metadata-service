# Objects — First-class Entity Specs

Phase-wise specs for new first-class entities added to the Jain Knowledge Base. Each entity gets its own subdirectory under this folder (or a numbered file) with phase docs that an implementing agent can carry out in a single context window per phase.

## Tables — `table_*.md`

Add `Table` as a first-class node, ingested initially from JainKosh and rendered in a UI modal. A Table is an HTML table that appears under a Topic / Keyword / Gatha / GathaTeeka / GathaTeekaBhaavarth / Kalash / KalashBhaavarth / Page in the source, captured as `raw_html` plus a parsed cell-matrix and caption, mirrored into Postgres (`tables` index row), Mongo (`tables` collection), and Neo4j (`Table` node with `CONTAINS_TABLE` incoming edges and optional outgoing `MENTIONS_KEYWORD` / `MENTIONS_TOPIC` edges).

Phases:

1. [Phase 1 — Schema](./table_phase1_schema.md) — Postgres `tables` table + Alembic migration, Mongo `tables` collection + Pydantic schema + indexes, Neo4j `Table` label + constraints + `CONTAINS_TABLE` edge type, edge-type registry update. Update parent data-model docs ([02 Postgres](../data_model/data_model_postgres.md), [03 Mongo](../data_model/data_model_mongo.md), [04 Neo4j](../data_model/data_model_graph.md)) and the [main README](../../../README.md) (Architecture > Data Stores table).
2. [Phase 2 — JainKosh Parser](./table_phase2_parser.md) — emit a parallel `Table` node from each `Block(kind="table")` while keeping the inline block for back-compat; extract caption + 2D cell matrix + mentioned keyword/topic naturalKeys from the table HTML; wire into `WouldWriteEnvelope`; refresh goldens. Update [JainKosh parser doc](../data_sources/jainkosh/parser.md).
3. [Phase 3 — Apply layer](./table_phase3_apply.md) — extend `apply_approved_keyword_payload` to upsert Tables (PG row → Mongo doc → Neo4j node + edges); add `clear_dbs.py` cleanup; refresh `ingest_goldens_apply.py` smoke output. Update [JainKosh ingestion doc](../data_sources/jainkosh/ingestion.md).
4. [Phase 4 — API + hydration](./table_phase4_api.md) — `core-service` data domain endpoint `GET /v1/tables/{natural_key}`; `navigation` graph traversal includes the `table` EntityKind; hydration helper `hydrate_table` for graph payloads; query-service exposes tables on topic/keyword detail responses. Update [API docs index](../api/README.md).
5. [Phase 5 — UI](./table_phase5_ui.md) — `TableModal` (Base UI Dialog, mirrors `DefinitionModal`); `table` EntityKind + swatch/icon in graph filters and node renderer; "Tables" section on topic / keyword / gatha / reader pages that opens the modal; types in `lib/types.ts`; API client in `lib/api/data.ts`. Update [UI README](../../../ui/README.md) (§5 Design System, §8 Component Catalogue, §10 Graph Page, §12 Content Pages).

### Cross-cutting conventions

- `natural_key` format: `table:<source>:<parent_natural_key>:<seq>` (e.g. `table:jainkosh:द्रव्य:षट्द्रव्य-विभाजन:द्रव्य-के-या-वस्तु-के-एक-दो-आदि-भेदों-की-अपेक्षा-विभाग:01`). `seq` is 1-indexed per parent in source order.
- Mongo `_id = stable_id(natural_key)` (same SHA1 pattern as other collections).
- Source enum: tables reuse the existing `ingestion_source` values; no new enum needed.
- Edges: `(Parent)-[:CONTAINS_TABLE]->(Table)` where `Parent` ∈ `{Topic, Keyword, Gatha, GathaTeeka, GathaTeekaBhaavarth, Kalash, KalashBhaavarth, Page}`. Tables may also have outgoing `MENTIONS_KEYWORD` / `MENTIONS_TOPIC` edges (parsed from `<a>` tags inside the raw HTML, like `topic_extracts` do today).
- EntityKind in UI: `table` (joins existing `keyword | topic | gatha | teeka | bhaavarth | kalash | page`).
- No admin review queue for v1: tables flow through the existing `apply_approved_keyword_payload` like every other JainKosh block.
- Initial source scope: JainKosh only. NJ + Vyakaran-OCR + flowchart-scanner are deferred (a future doc under this folder will spec them when picked up).
