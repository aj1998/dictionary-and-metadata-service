# 00 — Dictionary & Metadata Service: Overview

## Mission

Build a structured, knowledge-graph-backed retrieval service for Jain texts that complements the existing vector/BM25 retriever (`cataloguesearch`) and the LLM chat layer (`cataloguesearch-chat`). It owns:

- **Master Metadata** — authors, shastras, teekas, publications, books, pravachans, anuyogas (in Postgres).
- **Dictionary content** — gathas (Prakrit/Sanskrit/Hindi), kalashas, word-to-meaning maps, keyword definitions, topic extracts (in MongoDB).
- **Topic Knowledge Graph** — keyword↔topic↔topic relations, alias edges, structural containment edges (in Neo4j).

It exposes:

1. A **public read API** for the UI (browse shastras, look up keywords, read gathas, explore topics).
2. A **graph navigation API** for graph-based UI navigation and as the resolution layer for the query service.
3. A **GraphRAG query API** consumed by `cataloguesearch-chat` to enrich vector hits with structured topic context.
4. An **admin API + UI** for triggering ingestion, reviewing parsed extracts, curating synonyms, and approving AI-generated topic candidates.

## Four Deployable Services

| Service | Port | Purpose | Reads | Writes |
|---|---|---|---|---|
| `metadata-service` | 8001 | CRUD/queries on shastras, authors, teekas, publications, books, pravachans | Postgres | Postgres |
| `data-service` | 8002 | Read API for gathas, keywords, topics, kalashas; browse and search | Postgres + Mongo | Postgres (admin keyword edits only) |
| `navigation-service` | 8003 | Neo4j graph navigation: alias resolution, topic neighbors, topic↔keyword links; graph admin (alias CRUD, edge CRUD, resync) | Neo4j + Postgres | Neo4j + Postgres |
| `query-service` | 8004 | GraphRAG endpoint for `cataloguesearch-chat`: token → keyword resolve → graph traverse → rank → hydrate | Postgres + Mongo + Neo4j | Postgres (query_logs) |

Each service is a separate FastAPI app, separate Dockerfile, separate process. They share library code via `jain_kb_common` (DB clients, models, normalization).

## Data Stores

| Store | Engine | Use |
|---|---|---|
| Relational | **PostgreSQL 16** | Metadata, parser configs, ingestion runs, candidate topics, review queue, audit logs, keyword/topic/gatha/kalasha index rows |
| Document  | **MongoDB 7** | Long-form text extracts (gathas, teeka commentary, keyword definitions, topic extracts, raw HTML snapshots, kalash content, future OCR pages) |
| Graph     | **Neo4j 5 Community** | Keyword & topic nodes + typed edges (IS_A, PART_OF, RELATED_TO, ALIAS_OF, HAS_TOPIC, MENTIONS_KEYWORD, MENTIONS_TOPIC, IN_SHASTRA, IN_TEEKA, IN_PUBLICATION, CONTAINS_DEFINITION) |
| Queue/cache | **Redis 7** | Celery broker, rate-limit buckets for scrapers, ephemeral parse-job state |

Postgres is the **source of truth for IDs**. Every entity in Mongo or Neo4j has a `natural_key` and a UUID issued by Postgres. The Neo4j graph mirrors Postgres — full rebuild from Postgres + Mongo is always possible and safe.

## Tech Stack

- **Language**: Python 3.12 (.venv virtualenv)
- **Web**: FastAPI + Uvicorn, Pydantic v2 models
- **ORM**: SQLAlchemy 2 (async) + Alembic (migrations)
- **Mongo client**: Motor (async)
- **Neo4j client**: official `neo4j` driver (async)
- **Job queue**: Celery + Redis
- **Scraping**: `httpx` + `selectolax` (HTML), `trafilatura` for fallback text extraction
- **OCR (future)**: pluggable; first integration target is Tesseract (`pytesseract`) with Hindi + Sanskrit traineddata
- **Frontend**: Next.js 14 (App Router) + Tailwind + `next-intl` (Hindi-first, EN later)
- **Deploy**: Docker Compose on a single VM (vertical-scale only for now)

## High-Level Data Flow

```
                        ┌─────────────────┐
                        │  Admin UI       │
                        │ (Next.js)       │
                        └──────┬──────────┘
                               │ trigger ingest, review queues, curate graph
                               ▼
┌─────────┐ scrape  ┌──────────────────────────────────────┐
│jainkosh │◄────────│  ingestion workers (Celery)          │
└─────────┘         │  - jainkosh parser + apply           │
┌─────────┐ scrape  │  - gatha parser (nj/cataloguesearch) │
│nj(local)│◄────────│  - vyakaran OCR (future)             │
│ CS OCRs │         │                                      │
│         │         │  enrichment workers (Celery)         │
│         │         │  - chat-candidate puller (cron)      │
└─────────┘         └────┬──────────┬──────────┬───────────┘
                         ▼          ▼          ▼
                   ┌─────────┐ ┌────────┐ ┌─────────┐
                   │Postgres │ │ Mongo  │ │ Neo4j   │
                   └────┬────┘ └───┬────┘ └────┬────┘
                        │          │            │
              ┌─────────┴──┐  ┌────┴──────┐ ┌──┴──────────────┐
              │metadata-svc│  │data-svc   │ │navigation-svc   │
              │ (port 8001)│  │(port 8002)│ │(port 8003)      │
              └─────────┬──┘  └────┬──────┘ └──┬──────────────┘
                        │          │            │
                        │          └─────┬──────┘
                        │                │
                        ▼                ▼
                   Public UI          query-svc
                (metadata browse)    (port 8004)
                                        │
                                        ▼
                                cataloguesearch-chat
```

## Repository Layout

```
dictionary-and-metadata-service/
├── docs/
│   ├── design/
│   │   ├── 00_overview.md            ← this file
│   │   ├── 01_clarifications.md
│   │   ├── 02_data_model_postgres.md
│   │   ├── 03_data_model_mongo.md
│   │   ├── 04_data_model_graph.md
│   │   ├── 07_api_query_service.md
│   │   ├── 08_ingestion_jainkosh.md
│   │   ├── 09_ingestion_nikkyjain.md
│   │   ├── 10_ingestion_vyakaran_ocr.md
│   │   ├── 11_chat_enrichment_loop.md
│   │   ├── 12_query_engine.md
│   │   ├── 13_admin_ui.md
│   │   ├── 14_public_ui.md
│   │   ├── 15_deployment.md
│   │   ├── 16_testing_and_fixtures.md
│   │   ├── api/
│   │   │   ├── metadata/01_spec.md   ✅ implemented
│   │   │   ├── data/01_spec.md       ← data service spec
│   │   │   └── navigation/01_spec.md ← navigation service spec
│   │   ├── ingestion/
│   │   │   ├── phase_1_schema_and_apply.md
│   │   │   └── phase_1b_neo4j_stub_nodes.md
│   │   ├── jainkosh/
│   │   └── updates/                  ← retroactive corrections
│   └── manual_testing/
├── parser_configs/
│   ├── jainkosh.yaml
│   └── _meta/
│       └── edge_types.yaml
├── services/
│   ├── metadata_service/             ✅ implemented
│   ├── data_service/                 🔜 to implement
│   ├── navigation_service/           🔜 to implement
│   └── query_service/                🔜 to implement (future)
├── workers/
│   ├── ingestion/
│   │   └── jainkosh/
│   └── enrichment/
├── packages/
│   └── jain_kb_common/
├── migrations/
├── ui/
├── docker-compose.yml
├── pyproject.toml
└── README.md
```

## Sources We Ingest

| Source | Format | Frequency | Output |
|---|---|---|---|
| `jainkosh.org/wiki/Category:<letter>` then per-keyword pages | Live HTML (MediaWiki) | Manual trigger, batched per-letter | Keyword + Definitions + initial Topics |
| `nikkyjain.github.io` (local clone) | Static HTML per shastra | Manual trigger, per shastra | Shastra metadata + Gathas (Prakrit/Sanskrit/Hindi) + word-meaning maps |
| `samples/vyakaran_vishleshan/<shastra>/*.png` | PNG scans | Future, manual | Word-by-word breakdowns per gatha |
| (**enrichment**) `cataloguesearch-chat` candidate topics DB | Read-only pull (cron) | Daily | `topic_candidates` rows for admin review |

## Out of Scope

- Training a Jainism LLM
- Mobile apps
- Owning OCR of the cataloguesearch corpus (we only OCR `vyakaran_vishleshan` here)
- User accounts and auth (public read; admin protected by basic auth or IP allowlist for v1)

## Reading Order for Implementers

1. `01_clarifications.md` — captured Q&A, the *why* behind decisions. ✅
2. `02_data_model_postgres.md` → `03_data_model_mongo.md` → `04_data_model_graph.md` — schemas first. ✅ implemented.
3. `08_ingestion_jainkosh.md` and `09_ingestion_nikkyjain.md` — fill the stores. [_Partially Implemented_]
4. `api/metadata/01_spec.md` — metadata service. ✅ implemented.
5. `api/data/01_spec.md` — data service (gathas, keywords, topics, kalashas, browse). ✅ implemented.
6. `api/navigation/01_spec.md` — navigation service (Neo4j graph navigation, alias writes). ✅ implemented.
7. `12_query_engine.md` then `07_api_query_service.md` — GraphRAG pipeline (future).
8. `11_chat_enrichment_loop.md` — incremental graph growth.
9. `13_admin_ui.md` and `14_public_ui.md`.
10. `15_deployment.md`, `16_testing_and_fixtures.md`.
