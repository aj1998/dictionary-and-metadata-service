# 00 — Dictionary & Metadata Service: Overview

## Mission

Build a structured, knowledge-graph-backed retrieval service for Jain texts that complements the existing vector/BM25 retriever (`cataloguesearch`) and the LLM chat layer (`cataloguesearch-chat`). It owns:

- **Master Metadata** — authors, shastras, teekas, books, pravachans, anuyogas (in Postgres).
- **Dictionary content** — gathas (Prakrit/Sanskrit/Hindi), word-to-meaning maps, keyword definitions, topic extracts (in MongoDB).
- **Topic Knowledge Graph** — keyword↔topic↔topic relations, used for graph-based retrieval (in Neo4j).

It exposes:

1. A **public read API** for the UI (browse shastras, look up keywords, explore topics).
2. A **GraphRAG query API** consumed by `cataloguesearch-chat` to enrich vector hits with structured topic context.
3. An **admin API + UI** for triggering ingestion, reviewing parsed extracts, curating synonyms, and approving AI-generated topic candidates.

## Three Deployable Services

| Service | Purpose | Reads | Writes |
|---|---|---|---|
| `metadata-service` | CRUD/queries on shastras, authors, teekas, books, pravachans | Postgres | Postgres |
| `dictionary-service` | CRUD/queries on gathas, keywords, topics, definitions | Postgres + Mongo + Neo4j | Mongo, Neo4j (graph nodes for keywords/topics) |
| `query-service` | GraphRAG endpoint, tokenize→normalize→graph-traverse→rank | Postgres + Mongo + Neo4j | (read only; logs to Postgres) |

Each service is a separate FastAPI app, separate Dockerfile, separate process. They share library code via a Python package `jain_kb_common` (DB clients, models, normalization).

## Data Stores

| Store | Engine | Use |
|---|---|---|
| Relational | **PostgreSQL 16** | Metadata, parser configs, ingestion runs, candidate topics, review queue, audit logs |
| Document  | **MongoDB 7** | Long-form text extracts (gathas, teeka commentary, keyword definitions, topic extracts, raw HTML snapshots, future OCR pages) |
| Graph     | **Neo4j 5 Community** | Keyword & topic nodes + typed edges (IS_A, PART_OF, RELATED_TO, ALIAS_OF, MENTIONS) |
| Queue/cache | **Redis 7** | Celery broker, rate-limit buckets for scrapers, ephemeral parse-job state |

Postgres is the **source of truth for IDs**. Every entity in Mongo or Neo4j has a `natural_key` and a UUID issued by Postgres (or generated client-side as `uuid.uuid4()` and persisted in Postgres on the same write).

## Tech Stack

- **Language**: Python 3.12
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
                               │ trigger ingest, review queues
                               ▼
┌─────────┐ scrape  ┌──────────────────────────────────────┐
│jainkosh │◄────────│  ingestion workers (Celery)          │
└─────────┘         │  - jainkosh parser                   │
┌─────────┐ read    │  - nikkyjain parser                  │
│nikkyjain│◄────────│  - vyakaran OCR (future)             │
│ (local) │         │  - chat-candidate puller (cron)      │
└─────────┘         └────┬──────────┬──────────┬───────────┘
                         ▼          ▼          ▼
                   ┌─────────┐ ┌────────┐ ┌─────────┐
                   │Postgres │ │ Mongo  │ │ Neo4j   │
                   └────┬────┘ └───┬────┘ └────┬────┘
                        │          │           │
                ┌───────┴──────────┴───────────┴─────────┐
                │  metadata-svc  dictionary-svc  query-svc│
                └────┬─────────────────┬──────────────┬───┘
                     │                 │              │
                     ▼                 ▼              ▼
                 Public UI          Public UI    cataloguesearch-chat
              (shastra browse)  (dictionary)    (GraphRAG context)
```

## Repository Layout

```
dictionary-and-metadata-service/
├── docs/                          # This documentation set
├── parser_configs/                # YAML/JSON parser rules (versioned)
│   ├── jainkosh.yaml
│   ├── nikkyjain/
│   │   ├── pravachansaar.yaml
│   │   └── samaysaar.yaml
│   └── vyakaran_vishleshan/       # future
├── services/
│   ├── metadata_service/
│   ├── dictionary_service/
│   └── query_service/
├── workers/
│   ├── ingestion/
│   │   ├── jainkosh.py
│   │   ├── nikkyjain.py
│   │   └── vyakaran_ocr.py
│   └── enrichment/
│       └── chat_candidate_puller.py
├── packages/
│   └── jain_kb_common/            # shared DB clients, models, normalization
├── migrations/                    # alembic
├── ui/
│   ├── public/                    # Next.js public app
│   └── admin/                     # Next.js admin app (or sub-route)
├── docker-compose.yml
├── pyproject.toml
└── README.md
```

## Sources We Ingest

| Source | Format | Frequency | Output |
|---|---|---|---|
| `jainkosh.org/wiki/Category:<letter>` then per-keyword pages | Live HTML (MediaWiki) | Manual trigger, batched per-letter | Keyword + Definitions + initial Topics |
| `nikkyjain.github.io` (local clone) | Static HTML per shastra | Manual trigger, per shastra | Shastra metadata + Gathas (Prakrit/Sanskrit/Hindi) + word-meaning maps |
| `vyakaran_vishleshan/<shastra>/*.png` | PNG scans (rules in `rules/`) | Future, manual | Word-by-word breakdowns per gatha |
| `cataloguesearch-chat` candidate topics DB | Read-only pull (cron) | Daily | `topic_candidates` rows for admin review |

## Out of Scope

- Training a Jainism LLM
- Mobile apps
- Owning OCR of the cataloguesearch corpus (we only OCR `vyakaran_vishleshan` here)
- User accounts and auth (public read; admin protected by basic auth or IP allowlist for v1)

## Reading Order for Implementers

1. `01_clarifications.md` — captured Q&A, the *why* behind decisions.
2. `02_data_model_postgres.md` → `03_data_model_mongo.md` → `04_data_model_graph.md` — schemas first.
3. `08_ingestion_jainkosh.md` and `09_ingestion_nikkyjain.md` — fill the stores.
4. `05_api_metadata_service.md` → `06_api_dictionary_service.md` — expose the data.
5. `12_query_engine.md` then `07_api_query_service.md` — wire up GraphRAG.
6. `11_chat_enrichment_loop.md` — incremental graph growth.
7. `13_admin_ui.md` and `14_public_ui.md`.
8. `15_deployment.md`, `16_testing_and_fixtures.md`.
