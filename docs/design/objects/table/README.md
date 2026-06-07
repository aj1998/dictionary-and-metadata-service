# Table — Complete Wiki

`Table` is a first-class entity in the Jain Knowledge Base. This document is the single reference for any agent working with tables — schema, parsing, ingestion, API, and UI.

---

## Table of Contents

1. [Overview](#1-overview)
2. [Natural Key Format](#2-natural-key-format)
3. [Data Layer — Postgres](#3-data-layer--postgres)
4. [Data Layer — MongoDB](#4-data-layer--mongodb)
5. [Data Layer — Neo4j](#5-data-layer--neo4j)
6. [Parser — JainKosh](#6-parser--jainkosh)
7. [Apply Layer — Ingestion](#7-apply-layer--ingestion)
8. [API Endpoints](#8-api-endpoints)
9. [Hydration](#9-hydration)
10. [UI Components](#10-ui-components)
11. [Graph Integration](#11-graph-integration)
12. [i18n Strings](#12-i18n-strings)
13. [Testing](#13-testing)
14. [Manual Verification](#14-manual-verification)
15. [Key Files Reference](#15-key-files-reference)
16. [Phase History](#16-phase-history)

---

## 1. Overview

A `Table` is an HTML table that appears inside a Topic / Keyword / Gatha / GathaTeeka / GathaTeekaBhaavarth / Kalash / KalashBhaavarth / Page node in JainKosh. Each table is:

- Stored as a raw HTML string **plus** a parsed 2D cell matrix.
- Persisted in all three stores: Postgres (index row), MongoDB (full doc with `raw_html` + `cells`), Neo4j (`Table` node with edges).
- Exposed via HTTP: `GET /v1/tables/{natural_key}` and `GET /v1/tables?parent_natural_key=...`.
- Rendered in the UI inside a `TableModal` — from `cells`, never from `raw_html` (security).

**Source scope**: JainKosh only for the initial implementation. NJ, Vyakaran-OCR, and flowchart-scanner are deferred.

**Review queue**: None for v1. Tables flow through `apply_approved_keyword_payload` like every other JainKosh block.

---

## 2. Natural Key Format

```
table:<source>:<parent_natural_key>:<seq:02d>
```

- `source` is always `jainkosh` currently.
- `seq` is 1-indexed per parent, in DOM source order.
- `parent_natural_key` is the full naturalKey of the owning node (may itself contain colons).

Examples:
```
table:jainkosh:द्रव्य:षट्द्रव्य-विभाजन:द्रव्य-के-या-वस्तु-के-एक-दो-आदि-भेदों-की-अपेक्षा-विभाग:01
table:jainkosh:आत्मा:02
```

---

## 3. Data Layer — Postgres

**File**: `packages/jain_kb_common/jain_kb_common/db/postgres/tables.py`  
**Migration**: `migrations/0020_tables.py`

### Schema

```sql
CREATE TABLE tables (
  id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  natural_key            TEXT NOT NULL UNIQUE,
  source                 ingestion_source NOT NULL,
  parent_natural_key     TEXT NOT NULL,
  parent_kind            TEXT NOT NULL,   -- 'topic'|'keyword'|'gatha'|'gatha_teeka'|'gatha_teeka_bhaavarth'|'kalash'|'kalash_bhaavarth'|'page'
  seq                    INT  NOT NULL,
  caption                JSONB,           -- [{lang, script, text}]
  source_url             TEXT,
  raw_html_doc_id        TEXT NOT NULL,   -- Mongo tables._id (stable SHA1)
  graph_node_id          TEXT,            -- = natural_key
  ingestion_run_id       UUID REFERENCES ingestion_runs(id) ON DELETE SET NULL,
  created_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (parent_natural_key, seq)
);

CREATE INDEX idx_tables_parent ON tables(parent_natural_key);
CREATE INDEX idx_tables_source ON tables(source);
CREATE INDEX idx_tables_run    ON tables(ingestion_run_id);
```

### Upsert function

```python
upsert_table(session, *, natural_key, source, parent_natural_key, parent_kind,
             seq, caption, source_url, raw_html_doc_id, ingestion_run_id) -> uuid.UUID
```

Uses `ON CONFLICT (natural_key) DO UPDATE SET ... RETURNING id`. `raw_html_doc_id` is pre-computed as `str(stable_id(natural_key))` before insert (deterministic — no two-round-trip pattern needed).

**Note**: `ingestion_run_id` is not forwarded at apply time (test compatibility). Run tracking lives in MongoDB only.

---

## 4. Data Layer — MongoDB

**Collection constant**: `TABLES = "tables"` in `db/mongo/collections.py`  
**Schema**: `TableDoc` in `packages/jain_kb_common/jain_kb_common/db/mongo/schemas.py`

```python
class TableDoc(BaseModel):
    natural_key: str
    table_id: str | None           # Postgres tables.id (injected at apply time)
    source: str
    parent_natural_key: str
    parent_kind: str
    seq: int
    source_url: str | None
    caption: list[LangText] = []
    raw_html: str
    cells: list[list[str]] = []    # parsed 2D matrix, NFC-normalized, '' for missing cells
    header_rows: int = 0           # number of leading <th>-header rows
    mentioned_keyword_natural_keys: list[str] = []
    mentioned_topic_natural_keys: list[str] = []
    plaintext: str | None = None   # whitespace-normalized cell concatenation, for text search
    ingestion_run_id: str | None = None
    parser_version: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
```

`_id = stable_id(natural_key)` (SHA1 — same pattern as all other collections).

### Indexes

```python
await db[TABLES].create_index("natural_key", unique=True)
await db[TABLES].create_index([("parent_natural_key", 1), ("seq", 1)])
await db[TABLES].create_index("ingestion_run_id")
await db[TABLES].create_index([("plaintext", "text"), ("caption.text", "text")], default_language="none")
```

### Upsert

```python
async def upsert_table(db, *, natural_key: str, doc: dict) -> ObjectId
```

Standard `$set` / `$setOnInsert` pattern. Lookups are by `natural_key` field (not `_id` ObjectId) for consistency.

---

## 5. Data Layer — Neo4j

**Constraints file**: `packages/jain_kb_common/jain_kb_common/db/neo4j/constraints.py`  
**Upserts file**: `packages/jain_kb_common/jain_kb_common/db/neo4j/upserts.py`

### Node label: `Table`

Stored properties (lightweight — heavy fields stay in Mongo):

| Property | Type | Notes |
|---|---|---|
| `natural_key` | string | Unique identifier |
| `pg_id` | string | Postgres `tables.id` |
| `source` | string | e.g. `jainkosh` |
| `parent_natural_key` | string | Owning node's naturalKey |
| `parent_kind` | string | e.g. `topic` |
| `seq` | int | 1-indexed within parent |
| `caption_hi` | string | Hindi caption text for display |
| `is_stub` | bool | Always `false` for JainKosh tables |
| `created_at` | datetime | |
| `updated_at` | datetime | |

### Constraints and indexes

```cypher
CREATE CONSTRAINT table_natural_key IF NOT EXISTS FOR (n:Table) REQUIRE n.natural_key IS UNIQUE;
CREATE INDEX table_pg_id IF NOT EXISTS FOR (n:Table) ON (n.pg_id);
CREATE INDEX table_is_stub IF NOT EXISTS FOR (n:Table) ON (n.is_stub);
CREATE INDEX table_parent IF NOT EXISTS FOR (n:Table) ON (n.parent_natural_key);
```

### Edges

| Edge type | From | To | Notes |
|---|---|---|---|
| `CONTAINS_TABLE` | Topic, Keyword, Gatha, GathaTeeka, GathaTeekaBhaavarth, Kalash, KalashBhaavarth, Page | Table | Primary containment edge |
| `MENTIONS_KEYWORD` | Table | Keyword | Parsed from `<a>` tags in raw HTML |
| `MENTIONS_TOPIC` | Table | Topic | Parsed from `<a>` tags in raw HTML |

`CONTAINS_TABLE` is registered in `parser_configs/_meta/edge_types.yaml`.

### Upsert functions

```python
sync_table(neo4j, pg_table_row)                           # MERGE Table node
sync_contains_table_edge(neo4j, *, parent_label, parent_nk, table_nk, source)
```

`"Table"` is included in `_VALID_LABELS`. `MENTIONS_KEYWORD` is included in `_VALID_EDGE_TYPES` in `stubs.py`.

### Useful Cypher query

```cypher
MATCH (t:Topic {natural_key:$nk})-[:CONTAINS_TABLE]->(tbl:Table)
RETURN tbl.natural_key, tbl.seq, tbl.caption_hi ORDER BY tbl.seq;
```

---

## 6. Parser — JainKosh

**File**: `workers/ingestion/jainkosh/tables.py`  
**Model additions**: `workers/ingestion/jainkosh/models.py`

### ParsedTable model

```python
class ParsedTable(BaseModel):
    natural_key: str
    seq: int
    parent_natural_key: str
    parent_kind: Literal["topic", "keyword", "gatha", "gatha_teeka",
                          "gatha_teeka_bhaavarth", "kalash",
                          "kalash_bhaavarth", "page"]
    source_url: str | None = None
    caption: list[LangText] = []
    raw_html: str
    cells: list[list[str]] = []
    header_rows: int = 0
    plaintext: str = ""
    mentioned_keyword_natural_keys: list[str] = []
    mentioned_topic_natural_keys: list[str] = []
```

`WouldWriteEnvelope` has a `tables: list[ParsedTable] = []` field.

### Parsing logic (`parse_table_block`)

Signature: `parse_table_block(...) -> tuple[Block, ParsedTable]`

Returns **both** the inline `Block(kind="table", raw_html=...)` for back-compat AND a first-class `ParsedTable`.

Steps:
1. **raw_html**: existing `_clean_raw_html()` output.
2. **cells**: walk `<tr>`/`<td>`/`<th>`. Each cell = `HTMLParser(cell.html).text(strip=True)`, NFC-normalized. `<br>` → `\n`. Pad short rows with `''` (rectangular matrix).
3. **header_rows**: count leading rows where all cells are `<th>`.
4. **caption**: prefer `<caption>` tag; else use `preceding_heading`. Format: `[{lang:"hin", script:"Deva", text:...}]`.
5. **plaintext**: `" ".join(cell for row in cells for cell in row if cell)`.
6. **mentioned_***: walk `<a>` tags — `/wiki/<keyword>` → keyword naturalKey; `#<anchor>` → topic anchor string (resolved to full naturalKey at apply time via the topic tree).
7. **naturalKey**: `f"table:{source}:{parent_natural_key}:{seq:02d}"`.

### Config flag

In `workers/ingestion/jainkosh/config.py`:

```python
class TableExtractionConfig(BaseModel):
    extraction_strategy: Literal["raw_html_only", "raw_html_plus_rows"] = "raw_html_plus_rows"
    emit_first_class_node: bool = True   # set False to revert to inline-block-only behavior
    parse_cells: bool = True
    parse_mentions: bool = True
```

### Envelope building

`_collect_parsed_tables()` in `envelope.py` is called from `build_envelope()`. Walks definitions, `extra_blocks`, and all subsections in source order. Maintains a per-parent seq counter keyed by `parent_natural_key`.

**Note**: `parse_table_block()` and `parse_table_block_from_html()` both live in `tables.py`. The envelope path uses `_from_html` since DOM nodes are unavailable at envelope-build time.

**Goldens**: `workers/ingestion/jainkosh/tests/golden/*.json` — `द्रव्य.json` has one table in `envelope.tables[]`.

---

## 7. Apply Layer — Ingestion

**File**: `workers/ingestion/jainkosh/apply.py` — `apply_approved_keyword_payload()`

### Apply order (per `ParsedTable` in `envelope.tables`)

After topic/keyword writes, before stub-edge linking:

```
1. upsert_table (Postgres)                → table_id (UUID)
2. upsert_table (Mongo) with table_id     → stable mongo _id
   (raw_html_doc_id = str(stable_id(natural_key))  ← pre-computed, not two-round-trip)
3. sync_table (Neo4j MERGE Table node)
4. sync_contains_table_edge (parent → table)
5. for kw_nk in mentioned_keyword_natural_keys:
     sync_stub_node Keyword if missing
     MERGE (Table)-[:MENTIONS_KEYWORD]->(Keyword)
6. for tp_nk in mentioned_topic_natural_keys:
     sync_stub_node Topic if missing
     MERGE (Table)-[:MENTIONS_TOPIC]->(Topic)
```

All within PG transaction → commit → Mongo → Neo4j flow.

### Parent-label lookup

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

If parent node doesn't exist yet, a stub is created so the edge can be MERGEd.

### `clear_dbs.py`

- Postgres: `tables` in the TRUNCATE list.
- MongoDB: `"tables"` in the collections-drop list.
- Neo4j: handled by `MATCH (n) DETACH DELETE n` (no change needed).

### Manual smoke check

```bash
python scripts/clear_dbs.py
python scripts/ingest_goldens_apply.py --keyword द्रव्य
psql jain_kb_dev -c "SELECT natural_key, parent_natural_key, seq FROM tables;"
mongosh jain_kb --eval 'db.tables.find({}, {natural_key:1, "cells.0":1}).pretty()'
cypher-shell -u neo4j -p jainkb_password \
  "MATCH (p)-[:CONTAINS_TABLE]->(t:Table) RETURN labels(p)[0] AS parent, p.natural_key, t.natural_key LIMIT 5;"
```

---

## 8. API Endpoints

**Router**: `services/core_service/domains/data/routers/tables.py`  
**Schemas**: `services/core_service/domains/data/schemas/tables.py`  
**Service**: `services/core_service/domains/data/services/tables.py`

### `GET /v1/tables/{natural_key}`

Returns `TableResponse` (full payload). 404 if not found.

Response includes `raw_html`, `cells`, `header_rows`, `plaintext`, `mentioned_keyword_natural_keys`, `mentioned_topic_natural_keys`.

### `GET /v1/tables?parent_natural_key=<nk>`

Returns `list[TableSummary]` ordered by `seq`. `parent_natural_key` is required (missing → 422).

```python
class TableSummary(BaseModel):
    natural_key: str
    seq: int
    caption: list[LangText]
```

Both endpoints set `Cache-Control: public, max-age=60`.

Data source: Postgres row joined with MongoDB doc. If Mongo doc is absent, returns empty `cells` + logs a warning (does not 500).

---

## 9. Hydration

**File**: `packages/jain_kb_common/jain_kb_common/hydration/tables.py`

```python
async def hydrate_tables_for_parent(pg, mongo, *, parent_natural_key: str) -> list[TableSummary]
async def hydrate_table_full(pg, mongo, *, natural_key: str) -> TableResponse | None
```

Used by topic / keyword detail responses to attach a `tables: [TableSummary]` list. Re-exported from `hydration/__init__.py`.

---

## 10. UI Components

### Types — `ui/src/lib/types.ts`

```ts
export type EntityKind =
  | "keyword" | "topic" | "gatha" | "teeka"
  | "bhaavarth" | "kalash" | "page" | "table";

export interface TableSummary {
  naturalKey: string;
  seq: number;
  caption: LangText[];
}

export interface TableFull {
  naturalKey: string;
  pgId: string;
  source: string;
  parentNaturalKey: string;
  parentKind: "topic" | "keyword" | "gatha" | "gatha_teeka"
            | "gatha_teeka_bhaavarth" | "kalash" | "kalash_bhaavarth" | "page";
  seq: number;
  caption: LangText[];
  sourceUrl: string | null;
  rawHtml: string;
  cells: string[][];
  headerRows: number;
  plaintext: string | null;
  mentionedKeywordNaturalKeys: string[];
  mentionedTopicNaturalKeys: string[];
}
```

### API Client — `ui/src/lib/api/data.ts`

```ts
getTable(naturalKey: string): Promise<TableFull>
listTablesForParent(parentNaturalKey: string): Promise<TableSummary[]>
```

Both route through the Next.js proxy at `/api/data/v1/tables/...`.

### Design tokens — `ui/src/styles/theme.css`

```css
--kind-table:       #6B7280;   /* neutral slate */
--kind-table-soft:  #E5E7EB;
```

Icon: `lucide-react/Table` reserved as `IconTable` in `ui/src/lib/icons.ts`.

### `TableModal` — `ui/src/components/TableModal.tsx`

Props: `{ naturalKey: string | null; onClose: () => void }`

Behaviour:
- Opens when `naturalKey` is non-null. Fetches via `getTable()` once, cached in a `useRef<Map>`.
- Loading state: shimmer skeleton.
- Error state: retry button + naturalKey for debugging.

Body sections (in order):
1. **Caption** — `getHindiText(table.caption)` as `<h2>`. Falls back to "तालिका".
2. **Source link** — link to `table.sourceUrl` in new tab (only when present).
3. **Rendered table** — from `cells` (NOT `rawHtml`). First `headerRows` rows → `<th>`. Alternating row bg using `--color-kind-table-soft/40`. Horizontally scrollable.
4. **Mentions** — badge rows for keywords + topics, each a locale-aware `Link`. Rendered only when non-empty.
5. **Raw HTML toggle (dev only)** — collapsible `<details>` with `<iframe srcDoc>` for debugging.

**Why cells, not rawHtml**: Source HTML may carry inline styles, classes, JS, or external `<a>` tags — security risk and visual clash. Parsed `cells` is clean NFC text.

### Graph store — `graphStore.ts`

Actions added:
- `tableModalNk: string | null`
- `openTableModal(nk: string)`
- `closeTableModal()`

---

## 11. Graph Integration

**File**: `services/core_service/domains/navigation/routers/graph.py`

- `Table` added to `_label_to_kind` → `"table"`.
- `CONTAINS_TABLE` added to the edge-type union in both `landing` and `expand` Cypher strings.
- `OR s:Table / OR t:Table` added to node label filters in `landing`.
- Tables are never stubs from JainKosh (`is_stub=false`), so they always appear when `exclude_stubs=true`.

**UI graph node rendering**: `kind === "table"` → `--color-kind-table` border, `--color-kind-table-soft` fill, `IconTable` icon, smaller diameter (leaf node). Click → `openTableModal(node.naturalKey)`.

**Filter chip**: label "तालिकाएँ", default ON, in the left filter panel.

**Content pages**:
- `topics/[nk]/page.tsx`, `dictionary/[nk]/page.tsx` — "तालिकाएँ" section with horizontal scrollable strip of `TableCard` (caption + first row preview). Click → modal.
- Reader page — tables surface as chips in the right info column.

---

## 12. i18n Strings

**Files**: `ui/messages/hi.json`, `ui/messages/en.json`

```json
"tables": {
  "section_title":       "तालिकाएँ",
  "modal_title_fallback": "तालिका",
  "mentioned_keywords":  "उल्लिखित कीवर्ड",
  "mentioned_topics":    "उल्लिखित विषय",
  "open_source":         "जैनकोश पर देखें",
  "loading":             "लोड हो रहा है…",
  "error":               "तालिका लोड नहीं हो सकी"
}
```

---

## 13. Testing

### DB layer (`tests/db/`)

- `test_upsert_table_idempotent` — insert, re-insert, assert row count = 1.
- `test_upsert_table_doc_idempotent` — MongoDB stable_id round-trip + indexes.
- `test_table_constraints_and_contains_edge` — Neo4j MERGE + 1 edge on re-run.

### Parser (`tests/workers/jainkosh/`)

- `test_table_parser.py::test_parses_cell_matrix_from_fixture`
- `test_table_parser.py::test_collects_mentioned_keywords_and_topics`
- `test_table_parser.py::test_natural_key_and_seq`
- `test_envelope_includes_tables`
- `tests/workers/jainkosh/test_golden_envelope.py` — snapshots against regenerated goldens.

### Apply (`tests/ingestion/test_apply.py`)

- `test_apply_persists_table_to_postgres`
- `test_apply_persists_table_to_mongo`
- `test_apply_creates_table_node_and_contains_edge_in_neo4j`
- `test_apply_table_mention_edges`
- `test_apply_table_idempotent`

### Services (`tests/services/`, `tests/common/`)

- `tests/services/data/test_tables.py` — 200, 404, seq ordering, missing-Mongo-doc graceful.
- `tests/services/navigation/test_graph_includes_tables.py` — Table node in `landing`/`expand`, `entity_kind="table"`, `exclude_stubs` behavior.
- `tests/common/hydration/test_hydration.py::test_hydrate_tables_for_parent`

### UI (`ui/src/__tests__/`)

- `TableModal.test.tsx` — cells, header rows, mentions, source link, dev toggle.
- `api/data.test.ts` — `getTable` / `listTablesForParent` proxy calls.
- `graphStore.test.ts` — modal state transitions.

### Run commands

```bash
# DB layer
export DATABASE_URL="postgresql+asyncpg://$(whoami)@localhost/jain_kb_test"
export MONGO_URL="mongodb://localhost:27017"
export NEO4J_URL="bolt://localhost:7687" NEO4J_USER=neo4j NEO4J_PASSWORD=jainkb_password
python -m pytest tests/db/ tests/workers/jainkosh/ tests/ingestion/ tests/services/ tests/common/ -v

# UI
cd ui && pnpm test && pnpm build
```

---

## 14. Manual Verification

### Backend

```bash
python scripts/clear_dbs.py
python scripts/ingest_goldens_apply.py --keyword द्रव्य
psql jain_kb_dev -c "SELECT natural_key, parent_natural_key, seq FROM tables;"
mongosh jain_kb --eval 'db.tables.find({}, {natural_key:1, "cells.0":1}).pretty()'
cypher-shell -u neo4j -p jainkb_password \
  "MATCH (p)-[:CONTAINS_TABLE]->(t:Table) RETURN labels(p)[0] AS parent, p.natural_key, t.natural_key LIMIT 5;"
curl "http://localhost:8001/v1/tables?parent_natural_key=<topic-nk>" | jq .
curl "http://localhost:8001/v1/tables/<table-nk>" | jq .
```

### UI

1. `uvicorn services.core_service.main:app --port 8001` (separate shell)
2. `cd ui && pnpm dev`
3. Open the topic page for `द्रव्य:षट्द्रव्य-विभाजन:...` — confirm "तालिकाएँ" section with one card; click → modal with 13 rows + 1 header row.
4. Open `/graph?focus=<same-nk>&depth=1` — confirm slate Table node with Table icon; click → modal.
5. Toggle "तालिकाएँ" filter chip OFF → Table nodes hidden; ON → reappear.
6. Switch to `/en/...` — labels translate, Devanagari content unchanged.

---

## 15. Key Files Reference

| Layer | File |
|---|---|
| Postgres model | `packages/jain_kb_common/jain_kb_common/db/postgres/tables.py` |
| Alembic migration | `migrations/0020_tables.py` |
| MongoDB schema | `packages/jain_kb_common/jain_kb_common/db/mongo/schemas.py` → `TableDoc` |
| MongoDB upsert | `packages/jain_kb_common/jain_kb_common/db/mongo/upserts.py` → `upsert_table` |
| MongoDB indexes | `packages/jain_kb_common/jain_kb_common/db/mongo/indexes.py` |
| Neo4j constraints | `packages/jain_kb_common/jain_kb_common/db/neo4j/constraints.py` |
| Neo4j upserts | `packages/jain_kb_common/jain_kb_common/db/neo4j/upserts.py` |
| Edge types config | `parser_configs/_meta/edge_types.yaml` |
| JainKosh parser | `workers/ingestion/jainkosh/tables.py` |
| Parser models | `workers/ingestion/jainkosh/models.py` → `ParsedTable` |
| Parser config | `workers/ingestion/jainkosh/config.py` → `TableExtractionConfig` |
| Envelope builder | `workers/ingestion/jainkosh/envelope.py` → `_collect_parsed_tables` |
| Apply layer | `workers/ingestion/jainkosh/apply.py` → `apply_approved_keyword_payload` |
| Hydration | `packages/jain_kb_common/jain_kb_common/hydration/tables.py` |
| API router | `services/core_service/domains/data/routers/tables.py` |
| API schemas | `services/core_service/domains/data/schemas/tables.py` |
| API service | `services/core_service/domains/data/services/tables.py` |
| Graph traversal | `services/core_service/domains/navigation/routers/graph.py` |
| UI types | `ui/src/lib/types.ts` |
| UI API client | `ui/src/lib/api/data.ts` |
| UI modal | `ui/src/components/TableModal.tsx` |
| UI graph store | `ui/src/store/graphStore.ts` |
| UI design tokens | `ui/src/styles/theme.css` |
| i18n (Hindi) | `ui/messages/hi.json` |
| i18n (English) | `ui/messages/en.json` |

---

## 16. Phase History

| Phase | Scope | Status |
|---|---|---|
| [Phase 1 — Schema](./initial_design/table_phase1_schema.md) | Postgres + Mongo + Neo4j schema, constraints, upserts | Done |
| [Phase 2 — JainKosh Parser](./initial_design/table_phase2_parser.md) | `ParsedTable`, envelope emission, goldens | Done |
| [Phase 3 — Apply](./initial_design/table_phase3_apply.md) | Persist to all 3 stores, mention edges, `clear_dbs.py` | Done |
| [Phase 4 — API + Hydration](./initial_design/table_phase4_api.md) | `GET /v1/tables/*`, graph traversal, hydration helpers | Done |
| [Phase 5 — UI](./initial_design/table_phase5_ui.md) | `TableModal`, graph node + filter chip, content page sections | Done |
