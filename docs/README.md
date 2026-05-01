# Dictionary & Metadata Service — Design Docs

A structured, knowledge-graph-backed retrieval layer for Jain texts. Companion to `cataloguesearch` (vector/BM25) and `cataloguesearch-chat` (LLM chat).

## Reading order

| # | File | What you'll find |
|---|---|---|
| 00 | [Overview](./00_overview.md) | Mission, services, stack, repo layout, data flow diagram |
| 01 | [Clarifications](./01_clarifications.md) | Verbatim Q&A; the *why* behind every decision |
| 02 | [Postgres data model](./02_data_model_postgres.md) | Full DDL, enums, indexes, migrations, idempotent upsert pattern |
| 03 | [Mongo data model](./03_data_model_mongo.md) | Per-type collections, JSON schemas, stable IDs |
| 04 | [Graph data model](./04_data_model_graph.md) | Neo4j labels, edge types, constraints, sync rules |
| 05 | [Metadata service API](./05_api_metadata_service.md) | Authors / shastras / teekas / books / pravachans REST |
| 06 | [Dictionary service API](./06_api_dictionary_service.md) | Keywords / gathas / topics / browse / public search |
| 07 | [Query service API](./07_api_query_service.md) | GraphRAG endpoint contract for cataloguesearch-chat |
| 08 | [Ingestion: jainkosh](./08_ingestion_jainkosh.md) | Parser config, scrape pipeline, alias mining |
| 09 | [Ingestion: nikkyjain](./09_ingestion_nikkyjain.md) | Local-clone parser for shastras, gathas, anvayartha |
| 10 | [Ingestion: vyakaran OCR](./10_ingestion_vyakaran_ocr.md) | Pluggable OCR scaffold (v1 stub) |
| 11 | [Chat enrichment loop](./11_chat_enrichment_loop.md) | Daily puller → admin review → graph merge |
| 12 | [Query engine](./12_query_engine.md) | Tokenize → normalize → resolve → traverse → rank |
| 13 | [Admin UI](./13_admin_ui.md) | Internal control plane — pages, endpoints, auth |
| 14 | [Public UI](./14_public_ui.md) | Hindi-first browse + search frontend |
| 15 | [Deployment](./15_deployment.md) | docker-compose, nginx, env vars, backups, sizing |
| 16 | [Testing & fixtures](./16_testing_and_fixtures.md) | Per-module test plans, goldens, e2e happy path |

## How to implement (suggested order, modular)

Each doc has a "Definition of Done" checklist — pick one and ship it. Recommended sequence so blocking dependencies resolve cleanly:

1. **Schemas first**: `02` → `03` → `04`.
2. **Core ingest**: `08` (jainkosh) and `09` (nikkyjain) in parallel.
3. **APIs**: `05` → `06`.
4. **Query path**: `12` → `07`.
5. **Enrichment loop**: `11`.
6. **UIs**: `14` then `13`.
7. **Deploy**: `15`.
8. **Tests + fixtures**: `16` (touched throughout, finalized last).

`10` (OCR) is a v2 stub and can be left until `vyakaran_vishleshan` rules are formalized.

## Key principles (recurring)

- **Postgres is the source of truth for IDs**. Mongo and Neo4j mirror.
- **`natural_key` everywhere**, so re-scrapes are idempotent overwrites.
- **Multilingual fields are arrays** of `{lang, script, text}` from day one.
- **NFC normalize all Devanagari** at every entry point.
- **v1 is graph-only + synonym dictionary**; embeddings are deferred to v2 with a clean swap point in `12_query_engine.md`.
- **Admin reviews everything** before public. No auto-publishing in v1.
