# Implementation status

### ✅ Completed: Postgres data model (`docs/design/data_model_postgres.md`)

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
| `topics.py` | `Topic` |
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
| `0006_gathas_topics_mentions.py` | `gathas`, `topics` , mentions removed|
| `0007_ingestion_ops.py` | `parser_configs`, `ingestion_runs`, `ingestion_review_queue` |
| `0008_chat_enrichment.py` | `topic_candidates`, `chat_puller_state` |
| `0009_query_logs.py` | `query_logs` |
| `0010_topics_hierarchy.py` | `topic_path`, `parent_topic_id`, `is_leaf`, `is_synthetic` columns + CHECK constraint on `topics` |
| `0011_publications.py` | `publications` table + `idx_publications_teeka` |
| `0012_kalashas.py` | `kalashas` table + `idx_kalashas_teeka` |

#### Upsert helpers (`jain_kb_common/db/postgres/upserts.py`)

`upsert_author`, `upsert_shastra`, `upsert_teeka`, `upsert_book`, `upsert_pravachan`, `upsert_keyword`, `upsert_topic`, `upsert_gatha`, `upsert_publication`, `upsert_kalash` — all idempotent via `ON CONFLICT (natural_key) DO UPDATE`.

#### Tests

```bash
# Run (requires PostgreSQL running locally)
DATABASE_URL="postgresql+asyncpg://$(whoami)@localhost/jain_kb_test" \
  .venv/bin/python -m pytest tests/ -v

# Without DATABASE_URL: 8 tests skip gracefully
.venv/bin/python -m pytest tests/ -v
```

See [`dev_docs/testing.md`](docs/manual_testing/db/postgres/testing.md) for the full manual testing guide.

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
| `gatha_teeka_sanskrit` | `GathaTeekaSanskrit` | `upsert_gatha_teeka_sanskrit` |
| `gatha_teeka_hindi` | `GathaTeekkaHindi` | `upsert_gatha_teeka_hindi` |
| `gatha_teeka_bhaavarth_hindi` | `GathaTeekaBhaavarth` | `upsert_gatha_teeka_bhaavarth_hindi` |
| `kalash_sanskrit` | `KalashSanskrit` | `upsert_kalash_sanskrit` |
| `kalash_hindi` | `KalashHindi` | `upsert_kalash_hindi` |
| `kalash_bhaavarth_hindi` | `KalashBhaavarth` | `upsert_kalash_bhaavarth_hindi` |

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

Without `MONGO_URL`, 8 round-trip tests skip gracefully; 6 offline tests always run.

See [`docs/manual_testing/mongo/testing.md`](docs/manual_testing/db/mongo/testing.md) for the full manual testing guide.

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

**Postgres-backed**: `Keyword` · `Topic` · `Alias` · `Gatha` · `Shastra` · `Teeka` · `Publication` · `Kalash`

**Graph-only (lazy MERGE)**: `GathaTeeka` · `GathaTeekaBhaavarth` · `KalashBhaavarth` · `Page`

#### Edge types (`parser_configs/_meta/edge_types.yaml`)

`IS_A` · `PART_OF` · `RELATED_TO` · `ALIAS_OF` · `MENTIONS_KEYWORD` · `HAS_TOPIC` · `MENTIONS_TOPIC` · `CONTAINS_DEFINITION` · `IN_SHASTRA` · `IN_TEEKA` · `IN_PUBLICATION`

#### Key conventions

- **Cypher 25 compatible** — uses `coalesce(n.created_at, datetime())` instead of `ON CREATE SET` (Neo4j 2026 ships with `db.query.default_language=CYPHER_25`).
- **Idempotent MERGE** — every upsert uses `MERGE` with full `SET`; safe to re-run on the same data.
- **`ensure_constraints()`** — all constraints and indexes use `IF NOT EXISTS`; safe to call on every service startup. Covers 7 uniqueness constraints + 3 `pg_id` lookup indexes for Postgres-backed node labels.
- **Edge type validation** — `validate_edge_type(edge_type)` raises `UnknownEdgeTypeError` for any edge type not in `edge_types.yaml`. Add new types there; no code changes needed.
- **Driver factory** — `get_driver()` reads `NEO4J_URL`, `NEO4J_USER`, `NEO4J_PASSWORD` from environment; singleton pattern matches Motor/SQLAlchemy conventions.
- **Lazy-node pattern** — `ensure_lazy_node` creates pure-graph nodes (`GathaTeeka`, `GathaTeekaBhaavarth`, `KalashBhaavarth`, `Page`) + their structural edge in one MERGE round trip; called by the envelope layer before emitting reference edges.
- **Structural edges excluded from traversal** — `IN_SHASTRA`, `IN_TEEKA`, `IN_PUBLICATION` carry `weight = 0.0` and are excluded from Stage 4 query patterns to prevent backbone noise in ranking.

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

See [`docs/manual_testing/neo4j/testing.md`](docs/manual_testing/db/neo4j/testing.md) for the full manual testing guide.

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

#### Tests

```bash
# No DB required — pure Python parser
pip install selectolax PyYAML jsonschema pydantic
python -m pytest workers/ingestion/jainkosh/tests/ -v
```

See [`docs/manual_testing/jainkosh_parser.md`](docs/manual_testing/parser/jainkosh_parser.md) for the full manual testing guide.

---

### ✅ Completed: Phase 1 — Schema deltas + apply-on-approve layer (`docs/design/ingestion/phase_1_schema_and_apply.md`)

**Package / module**: `workers/ingestion/jainkosh/apply.py`

#### What was added

| Area | Change |
|---|---|
| `topics.py` | 4 new columns: `topic_path`, `parent_topic_id`, `is_leaf`, `is_synthetic` + new indexes + CHECK constraint |
| `keywords.py` | `KeywordAlias` unique constraint fixed to `(keyword_id, alias_text)` |
| `upserts.py` | `upsert_topic` extended with 4 new kwargs; new `upsert_keyword_alias` helper |
| `mongo/schemas.py` | New types: `DefinitionItem`, `SubsectionTreeNode`, `IndexRelationItem`, `KeywordPageSection`; `KeywordDefinition` and `TopicExtract` updated |
| `mongo/indexes.py` | `topic_kw_path` and `parent_natural_key` indexes on `topic_extracts` |
| `neo4j/upserts.py` | `sync_topic` writes `topic_path` + `is_leaf`; new `sync_part_of_edge` and `sync_related_to_edge` |
| `migrations/` | `0013_keyword_alias_unique.py` — fixes unique constraint on `keyword_aliases` |
| `apply.py` | `apply_approved_keyword_payload(envelope, pg_session, mongo_db, neo4j_driver)` — idempotent, topological parent-first ordering, NFC normalization |

#### Tests

12 parametrized integration tests across 4 golden keywords (आत्मा, द्रव्य, पर्याय, वस्तु) × 3 test cases:

1. `test_apply_idempotent_full_envelope` — double-apply produces zero net DB changes
2. `test_apply_topics_parents_first` — every topic with a parent gets `parent_topic_id` populated
3. `test_apply_alias_dedup` — aliases don't grow on second apply

11 pass; 1 correctly skips (`वस्तु` has no sub-topics).

```bash
# Requires all three DB env vars
export DATABASE_URL="postgresql+asyncpg://$(whoami)@localhost/jain_kb_test"
export MONGO_URL="mongodb://localhost:27017"
export NEO4J_URL="bolt://localhost:7687"
export NEO4J_USER="neo4j"
export NEO4J_PASSWORD="jainkb_password"
python -m pytest tests/ingestion/ -v
```

See [`docs/manual_testing/jainkosh_ingestion.md`](docs/manual_testing/ingestion/jainkosh_ingestion.md) for the manual testing guide.

---

### ✅ Completed: Metadata Service API (`docs/design/api/metadata/01_spec.md`)

**Module**: `services/metadata_service/` — FastAPI service on port `8001`.

#### Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/healthz` | Health check |
| `GET` | `/v1/authors` | List authors (paginated) |
| `GET` | `/v1/authors/{id\|natural_key}` | Fetch author |
| `POST` | `/v1/admin/authors` | Create author |
| `PATCH` | `/v1/admin/authors/{id}` | Update author |
| `GET` | `/v1/shastras` | List shastras (filter: `?author_id=`, `?anuyoga=`, `?q=`) |
| `GET` | `/v1/shastras/{id\|natural_key}` | Fetch shastra with embedded author + anuyogas + stats |
| `GET` | `/v1/shastras/{id\|natural_key}/teekas` | List teekas for shastra |
| `POST` | `/v1/admin/shastras` | Create shastra |
| `PATCH` | `/v1/admin/shastras/{id}` | Update shastra |
| `GET` | `/v1/anuyogas` | List all four anuyogas |
| `GET` | `/v1/teekas` | List teekas (filter: `?shastra_id=`, `?teekakar_id=`) |
| `GET` | `/v1/teekas/{id\|natural_key}` | Fetch teeka with embedded shastra + teekakar + stats |
| `GET` | `/v1/teekas/{id\|natural_key}/publications` | List publications for teeka |
| `POST` | `/v1/admin/teekas` | Create teeka |
| `PATCH` | `/v1/admin/teekas/{id}` | Update teeka |
| `GET` | `/v1/publications` | List publications (filter: `?teeka_id=`, `?publisher_id=`) |
| `GET` | `/v1/publications/{id\|natural_key}` | Fetch publication |
| `POST` | `/v1/admin/publications` | Create publication |
| `PATCH` | `/v1/admin/publications/{id}` | Update publication |
| `GET` | `/v1/publishers` | List publishers (read-only from `publishers.json`) |
| `GET` | `/v1/books` | List books (filter: `?shastra_id=`, `?anuyoga=`) |
| `GET` | `/v1/books/{id\|natural_key}` | Fetch book with embedded shastra + anuyogas |
| `POST` | `/v1/admin/books` | Create book |
| `PATCH` | `/v1/admin/books/{id}` | Update book |
| `GET` | `/v1/pravachans` | List pravachans (filter: `?shastra_id=`, `?speaker_id=`) |
| `GET` | `/v1/pravachans/{id\|natural_key}` | Fetch pravachan with embedded shastra + speaker |
| `POST` | `/v1/admin/pravachans` | Create pravachan |
| `PATCH` | `/v1/admin/pravachans/{id}` | Update pravachan |
| `GET` | `/v1/admin/search` | Cross-entity pg_trgm fuzzy search |

All `GET` endpoints are unauthenticated. `POST`/`PATCH`/admin endpoints require HTTP Basic Auth (`ADMIN_USER` / `ADMIN_PASSWORD`).

#### Layout

```
services/metadata_service/
├── main.py          # FastAPI app, lifespan (publishers.json load), routers
├── config.py        # pydantic-settings: DATABASE_URL, ADMIN_USER, ADMIN_PASSWORD
├── deps.py          # get_session(), require_admin() (HTTP Basic)
├── routers/         # One router per resource
├── services/        # Business logic (SQLAlchemy async queries)
├── schemas/         # Pydantic request/response models
└── tests/           # 60 integration tests (httpx AsyncClient against real DB)
```

#### Run

```bash
export DATABASE_URL="postgresql+asyncpg://$(whoami)@localhost/jain_kb_dev"
export ADMIN_USER="admin"
export ADMIN_PASSWORD="secret"
uvicorn services.metadata_service.main:app --port 8001 --reload
```

OpenAPI docs auto-served at `http://localhost:8001/openapi.json`.

#### Tests

```bash
export DATABASE_URL="postgresql+asyncpg://$(whoami)@localhost/jain_kb_test"
export ADMIN_USER=admin
export ADMIN_PASSWORD=secret
python -m pytest services/metadata_service/tests/ -v
# 60 tests, 0 skipped — no Mongo/Neo4j required
```

---

### ✅ Completed: Data Service API (`docs/design/api/data/01_spec.md`)

**Module**: `services/data_service/` — FastAPI service on port `8002`.

#### Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/healthz` | Health check |
| `GET` | `/v1/keywords/letters` | Alphabet letter index with counts (cached 1h) |
| `GET` | `/v1/keywords` | List keywords (filter: `?q=`, `?letter=`) |
| `GET` | `/v1/keywords/{id\|natural_key}` | Keyword detail: Postgres row + aliases + Mongo definition |
| `PATCH` | `/v1/admin/keywords/{id}` | Correct `display_text` / `source_url` |
| `GET` | `/v1/topics` | List topics (filter: `?q=`, `?parent_keyword_id=`, `?source=`, `?is_leaf=`) |
| `GET` | `/v1/topics/{id\|natural_key}` | Topic detail: Postgres row + parent refs + Mongo extracts |
| `GET` | `/v1/gathas` | List gathas (filter: `?shastra_id=`, `?q=`) |
| `GET` | `/v1/gathas/{id\|natural_key}` | Gatha detail: core content always; teeka content gated behind `?include=` |
| `GET` | `/v1/kalashas` | List kalashas (filter: `?teeka_id=`) |
| `GET` | `/v1/kalashas/{id\|natural_key}` | Kalasha detail: all Mongo collections by default; selective via `?include=` |
| `GET` | `/v1/browse/shastras` | All shastras with gatha/teeka counts (cached 1h) |
| `GET` | `/v1/browse/shastras/{nk}/index` | Shastra ToC: gathas grouped by adhikaar |
| `GET` | `/v1/browse/teekas/{nk}/index` | Teeka ToC: gathas + kalashas interleaved |
| `GET` | `/v1/search` | Cross-entity pg_trgm search across keywords, topics, gathas, kalashas |

All `GET` endpoints are unauthenticated. `PATCH /v1/admin/keywords/{id}` requires HTTP Basic Auth. `Cache-Control: public, max-age=60` is set on every public `GET` response.

#### Gatha `include` param

| Value | Mongo collection fetched |
|---|---|
| `teeka_mapping` | `teeka_gatha_mapping` |
| `teeka_sanskrit` | `gatha_teeka_sanskrit` |
| `teeka_hindi` | `gatha_teeka_hindi` |
| `teeka_bhaavarth` | `gatha_teeka_bhaavarth_hindi` |

Fields not requested are **absent** from the response (not null). All included collections are fetched in a single `asyncio.gather` alongside core content.

#### Layout

```
services/data_service/
├── main.py          # FastAPI app, lifespan, routers
├── config.py        # pydantic-settings: DATABASE_URL, MONGO_URL, ADMIN_USER, ADMIN_PASSWORD
├── deps.py          # get_session(), get_mongo_db(), require_admin()
├── routers/         # keywords, topics, gathas, kalashas, browse, search
├── services/        # Business logic (SQLAlchemy async + Motor queries + asyncio.gather)
├── schemas/         # Pydantic request/response models
└── tests/           # 60 integration tests (httpx AsyncClient, Postgres real, MongoDB mocked)
```

#### Run

```bash
export DATABASE_URL="postgresql+asyncpg://$(whoami)@localhost/jain_kb_dev"
export MONGO_URL="mongodb://localhost:27017"
export ADMIN_USER="admin"
export ADMIN_PASSWORD="secret"
uvicorn services.data_service.main:app --port 8002 --reload
```

OpenAPI docs auto-served at `http://localhost:8002/openapi.json`.

#### Tests

```bash
export DATABASE_URL="postgresql+asyncpg://$(whoami)@localhost/jain_kb_test"
export ADMIN_USER=admin
export ADMIN_PASSWORD=secret
python -m pytest services/data_service/tests/ -v
# 60 tests, 0 skipped — MongoDB is mocked, no real Mongo required
```

See [`docs/manual_testing/api/data/testing.md`](docs/manual_testing/api/data/testing.md) for the full manual testing guide.

---

### ✅ Completed: Navigation Service API (`docs/design/api/navigation/01_spec.md`)

**Module**: `services/navigation_service/` — FastAPI service on port `8003`.

#### Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/healthz` | Health check with Neo4j node count (5-min cache) |
| `GET` | `/v1/keywords/{token}/resolve` | Keyword resolution: exact → alias → suffix-strip → none |
| `GET` | `/v1/keywords/{nk}/topics` | Topics reachable from a keyword via the graph |
| `GET` | `/v1/topics/{nk}/neighbors` | Topic neighborhood traversal (depth 1–3, configurable edge types) |
| `GET` | `/v1/topics/{nk}/keywords` | Keywords referenced by a topic (`MENTIONS_KEYWORD` edges) |
| `GET` | `/v1/graph/shortest_path` | Shortest path between two Topic nodes (max depth 6) |
| `POST` | `/v1/admin/keywords/{id}/aliases` | Add alias (Postgres + Neo4j ALIAS_OF edge) |
| `DELETE` | `/v1/admin/keywords/{id}/aliases/{alias_id}` | Remove alias (Postgres row + Neo4j Alias node if orphaned) |
| `POST` | `/v1/admin/topics/{nk}/edges` | Add semantic topic edge (IS_A / PART_OF / RELATED_TO) |
| `DELETE` | `/v1/admin/topics/{nk}/edges` | Remove semantic topic edge |
| `POST` | `/v1/admin/graph/resync` | Rebuild Neo4j graph from Postgres (`scope=full\|keyword\|topic\|shastra`) |
| `GET` | `/v1/admin/graph/stubs` | List stub nodes (paginated, label filter) |

All `GET` endpoints are unauthenticated. Admin writes require HTTP Basic Auth.

#### Key design choices

- **One Cypher round-trip per neighbor query** — UNION query handles outbound, inbound, and undirected (RELATED_TO) in a single call.
- **Stub filtering is Cypher-side** (`WHERE NOT coalesce(n.is_stub, false)`) — no unnecessary data fetched to Python.
- **Postgres alias writes commit before Neo4j writes** — retry of the same POST is idempotent (Neo4j MERGE).
- **Structural edge types (`IN_SHASTRA`, `IN_TEEKA`, `IN_PUBLICATION`) silently excluded** from public neighbor responses.
- **Full resync requires `X-Confirm: resync-full` header** — guards against accidental graph wipe.

#### Layout

```
services/navigation_service/
├── main.py          # FastAPI app, lifespan (Neo4j ping), 5-min node count cache
├── config.py        # pydantic-settings: DATABASE_URL, NEO4J_*, ADMIN_USER, ADMIN_PASSWORD
├── deps.py          # get_session(), get_neo4j_driver(), require_admin()
├── routers/         # keywords, topics, graph, admin
├── services/        # resolution (Postgres), traversal (Neo4j), aliases, edges, resync
├── schemas/         # resolution, neighbors, admin
└── tests/           # 32 integration tests (Postgres real, Neo4j mocked)
```

#### Run

```bash
export NEO4J_URL="bolt://localhost:7687"
export NEO4J_USER="neo4j"
export NEO4J_PASSWORD="jainkb_password"
export DATABASE_URL="postgresql+asyncpg://$(whoami)@localhost/jain_kb_dev"
export ADMIN_USER="admin"
export ADMIN_PASSWORD="secret"
uvicorn services.navigation_service.main:app --port 8003 --reload
```

#### Tests

```bash
export DATABASE_URL="postgresql+asyncpg://$(whoami)@localhost/jain_kb_test"
export ADMIN_USER=admin
export ADMIN_PASSWORD=secret
export NEO4J_PASSWORD=jainkb_password
python -m pytest services/navigation_service/tests/ -v
# 32 tests, 0 skipped — Neo4j is mocked, no live Neo4j required
```

See [`docs/manual_testing/api/navigation/testing.md`](docs/manual_testing/api/navigation/testing.md) for the full manual testing guide.

---

### ✅ Completed: Public UI (`docs/design/ui/`)

**Module**: `ui/` — Next.js 16 (App Router), Tailwind 4, `next-intl`, Zustand, D3-force.

See [`docs/ui/README.md`](ui/README.md) for the full developer wiki (directory layout, component catalogue, API wiring, test map, bug log).

#### Phases delivered

| Phase | Scope |
|---|---|
| 0 | Bootstrap: CSS token layer (30+ vars), Noto Serif Devanagari + Inter fonts, `next-intl` hi/en routing, Devanagari utils |
| 1 | Global shell: `TopBar`, `BreadcrumbBar`, `Footer`, 3 page shells (graph / content / reading), `Skeleton` |
| 2 | Atomic components: `BadgeChip`, `StatTile`, `ConnectedItemRow`, `PrimaryCTA`, `ListCards`, icon registry |
| 3 | API client layer: typed `apiFetch` + `ApiError`; clients for all 4 backend services; same-origin proxy via `next.config.ts` rewrites |
| 4 | Graph canvas: `NodeCard` (5 states), `RelationConnector` (cubic Bézier), `GraphCanvas` (dotted-grid, pan/zoom, D3 force sim), `ZoomControls`, `CategoryFilterList` |
| 5 | Graph interactivity: Zustand `useGraphStore`, URL ↔ state sync, `DetailsPanel` (node + edge mode), 300-node guard, SR-only nav tree |
| 6 | Content list pages: Home, Shastras, Dictionary index + letter listing, Topics browser, Search (ISR + dynamic) |
| 7 | Content detail pages: Shastra, Gatha (Shell C reader), Keyword, Topic; `GathaPanel`, `TaggedTermPopover`, `MiniGraphPreview` |
| 8 | About + Feedback (MongoDB write), full ARIA pass, focus ring, `prefers-reduced-motion` in force sim |
| Bugfixes | Node limit (MAX=20), graph stability on panel open, per-kind `getEntityDetail` dispatch, 404 silencing, disconnected node gravity |
| Vivaran fix | Keyword definition tree rendering, topic extract rendering, `DefinitionModal`, `PrimaryCTA` soft variant, footer clip |

#### Run

```bash
cd ui && pnpm install && pnpm dev   # http://localhost:3000
pnpm build                          # production build (0 errors, 0 warnings)
pnpm test                           # vitest — ~224 pure logic tests
```

---
### ✅ Completed: Query Service API — GraphRAG Engine (`docs/design/query_engine/`)

**Module**: `services/query_service/` — FastAPI service on port `8004`. Implements the full GraphRAG pipeline for `cataloguesearch-chat`: tokenise → resolve → graph-traverse → rank → hydrate.

Delivered across 6 phases. 91 tests pass (65 query-service + 26 hydration unit tests). Zero regressions across all other services.

#### Phases delivered

| Phase | Scope | Tests |
|---|---|---|
| 1 | `POST /v1/query/keyword_resolve_batch` — 4-pass resolution pipeline (exact, alias, suffix-strip, fuzzy trigram) + Mongo definition hydration | 5 test files |
| 2 | `POST /v1/query/topics_match` + `POST /v1/query/graphrag` — trigram topic search, Neo4j traversal, weighted-overlap ranking | 17 new API tests + 17 UI type/api tests |
| 3 | Fuzzy search on Metadata Service (`?q=&fuzzy=true`) for shastras, authors, teekas; GIN trigram indexes (migration 0017) | 24 new tests |
| 4 | `POST /v1/query/topics_in_shastra` + `POST /v1/query/shastras_for_topic`; GathaDetail shape audit; `page_numbers` gap documented | 14 new tests |
| 5 | Shared hydration helpers in `jain_kb_common/hydration/`; GraphRAG Mongo queries reduced from 2 to 1 | 26 new unit tests |
| 6 | `test_e2e.py` (11 round-trip tests), 9 env-configurable `QUERY_*` vars, 5 manual-testing docs | — |

#### Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/v1/query/keyword_resolve_batch` | Resolve up to 32 tokens via 4-pass pipeline; returns definitions from Mongo |
| `POST` | `/v1/query/topics_match` | Trigram search for topics; optional extract + reference hydration |
| `POST` | `/v1/query/graphrag` | Full GraphRAG: resolve tokens → traverse graph → rank topics → hydrate |
| `POST` | `/v1/query/topics_in_shastra` | Topics mentioned in a shastra (optionally narrowed to one gatha) |
| `POST` | `/v1/query/shastras_for_topic` | Shastras that mention a topic, with gatha list |

#### Resolution pipeline (`keyword_resolve_batch`)

| Pass | Method | DB |
|---|---|---|
| 1+2 | Exact `natural_key` + alias lookup (single CTE) | 1 Postgres |
| 3 | Suffix-strip retry (Hindi suffix list) | 1 Postgres (only if misses) |
| 4 | `pg_trgm` fuzzy similarity (default threshold 0.35) | 1 Postgres (only if still unresolved) |
| — | Definition hydration (`keyword_definitions` collection) | 1 Mongo |

Worst case: 3 Postgres + 1 Mongo per request.

#### Shared hydration package (`packages/jain_kb_common/jain_kb_common/hydration/`)

| Function | Purpose |
|---|---|
| `hydrate_definitions_hi(mongo_db, nks, cap)` | Fetch Hindi blocks from `keyword_definitions`; truncates at 1500 chars with `…` |
| `hydrate_topic_extracts_hi(mongo_db, nks, index_map, cap)` | Fetch Hindi blocks + inline references from `topic_extracts`; single Mongo query |
| `extract_references(blocks)` | Pure function; deduplicates `(shastra_nk, gatha_num, teeka_nk, page_num)` refs |

#### DB Migrations added

| Migration | Contents |
|---|---|
| `0015_keywords_natural_key_trgm_idx.py` | GIN trigram index on `keywords.natural_key` |
| `0016_topics_natural_key_trgm_idx.py` | GIN trigram index on `REPLACE(topics.natural_key,'/',' ')` expression |
| `0017_metadata_trgm_indexes.py` | GIN trigram indexes on `shastras`, `authors`, `teekas` |

#### Env variables

```
QUERY_KEYWORD_RESOLVE_MAX_TOKENS=32
QUERY_KEYWORD_FUZZY_MIN_SIM=0.35
QUERY_KEYWORD_FUZZY_TOP_K=5
QUERY_TOPICS_MATCH_DEFAULT_LIMIT=5
QUERY_TOPICS_MATCH_MIN_SIM=0.30
QUERY_GRAPHRAG_DEFAULT_LIMIT=5
QUERY_GRAPHRAG_DEFAULT_MAX_HOPS=2
QUERY_TOPICS_IN_SHASTRA_LIMIT=25
QUERY_SHASTRAS_FOR_TOPIC_LIMIT=10
```

#### Key deviations / gaps

- **`page_numbers` not in data model** — `Gatha` has no `page_number` column in Postgres or Mongo; documented in Phase 4, requires a new migration + backfill before production use.
- **`include_extracts` on `topics_in_shastra` not yet wired** — field accepted in schema but Mongo hydration not connected (deferred).
- **`gatha_number` vs `number` in Neo4j** — Phase 4 Cypher uses `g.number`; actual graph may use `g.gatha_number` (verify against live Neo4j before production).
- **`Shastra.name_hi` property** — used in `shastras_for_topic` Cypher; actual Neo4j property name must be confirmed against ingestion pipeline.

#### Run

```bash
export DATABASE_URL="postgresql+asyncpg://$(whoami)@localhost/jain_kb_dev"
export MONGO_URL="mongodb://localhost:27017"
export NEO4J_URL="bolt://localhost:7687"
export NEO4J_USER="neo4j"
export NEO4J_PASSWORD="jainkb_password"
uvicorn services.query_service.main:app --port 8004 --reload
```

#### Tests

```bash
export DATABASE_URL="postgresql+asyncpg://$(whoami)@localhost/jain_kb_test"
export ADMIN_USER=admin
export ADMIN_PASSWORD=secret
# Query-service tests (Neo4j + Mongo mocked; Postgres real)
python -m pytest services/query_service/tests/ -v
# Hydration unit tests (no DB required)
python -m pytest packages/jain_kb_common/tests/hydration/ -v
```

See [`docs/manual_testing/api/query/`](docs/manual_testing/api/query/) for curl examples and diagnostic SQL/Cypher for each endpoint.

---

### ✅ Completed: NikkYJain Ingestion Pipeline (`docs/design/data_sources/nikkyjain/`)

**Modules**: `workers/ingestion/nj/` — shastra-agnostic HTML parser + envelope builder + apply layer. Samaysar is the reference shastra; all other shastras use the same code with a new YAML config.

#### What it does

Reads per-file HTML from a local clone of `nikkyjain.github.io` and produces structured data across Postgres, MongoDB, and Neo4j. The pipeline is split into:

1. **Parser** (`orchestrator.py`, `parse_*.py`) — parses HTML → `ShastraParseResult` (Pydantic models)
2. **Envelope** (`envelope.py`) — `build_envelope()` produces a golden ingestion preview JSON with `postgres`, `mongo`, `neo4j`, and `idempotency_contracts` sections
3. **Apply** (`apply.py`) — `apply_nj_shastra_payload()` executes all DB writes idempotently
4. **CLI** (`cli.py`) — `python -m workers.ingestion.nj.cli parse` for golden generation

#### Parser modules

| File | Purpose |
|---|---|
| `orchestrator.py` | Top-level parse loop; sorts + classifies HTML files; tracks global kalash counter |
| `parse_myitem.py` | Regex-parses `myItem.js` → `GathaIndexEntry` maps (primary + secondary indexes) |
| `classify_pages.py` | `classify_page()` → `primary_gatha | secondary_kalash | skip`; `preceding_primary_gatha()` |
| `parse_page.py` | Per-file HTML parse: body fields + teeka routing + multi-gatha expansion |
| `parse_primary_teeka.py` | Structural extraction of primary teeka with kalashes (DarkSlateGray markers) |
| `parse_secondary_teeka.py` | Secondary teeka from `div#teeka1` or secondary-only pages |
| `html_to_markdown.py` | `node_to_markdown()` — HTML subtree → Markdown (bhaavarth conversion) |
| `models.py` | Pydantic extract models: `GathaExtract`, `KalashExtract`, `PrimaryTeeka`, `SecondaryTeeka`, etc. |
| `config.py` | YAML config loader for `parser_configs/nj/{shastra}.yaml` |
| `envelope.py` | `build_envelope()` — golden payload builder with natural key logic and neo4j graph |
| `apply.py` | `apply_nj_shastra_payload()` — idempotent tri-store writes |

#### Natural key conventions

All label segments in natural keys use Hindi words:

| Label | Hindi segment |
|---|---|
| Gatha | `:गाथा:` |
| Kalash | `:कलश:` |
| Teeka content | `:टीका:` |
| Bhaavarth | `:भावार्थ:` |
| Chapter | `:अध्याय:` |

Entity natural keys use Hindi names from config (`समयसार`, `कुन्दकुन्दाचार्य`, `अमृतचंद्राचार्य`). Teeka NKs use the **teeka title**, not the teekakar's name (`समयसार:आत्मख्याति`, not `समयसार:amritchandra`). Publisher ID for nikkyjain is numeric `"0"`. Leading zeros stripped from all numbers (`"001"` → `"1"`).

#### Postgres tables populated

`authors`, `shastras`, `teekas`, `publications`, `gathas`, `kalashas`, `teeka_chapters` (migration `0019_teeka_chapters.py`).

#### MongoDB collections populated

`gatha_prakrit`, `gatha_sanskrit`, `gatha_hindi_chhand`, `gatha_word_meanings`, `teeka_gatha_mapping` (primary only), `gatha_teeka_sanskrit`, `gatha_teeka_bhaavarth_hindi`, `kalash_sanskrit`, `kalash_hindi`, `kalash_word_meanings`.

#### Neo4j node labels

`Shastra`, `Teeka`, `Publication`, `Topic`, `Gatha`, `GathaTeeka`, `GathaTeekaBhaavarth`, `Kalash`, `KalashBhaavarth`.

#### Tests

```bash
# Unit tests (no DB required)
python -m pytest tests/workers/nj/ -v
# Expected: 72 passed

# Integration tests (require local nikkyjain clone)
export NIKKYJAIN_LOCAL_PATH="/path/to/nikkyjain.github.io"
python -m pytest tests/workers/nj/test_parse_page.py -v
```

Test files: `test_parse_myitem_unit.py`, `test_classify_pages_unit.py`, `test_parse_page_unit.py`, `test_parse_primary_teeka_unit.py`, `test_parse_secondary_teeka_unit.py`, `test_html_to_markdown_unit.py`, `test_orchestrator_unit.py`, `test_envelope.py`, `test_apply_unit.py`, `test_parse_page.py` (guarded integration).

See `docs/wiki/nj_parser.md` and `docs/wiki/nj_ingestion.md` for full agent-ready context.

#### Known open items

- `ingest_nj_apply.py` end-to-end apply script: specified in `02_ingestion_nj.md §5`, partially wired. Verify before production run.
- Cross-source Gatha NK: JK parser must adopt `गाथा` label to align with NJ's `समयसार:गाथा:8` for cross-source Neo4j MERGE.
- DB integration tests: unit-only; live DB tests deferred under `--run-db-tests` flag.

---

## Key conventions

- **`natural_key` everywhere** — re-scraping is an idempotent upsert, never a duplicate insert.
- **Postgres issues all UUIDs** — Mongo `_id` values are derived deterministically from `natural_key`; Neo4j nodes reference the same `natural_key`.
- **Multilingual fields are JSONB arrays** — shape `[{lang, script, text}]`, NFC-normalized Devanagari at every entry point.
- **Admin reviews everything** before public visibility — no auto-publishing in v1.