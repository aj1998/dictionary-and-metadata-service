# Jain Dictionary & Knowledge Base Service

A structured, knowledge-graph-backed retrieval layer for Jain texts. Complements `cataloguesearch` (vector/BM25) and `cataloguesearch-chat` (LLM chat). Uses GraphRAG.

## Usecases/Objectives

- **Structured (knowledge retented) search engine** for Jain Texts expanded/enhanced on top of `JainKosh` authored by - _Kshullak Jinendra Varni Ji_ and the works done by scholars for creating its digital infrastructure at [jainkosh.org](www.jainkosh.org) by linking keywords with definitions/topics/shastras/references. Also, uses various shastras' OCRed data fed systematically and categorically.

- **Graph traversal** of Jain Knowledge Base in an interactive UI.

<p float="left">
  <img src="images/graph1.png" width="49%" />
  <img src="images/graph2.png" width="49%" />
</p>

- **Finding exact** sanskrit/prakrit/hindi gatha from shastras and understanding it word to word.

- Acts as a **cache and pre-querying dictionary** layer (finding exact keywords) to the existing vector search at cataloguesearch.

- **In depth answer generation** of questions on cataloguesearch-chat

- Structured or metadata based questions (like questions related on a specific gatha, adhyaya, specific topic mentions, translations of gatha verses etc.) For ex -
  - समयसार की गाथा ६ बताओ
  - समयसार की गाथा ६ की संस्कृत समझाओ
  - षट् द्रव्य के क्रियावान् व भाववान् विभाग का वर्णन कोन कोनसे शास्त्रों में आया है?

[Current vector search only extracts excerpts of gatha mentions in texts but does not have context of the gatha itself, what does it explain at an high level etc. This will extract high-level content and specific topics which are relevant to it, feed it to chat service, and then final answer generation will utilize both vectored RAG and vectorless/graphRAG results.]

- **Train a Jainism based AI model** in future with the help of Cataloguesearch OCRed data and this Knowledge Graph for the most accurate results.

## What this service does

- **Master Metadata** — authors, shastras, teekas, books, pravachans, anuyogas stored in PostgreSQL with stable UUIDs.
- **Dictionary** — gathas, kalashas (Prakrit/Sanskrit/Hindi), keyword definitions, topic extracts stored in MongoDB (long-form text) with index rows in PostgreSQL.
- **Knowledge Graph** — `keyword↔topic↔topic↔gathas↔teekas↔shastras↔pages` all kind of relations in Neo4j, enabling GraphRAG retrieval.
- **Ingestion pipeline** — scrapers for JainKosh and nikkyjain.github.io; an enrichment loop that pulls topic candidates from `cataloguesearch-chat`.
- **Admin + Public APIs** — FastAPI services for curating content and serving the public UI.

## Architecture

> See [`docs/design/00_overview.md`](docs/design/00_overview.md) for the full design reading order.

### Services

Four separate FastAPI apps, each a separate process/Dockerfile, sharing the `jain_kb_common` library:

| Service | Port | Role | Reads | Writes |
|---|---|---|---|---|
| `metadata-service` | 8001 | CRUD on authors / shastras / teekas / publications / books / pravachans | Postgres | Postgres |
| `data-service` | 8002 | Read API for gathas, keywords, topics, kalashas; browse and cross-entity search | Postgres + Mongo | Postgres (admin edits only) |
| `navigation-service` | 8003 | Neo4j graph navigation: alias resolution, topic neighbors, keyword↔topic links; alias and edge admin | Neo4j + Postgres | Neo4j + Postgres |
| `query-service` | 8004 | GraphRAG endpoint for `cataloguesearch-chat`: tokenize → resolve → graph-traverse → rank | Postgres + Mongo + Neo4j | Postgres (query_logs) |

### Data Stores

| Store | Engine | Use |
|---|---|---|
| Relational | **PostgreSQL 16** | Source of truth for all IDs; metadata, keyword/topic/gatha/kalasha index rows, ingestion runs, review queue, audit logs |
| Document | **MongoDB 7** | Long-form text: gathas, teeka commentary, keyword definitions, topic extracts, raw HTML snapshots, kalash content, future OCR pages |
| Graph | **Neo4j 5 Community** | Keyword & topic nodes + typed edges (`IS_A`, `PART_OF`, `RELATED_TO`, `ALIAS_OF`, `HAS_TOPIC`, `MENTIONS_KEYWORD`, `MENTIONS_TOPIC`, `IN_SHASTRA`, `IN_TEEKA`, `IN_PUBLICATION`, `CONTAINS_DEFINITION`) |
| Queue/cache | **Redis 7** | Celery broker, rate-limit buckets for scrapers, ephemeral parse-job state |

Postgres is the **source of truth for IDs**. Every entity in Mongo or Neo4j has a `natural_key` and a UUID issued by Postgres. The Neo4j graph mirrors Postgres — a full rebuild from Postgres + Mongo is always possible and safe.

### Tech Stack

- **Language**: Python 3.12, `.venv` virtualenv
- **Web**: FastAPI + Uvicorn, Pydantic v2
- **ORM**: SQLAlchemy 2 (async) + Alembic migrations
- **Mongo client**: Motor (async)
- **Neo4j client**: official `neo4j` driver (async)
- **Job queue**: Celery + Redis
- **Scraping**: `httpx` + `selectolax` (HTML), `trafilatura` fallback
- **Frontend** _(future)_: Next.js 14 (App Router) + Tailwind + `next-intl` (Hindi-first)
- **Deploy**: Docker Compose on a single VM

### Data Sources

| Source | Format | Frequency | Output |
|---|---|---|---|
| `jainkosh.org/wiki/Category:<letter>` | Live HTML (MediaWiki) | Manual trigger, batched per-letter | Keywords, definitions, initial topics |
| `nikkyjain.github.io` | Static HTML per shastra | Manual trigger, per shastra | Shastra metadata, gathas (Prakrit/Sanskrit/Hindi), word-meaning maps |
| `samples/vyakaran_vishleshan/<shastra>/*.png` | PNG scans | Future, manual | Word-by-word breakdowns per gatha |
| `cataloguesearch-chat` candidate topics DB | Read-only pull (cron) | Daily | `topic_candidates` rows for admin review |

### High-Level Data Flow

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

### Implementation Status

See [`IMPLEMENTATION_NOTES.md`](IMPLEMENTATION_NOTES.md) for full details on each completed component.

| Component | Status |
|---|---|
| Postgres data model + Alembic migrations (13 versions) | ✅ |
| MongoDB data model (15 collections, Motor async) | ✅ |
| Neo4j graph data model (constraints, upserts, queries) | ✅ |
| JainKosh HTML parser (`workers/ingestion/jainkosh/`) | ✅ |
| Phase 1 ingestion apply layer (`apply_approved_keyword_payload`) | ✅ |
| Metadata Service API (port 8001, 60 tests) | ✅ |
| Data Service API (port 8002, 60 tests) | ✅ |
| Navigation Service API (port 8003, 32 tests) | ✅ |
| Query Service API (port 8004, GraphRAG) | 🔜 |
| Ingestion workers (nikkyjain, vyakaran OCR) | 🔜 |
| Admin + Public UI (Next.js) | 🔜 |
| Deployment (Docker Compose) | 🔜 |


### JainKosh Parser —

The JainKosh HTML parser (`workers/ingestion/jainkosh/`) converts raw MediaWiki HTML into a `WouldWriteEnvelope` — a structured preview of exactly what each store (Postgres / Mongo / Neo4j) would receive on admin approval.

Results on sample keyword pages:

#### Summary
| Page   | SK defs | PK defs | Idx rels | Subsections | Keywords (int+ext) | Topics (int+ext) | Nodes | Edges | Refs (Res) | Warnings |
| ------ | ------- | ------- | -------- | ----------- | ------------------ | ---------------- | ----- | ----- | ---------- | -------- |
| आत्मा  | 4       | 2       | 0        | 7           | 2                  | 9                | 11    | 30    | 15         | 0        |
| द्रव्य | 1       | 1       | 26       | 59          | 9                  | 105              | 114   | 224   | 164        | 0        |
| पर्याय | 1       | 2       | 8        | 43          | 3                  | 56               | 59    | 152   | 114        | 0        |

#### Nodes
| Page   | Keyword (int) | Keyword (ext) | Topic (int) | Topic (ext) | Gatha (lazy) | GathaTeeka (lazy) | GathaTeekaBhaavarth (lazy) | Page (lazy) |
| ------ | ------------- | ------------- | ----------- | ----------- | ------------ | ----------------- | -------------------------- | ----------- |
| आत्मा  | 1             | 1             | 7           | 2           | 8            | 2                 | 0                          | 5           |
| द्रव्य | 1             | 8             | 85          | 20          | 30           | 16                | 10                         | 26          |
| पर्याय | 1             | 2             | 51          | 5           | 9            | 19                | 9                          | 20          |

#### Edges
| Page   | CONTAINS_DEFINITION | HAS_TOPIC | MENTIONS_TOPIC | PART_OF | RELATED_TO |
| ------ | ------------------- | --------- | -------------- | ------- | ---------- |
| आत्मा  | 7                   | 3         | 13             | 4       | 3          |
| द्रव्य | 0                   | 5         | 103            | 80      | 36         |
| पर्याय | 0                   | 3         | 93             | 48      | 8          |

To regenerate from latest goldens, run: `python scripts/golden_stats.py`

---
## Local setup

### Prerequisites
- Python 3.12
- PostgreSQL 16 (`brew install postgresql@16`)
- MongoDB 7 (`brew install mongodb-community@7.0`)
- Neo4j 5+ (`brew install neo4j`)
- `.venv` already created at repo root

### Install

```bash
# Activate venv
source .venv/bin/activate

# Install jain_kb_common + deps (SQLAlchemy, asyncpg, Pydantic, Motor, neo4j, pyyaml)
pip install -e packages/jain_kb_common

# Start services
brew services start postgresql@16
brew services start mongodb-community@7.0

# Neo4j needs a one-time password setup before first start
/opt/homebrew/opt/neo4j/bin/neo4j-admin dbms set-initial-password jainkb_password
/opt/homebrew/opt/neo4j/bin/neo4j start   # runs as foreground process; use brew services for background

# Create Postgres databases
psql postgres -c "CREATE DATABASE jain_kb_dev;"    # migrations / manual testing
psql postgres -c "CREATE DATABASE jain_kb_test;"   # automated tests
# MongoDB and Neo4j databases are created automatically on first write
```

### Run migrations (Postgres)

```bash
export DATABASE_URL="postgresql+asyncpg://$(whoami)@localhost/jain_kb_dev"
alembic upgrade head
```

### Run tests

```bash
# Postgres tests only
export DATABASE_URL="postgresql+asyncpg://$(whoami)@localhost/jain_kb_test"
python -m pytest tests/db/test_idempotent_upsert.py -v

# MongoDB tests only
export MONGO_URL="mongodb://localhost:27017"
python -m pytest tests/db/mongo/ -v

# Neo4j tests only
export NEO4J_URL="bolt://localhost:7687"
export NEO4J_USER="neo4j"
export NEO4J_PASSWORD="jainkb_password"
python -m pytest tests/db/neo4j/ -v

# All tests (all env vars set)
export DATABASE_URL="postgresql+asyncpg://$(whoami)@localhost/jain_kb_test"
export MONGO_URL="mongodb://localhost:27017"
export NEO4J_URL="bolt://localhost:7687"
export NEO4J_USER="neo4j"
export NEO4J_PASSWORD="jainkb_password"
python -m pytest tests/ -v

# Ingestion apply tests only
python -m pytest tests/ingestion/ -v

# Metadata service tests only (no Mongo/Neo4j required)
python -m pytest services/metadata_service/tests/ -v

# Data service tests only (MongoDB mocked, no real Mongo required)
python -m pytest services/data_service/tests/ -v

# Navigation service tests only (Neo4j mocked, no real Neo4j required)
export NEO4J_PASSWORD=jainkb_password
python -m pytest services/navigation_service/tests/ -v
```

---

## Repository layout

```
dictionary-and-metadata-service/
├── docs/
│   ├── design/                # Full design docs (00–16)
│   └── manual_testing/
│       ├── postgres/testing.md
│       ├── mongo/testing.md
│       ├── neo4j/testing.md
│       └── api/
│           ├── metadata/testing.md
│           ├── data/testing.md
│           └── navigation/testing.md
├── parser_configs/
│   └── _meta/
│       └── edge_types.yaml    # Canonical Neo4j edge type registry
├── packages/
│   └── jain_kb_common/        # Shared DB clients, models, upserts
│       └── jain_kb_common/db/
│           ├── postgres/      # SQLAlchemy models + upserts (incl. publications.py, kalashas.py)
│           ├── mongo/         # Motor client, Pydantic schemas, upserts, indexes (15 collections)
│           └── neo4j/         # AsyncDriver factory, constraints, upserts, queries, schema_check
├── migrations/                # Alembic (15 versions, 0001–0009 + 0010–0013 schema sync + Phase 1)
├── tests/
│   ├── db/
│   │   ├── postgres/
│   │   │   └── test_idempotent_upsert.py   # Postgres upsert tests
│   │   ├── mongo/
│   │   │   └── test_mongo_upsert.py    # MongoDB schema + upsert tests
│   │   └── neo4j/
│   │       └── test_neo4j_graph.py     # Neo4j constraints, upserts, queries, schema_check
│   └── ingestion/
│       └── test_apply.py               # apply_approved_keyword_payload integration tests
├── services/
│   ├── metadata_service/      # FastAPI metadata service (port 8001) — authors, shastras, teekas, publications, books, pravachans
│   ├── data_service/          # FastAPI data service (port 8002) — keywords, gathas, topics, kalashas, browse, search
│   └── navigation_service/    # FastAPI navigation service (port 8003) — Neo4j graph navigation, alias CRUD, topic edge admin
├── workers/
│   └── ingestion/
│       └── jainkosh/
│           ├── apply.py               # apply_approved_keyword_payload
│           └── tests/fixtures/        # HTML fixtures for parser + apply tests
├── ui/                        # (future) Next.js public + admin apps
├── parser_configs/            # YAML/JSON scraper rules
├── samples/
│   ├── sample_html_granths_nj/    # Sample nikkyjain HTML for parser development
│   ├── sample_html_jainkosh_pages/# Sample JainKosh HTML for parser development
│   └── vyakaran_vishleshan/       # Scanned images for future OCR
├── alembic.ini
└── pyproject.toml
```
