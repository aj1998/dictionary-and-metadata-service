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

---

### ✅ Completed: MongoDB data model (`docs/design/03_data_model_mongo.md`)

**Package**: `packages/jain_kb_common` — `jain_kb_common/db/mongo/`.

#### Layout

| File | Purpose |
|---|---|
| `__init__.py` | `get_mongo_client(url)` / `get_db(url, db_name)` factory (singleton `AsyncIOMotorClient`) |
| `collections.py` | Collection-name string constants (`GATHA_PRAKRIT`, `KEYWORD_DEFINITIONS`, …) |
| `schemas.py` | Pydantic v2 document models; `LangText.text` auto-NFC-normalizes on construction |
| `upserts.py` | `stable_id(natural_key)` + `upsert_*` helpers (one per collection) |
| `indexes.py` | `ensure_indexes(db)` — creates all indexes idempotently; call on service startup |

#### Collections implemented

| Collection | Pydantic model | Upsert helper |
|---|---|---|
| `gatha_prakrit` | `GathaPrakrit` | `upsert_gatha_prakrit` |
| `gatha_sanskrit` | `GathaSanskrit` | `upsert_gatha_sanskrit` |
| `gatha_hindi_chhand` | `GathaHindiChhand` | `upsert_gatha_hindi_chhand` |
| `gatha_word_meanings` | `GathaWordMeanings` | `upsert_gatha_word_meanings` |
| `teeka_gatha_mapping` | `TeekaGathaMapping` | `upsert_teeka_gatha_mapping` |
| `keyword_definitions` | `KeywordDefinition` | `upsert_keyword_definition` |
| `topic_extracts` | `TopicExtract` | `upsert_topic_extract` |
| `raw_html_snapshots` | `RawHtmlSnapshot` | `upsert_raw_html_snapshot` |
| `ocr_pages` | `OcrPage` | _(scaffolded — indexes only, no upsert yet)_ |

#### Key conventions

- **`stable_id(natural_key)`** — SHA-1 of the UTF-8 key, first 12 bytes → `ObjectId`. Same key always produces the same `_id`, so Postgres references survive re-scrapes.
- **`$setOnInsert: {created_at}`** — `created_at` is only written on the first insert; subsequent upserts leave it untouched while updating `updated_at`.
- **NFC normalization** — `LangText.text` field validator calls `unicodedata.normalize('NFC', v)` on every construction.
- **`ensure_indexes(db)`** is safe to call on every startup (Motor's `create_index` is idempotent). `topic_extracts` has a full-text index with `default_language: "none"` for Devanagari. `raw_html_snapshots` has a TTL index (365 days) on `fetched_at`.

#### Tests

```bash
# Offline (no DB required) — schema + stable_id tests
.venv/bin/python -m pytest tests/db/mongo/ -v

# With MongoDB running
MONGO_URL="mongodb://localhost:27017" \
  .venv/bin/python -m pytest tests/db/mongo/ -v
```

Without `MONGO_URL`, 8 round-trip tests skip gracefully; 5 offline tests always run.

See [`docs/manual_testing/mongo/testing.md`](docs/manual_testing/mongo/testing.md) for the full manual testing guide.

---

### ✅ Completed: Neo4j graph data model (`docs/design/04_data_model_graph.md`)

**Package**: `packages/jain_kb_common` — `jain_kb_common/db/neo4j/`.

#### Layout

| File | Purpose |
|---|---|
| `__init__.py` | `get_driver(url, user, password)` / `close_driver()` singleton factory (`AsyncGraphDatabase`) |
| `constraints.py` | `ensure_constraints(driver, database)` — creates 5 uniqueness constraints + 2 indexes; idempotent via `IF NOT EXISTS` |
| `upserts.py` | `sync_keyword`, `sync_topic`, `sync_shastra`, `sync_gatha` — idempotent MERGE-based upserts |
| `queries.py` | `resolve_token`, `traverse_topics`, `shortest_path` |
| `schema_check.py` | `validate_edge_type(name)` — rejects unknown edge types; reads `parser_configs/_meta/edge_types.yaml` |

#### Node labels implemented

`Keyword` · `Topic` · `Alias` · `Gatha` · `Shastra`

#### Edge types (`parser_configs/_meta/edge_types.yaml`)

`IS_A` · `PART_OF` · `RELATED_TO` · `ALIAS_OF` · `MENTIONS_KEYWORD` · `HAS_TOPIC` · `MENTIONS_TOPIC` · `IN_SHASTRA`

#### Key conventions

- **Cypher 25 compatible** — uses `coalesce(n.created_at, datetime())` instead of `ON CREATE SET` (Neo4j 2026 ships with `db.query.default_language=CYPHER_25`).
- **Idempotent MERGE** — every upsert uses `MERGE` with full `SET`; safe to re-run on the same data.
- **`ensure_constraints()`** — all constraints and indexes use `IF NOT EXISTS`; safe to call on every service startup.
- **Edge type validation** — `validate_edge_type(edge_type)` raises `UnknownEdgeTypeError` for any edge type not in `edge_types.yaml`. Add new types there; no code changes needed.
- **Driver factory** — `get_driver()` reads `NEO4J_URL`, `NEO4J_USER`, `NEO4J_PASSWORD` from environment; singleton pattern matches Motor/SQLAlchemy conventions.

#### Tests

```bash
# Neo4j tests only (requires Neo4j running)
export NEO4J_URL="bolt://localhost:7687"
export NEO4J_USER="neo4j"
export NEO4J_PASSWORD="jainkb_password"
python -m pytest tests/db/neo4j/ -v

# All tests (all three env vars set, 41 tests, 0 skipped)
export DATABASE_URL="postgresql+asyncpg://$(whoami)@localhost/jain_kb_test"
export MONGO_URL="mongodb://localhost:27017"
export NEO4J_URL="bolt://localhost:7687"
export NEO4J_USER="neo4j"
export NEO4J_PASSWORD="jainkb_password"
python -m pytest tests/ -v
```

See [`docs/manual_testing/neo4j/testing.md`](docs/manual_testing/neo4j/testing.md) for the full manual testing guide.

---

### ✅ Completed: JainKosh HTML Parser — parser-only stage (`docs/design/08_ingestion_jainkosh.md`)

**Package**: `workers/ingestion/jainkosh/` — pure HTML→JSON parser, no DB writes. Currently at **v1.2.0** (fix-spec-001 and fix-spec-002 applied; see `docs/design/jainkosh/parser_fix_spec_002/README.md`).

#### What it does

Reads pre-saved HTML from `samples/sample_html_jainkosh_pages/` and produces a `WouldWriteEnvelope` JSON showing exactly what each store (Postgres / Mongo / Neo4j) would receive on approval.

#### Modules

| File | Purpose |
|---|---|
| `config.py` | Pydantic models for `parser_configs/jainkosh.yaml` + YAML loader with JSON Schema validation |
| `models.py` | All Pydantic output types: `Block`, `Definition`, `Subsection`, `IndexRelation`, `PageSection`, `KeywordParseResult`, `WouldWriteEnvelope` |
| `normalize.py` | NFC, ZWJ/ZWNJ strip, whitespace collapse, URL decode |
| `topic_keys.py` | Devanagari-aware slugging, `natural_key()`, `parent_of()` |
| `selectors.py` | CSS class → block kind mapping |
| `parse_keyword.py` | Top-level entry: `parse_keyword_html(html, url, config)` |
| `parse_section.py` | Splits one h2-section into pre_heading / index_ols / body / tables |
| `parse_index.py` | Leading `<ol>/<ul>` index → `IndexRelation` list |
| `parse_subsections.py` | Heading detection (V1–V4) + subsection tree assembly via full DFS |
| `parse_blocks.py` | Block stream with translation marker absorption and nested-span flatten |
| `parse_definitions.py` | `siddhantkosh` (GRef-boundary) and `puraankosh` (p[id]) definitions |
| `refs.py` | GRef extraction (leading vs trailing); `strip_refs_from_text` (ref-strip pass) |
| `see_also.py` | Configurable-trigger देखें detection (inline + index); redlink prose-strip |
| `nav.py` | पूर्व पृष्ठ / अगला पृष्ठ detection and removal |
| `tables.py` | Table → `Block(kind="table", raw_html=…)`; `extraction_strategy` switch |
| `envelope.py` | Builds the `would_write` dict (Postgres rows, Mongo docs, Neo4j nodes/edges) |
| `cli.py` | `python -m workers.ingestion.jainkosh.cli parse <html> --out <json>` |

#### Key implementation notes (v1.2.0)

- **Heading variant DFS**: `walk_and_collect_headings` uses a full pre-order DFS. When a block-class element (e.g. `<li class="HindiText">`) contains a V1 heading (`<strong id="N">`) as a direct child, the DFS recurses into it rather than emitting it as a block. This was the critical fix needed for deep पर्याय subsection trees (43 subsections, 3 levels).

- **Full-DFS index scan**: `parse_index_relations` now does a flat `css("a")` scan over the entire `<ol>` subtree instead of a two-tier walk. Deeply nested `<ul>` देखें entries (e.g. द्रव्य's triple-nested relations) are now captured. Trigger list is configurable (`see_also_triggers: [देखें, विशेष देखें, …]`).

- **Ref-strip pass**: GRef text is stripped from `text_devanagari` after extraction into `references[]`. Orphan bracket pairs and double spaces are collapsed.

- **Sibling `=` translation marker**: bare `=` text nodes between sibling elements (e.g. inside `<li>`) pair a HindiText sibling as `hindi_translation` of the preceding source block — in addition to the existing HindiText-starts-with-`=` rule.

- **Label→synthetic topic**: `• <label> - देखें X` prose emits a `Subsection(label_topic_seed=True, topic_path=None)` as a child of the current subsection, alongside the `see_also` block. Scope-guarded so labels inside Hindi translation prose don't spawn spurious seeds (v1.2.0).

- **Idempotency contracts** (v1.2.0): hoisted to a single `would_write.idempotency_contracts` map keyed by `"<store>:<table>"` at the envelope root; per-row `idempotency_contract` field removed.

- **Table outerHTML + whitespace collapse** (v1.2.0): `Block(kind="table").raw_html` always carries full outerHTML; whitespace within all `raw_html` fields is collapsed.

- **IndexRelation source chain** (v1.2.0): `source_topic_path_chain` and `source_topic_natural_key_chain` are now reliably resolved via ancestor `<strong>` text lookup; previously returned `null` for some entries.

- **Parenthesised देखें cleanup** (v1.2.0): `(देखें X)` fragments stripped from prose text; un-parenthesised देखें text preserved.

- **See-also-only block drop** (v1.2.0): blocks whose entire content is `• X – देखें Y` are dropped from `Subsection.blocks` and represented only via `see_alsos`.

- **Definition (N) numbering strip** (v1.2.0): leading `(1)`, `(2)`, … prefixes stripped from PuranKosh definition prose; `definition_index` is the sole counter.

- **Redlink edge suppression** (v1.2.0): `RELATED_TO` edges with `target_exists=false` are not emitted in `would_write.neo4j.edges`.

- **selectolax `iter()` vs `css("*")`**: `iter()` returns only *direct children*; `css("*")` traverses all descendants. `contains_heading()` and `has_nested_block()` use `css("*")`; structural recursion uses `iter()`.

- **MediaWiki underscores**: `parse_anchor()` replaces `_` with space after URL-decoding (MediaWiki convention). `decode_keyword_from_url()` does not — the keyword URL itself uses Unicode directly.

#### Parse results (sample pages, v1.2.0)

| Page | SiddhantKosh defs | Index relations | Total subsections | Warnings |
|------|-------------------|-----------------|-------------------|---------|
| आत्मा | 4 | 0 | 7 | 0 |
| द्रव्य | 1 | 26 | 67 | 0 |
| पर्याय | 1 | 8 | 43 | 0 |

*(Counts unchanged from v1.1.0; envelope shape updated — see fix-spec-002.)*

#### Tests

```bash
# No DB required — pure Python parser
pip install selectolax PyYAML jsonschema pydantic
python -m pytest workers/ingestion/jainkosh/tests/ -v  # 129 tests, all pass
```

See [`docs/manual_testing/jainkosh_parser.md`](docs/manual_testing/jainkosh_parser.md) for the full manual testing guide.

---

### 🔜 Not yet started

Metadata-service API (`05`), dictionary-service API (`06`), ingestion workers (`08`, `09`), query engine (`12`), query-service API (`07`), enrichment loop (`11`), admin + public UIs (`13`, `14`), deployment (`15`).

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

# All tests (all env vars set — 41 tests, 0 skipped)
export DATABASE_URL="postgresql+asyncpg://$(whoami)@localhost/jain_kb_test"
export MONGO_URL="mongodb://localhost:27017"
export NEO4J_URL="bolt://localhost:7687"
export NEO4J_USER="neo4j"
export NEO4J_PASSWORD="jainkb_password"
python -m pytest tests/ -v
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
│       └── neo4j/testing.md
├── parser_configs/
│   └── _meta/
│       └── edge_types.yaml    # Canonical Neo4j edge type registry
├── packages/
│   └── jain_kb_common/        # Shared DB clients, models, upserts
│       └── jain_kb_common/db/
│           ├── postgres/      # SQLAlchemy models + upserts
│           ├── mongo/         # Motor client, Pydantic schemas, upserts, indexes
│           └── neo4j/         # AsyncDriver factory, constraints, upserts, queries, schema_check
├── migrations/                # Alembic (9 versions, 0001–0009)
├── tests/
│   └── db/
│       ├── postgres/
│       │   └── test_idempotent_upsert.py   # Postgres upsert tests
│       ├── mongo/
│       │   └── test_mongo_upsert.py    # MongoDB schema + upsert tests
│       └── neo4j/
│           └── test_neo4j_graph.py     # Neo4j constraints, upserts, queries, schema_check
├── services/                  # (future) metadata-, dictionary-, query-service
├── workers/                   # (future) ingestion + enrichment Celery workers
├── ui/                        # (future) Next.js public + admin apps
├── parser_configs/            # YAML/JSON scraper rules
├── samples/
│   ├── sample_html_granths_nj/    # Sample nikkyjain HTML for parser development
│   ├── sample_html_jainkosh_pages/# Sample JainKosh HTML for parser development
│   └── vyakaran_vishleshan/       # Scanned images for future OCR
├── alembic.ini
└── pyproject.toml
```

## Key conventions

- **`natural_key` everywhere** — re-scraping is an idempotent upsert, never a duplicate insert.
- **Postgres issues all UUIDs** — Mongo `_id` values are derived deterministically from `natural_key`; Neo4j nodes reference the same `natural_key`.
- **Multilingual fields are JSONB arrays** — shape `[{lang, script, text}]`, NFC-normalized Devanagari at every entry point.
- **Admin reviews everything** before public visibility — no auto-publishing in v1.
