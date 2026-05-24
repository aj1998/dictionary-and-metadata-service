# Dictionary & Metadata Service — Design Docs

A structured, knowledge-graph-backed retrieval layer for Jain texts. Companion to `cataloguesearch` (vector/BM25) and `cataloguesearch-chat` (LLM chat).

## Current State

| # | File | What you'll find |
|---|---|---|
|  | [Postgres data model](./data_model/data_model_postgres.md) | Full DDL, enums, indexes, migrations, idempotent upsert pattern |
|  | [Mongo data model](./data_model/03_data_model_mongo.md) | Per-type collections, JSON schemas, stable IDs |
|  | [Graph data model](./data_model/04_data_model_graph.md) | Neo4j labels, edge types, constraints, sync rules |
|  | [Metadata service API](./api/metadata/01_spec.md) | Authors / shastras / teekas / books / pravachans REST |
|  | [Data service API](./api/data/01_spec.md) | Keywords / gathas / topics / kalashas / browse / public search |
|  | [Navigation service API](./api/navigation/01_spec.md) | Neo4j graph navigation, alias writes, topic graph traversal |
|  | parser: [jainkosh](./data_sources/jainkosh/parser.md) | Orchestrator pipeline, fetch, alias mining |
|  | parser: [nikkyjain](./data_sources/nikkyjain/01_parser_nj.md) | Local-clone parser for shastras, gathas, anvayartha |
|  | [Query engine](./query_engine/00_overview.md) | Tokenize → normalize → resolve → traverse → rank  |
|  | [UI](/ui/README.md) | Common web app for exploring above services |
|  | [Deployment](./deployment.md) | docker-compose, nginx, env vars, backups, sizing |

## Key principles (recurring)

- **Postgres is the source of truth for IDs**. Mongo and Neo4j mirror.
- **`natural_key` everywhere**, so re-scrapes are idempotent overwrites.
- **Multilingual fields are arrays** of `{lang, script, text}` from day one.
- **NFC normalize all Devanagari** at every entry point.
- **Admin reviews everything** before public. No auto-publishing in v1.
