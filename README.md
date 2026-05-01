# Dictionary & Metadata Service

A structured, knowledge-graph-backed retrieval layer for Jain texts. Complements `cataloguesearch` (vector/BM25) and `cataloguesearch-chat` (LLM chat).

## What this service does

- **Master Metadata** — authors, shastras, teekas, books, pravachans, anuyogas stored in PostgreSQL with stable UUIDs.
- **Dictionary** — gathas (Prakrit/Sanskrit/Hindi), keyword definitions, keyword↔topic mappings stored in MongoDB (long-form text) with index rows in PostgreSQL.
- **Knowledge Graph** — keyword↔topic↔topic relations in Neo4j, enabling GraphRAG retrieval.
- **Ingestion pipeline** — scrapers for JainKosh and nikkyjain.github.io; an enrichment loop that pulls topic candidates from `cataloguesearch-chat`.
- **Admin + Public APIs** — FastAPI services for curating content and serving the public UI.

## Architecture

Three separate FastAPI services sharing `jain_kb_common`:

| Service | Role |
|---|---|
| `metadata-service` | CRUD on authors / shastras / teekas / books / pravachans |
| `dictionary-service` | CRUD on gathas / keywords / topics + definition lookups |
| `query-service` | GraphRAG endpoint: tokenize → resolve → graph-traverse → rank |

Data stores: **PostgreSQL 16** (source of truth for IDs) · **MongoDB 7** (long-form text) · **Neo4j 5** (graph) · **Redis 7** (Celery broker).

See [`docs/design/00_overview.md`](docs/design/00_overview.md) for the full architecture diagram and reading order.

---

## Implementation status

### ✅ Completed: Postgres data model (`docs/design/02_data_model_postgres.md`)

**Package**: `packages/jain_kb_common` — shared Python library installed as `jain-kb-common`.

#### SQLAlchemy models (`jain_kb_common/db/postgres/`)

| File | Models |
|---|---|
| `authors.py` | `Author` |
| `shastras.py` | `Shastra`, `ShastrasAnuyoga` |
| `anuyogas.py` | `Anuyoga` |
| `teekas.py` | `Teeka` |
| `books.py` | `Book`, `BookAnuyoga` |
| `pravachans.py` | `Pravachan` |
| `keywords.py` | `Keyword`, `KeywordAlias` |
| `gathas.py` | `Gatha` |
| `topics.py` | `Topic`, `TopicMention` |
| `ingestion.py` | `ParserConfig`, `IngestionRun`, `IngestionReviewQueue` |
| `enrichment.py` | `TopicCandidate`, `ChatPullerState` |
| `query_logs.py` | `QueryLog` |

All models use SQLAlchemy 2 `Mapped`/`mapped_column` style with `JSONB` and `UUID(as_uuid=True)`. Enums are declared in `enums.py` as Python `str, enum.Enum` with matching `SAEnum` instances.

#### Alembic migrations (`migrations/versions/`)

| Migration | Contents |
|---|---|
| `0001_setup.py` | Extensions (pgcrypto, pg_trgm, btree_gin), enums, `set_updated_at()` trigger |
| `0002_seed_anuyogas.py` | Four anuyoga rows with Hindi + English multilingual labels |
| `0003_authors_shastras.py` | `authors`, `shastras`, `anuyogas`, `shastra_anuyogas` |
| `0004_teekas_books_pravachans.py` | `teekas`, `books`, `book_anuyogas`, `pravachans` |
| `0005_keywords_aliases.py` | `keywords`, `keyword_aliases` (GIN + trgm indexes) |
| `0006_gathas_topics_mentions.py` | `gathas`, `topics`, `topic_mentions` (GIN jsonb_path_ops indexes, CHECK constraint) |
| `0007_ingestion_ops.py` | `parser_configs`, `ingestion_runs`, `ingestion_review_queue` |
| `0008_chat_enrichment.py` | `topic_candidates`, `chat_puller_state` |
| `0009_query_logs.py` | `query_logs` |

#### Upsert helpers (`jain_kb_common/db/postgres/upserts.py`)

`upsert_author`, `upsert_shastra`, `upsert_teeka`, `upsert_book`, `upsert_pravachan`, `upsert_keyword`, `upsert_topic`, `upsert_gatha` — all idempotent via `ON CONFLICT (natural_key) DO UPDATE`.

#### Tests

```bash
# Run (requires PostgreSQL running locally)
DATABASE_URL="postgresql+asyncpg://$(whoami)@localhost/jain_kb_test" \
  .venv/bin/python -m pytest tests/ -v

# Without DATABASE_URL: 8 tests skip gracefully
.venv/bin/python -m pytest tests/ -v
```

See [`dev_docs/testing.md`](docs/manual_testing/postgres/testing.md) for the full manual testing guide.

### 🔜 Not yet started

MongoDB data model (`03`), Neo4j graph model (`04`), metadata-service API (`05`), dictionary-service API (`06`), ingestion workers (`08`, `09`), query engine (`12`), query-service API (`07`), enrichment loop (`11`), admin + public UIs (`13`, `14`), deployment (`15`).

---

## Local setup

### Prerequisites
- Python 3.12
- PostgreSQL 16 (`brew install postgresql@16`)
- `.venv` already created at repo root

### Install

```bash
# Activate venv
source .venv/bin/activate

# Install jain_kb_common + deps
pip install -e packages/jain_kb_common

# Create databases
brew services start postgresql@16
psql postgres -c "CREATE DATABASE jain_kb_dev;"    # migrations / manual testing
psql postgres -c "CREATE DATABASE jain_kb_test;"   # automated tests
```

### Run migrations

```bash
export DATABASE_URL="postgresql+asyncpg://$(whoami)@localhost/jain_kb_dev"
alembic upgrade head
```

### Run tests

```bash
export DATABASE_URL="postgresql+asyncpg://$(whoami)@localhost/jain_kb_test"
python -m pytest tests/ -v
```

---

## Repository layout

```
dictionary-and-metadata-service/
├── docs/design/               # Full design docs (00–16)
├── dev_docs/                  # Developer notes and testing guides
├── packages/
│   └── jain_kb_common/        # Shared DB clients, models, upserts
│       └── jain_kb_common/db/postgres/
├── migrations/                # Alembic (9 versions, 0001–0009)
├── tests/
│   └── db/
│       └── test_idempotent_upsert.py
├── services/                  # (future) metadata-, dictionary-, query-service
├── workers/                   # (future) ingestion + enrichment Celery workers
├── ui/                        # (future) Next.js public + admin apps
├── parser_configs/            # YAML/JSON scraper rules
├── samples
│   └── sample_html_granths_nj/    # Sample nikkyjain HTML for parser development
│   └── sample_html_jainkosh_pages/# Sample JainKosh HTML for parser development
│   └── vyakaran_vishleshan/       # Scanned images for future OCR
├── alembic.ini
└── pyproject.toml
```

## Key conventions

- **`natural_key` everywhere** — re-scraping is an idempotent upsert, never a duplicate insert.
- **Postgres issues all UUIDs** — Mongo `_id` values are derived deterministically from `natural_key`; Neo4j nodes reference the same `natural_key`.
- **Multilingual fields are JSONB arrays** — shape `[{lang, script, text}]`, NFC-normalized Devanagari at every entry point.
- **Admin reviews everything** before public visibility — no auto-publishing in v1.
