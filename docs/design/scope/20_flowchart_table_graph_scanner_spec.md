# 20 — Flowchart / Table / Graph Scanner Spec

Scope context: [`scope/06_advanced_rag_and_finetuning.md`](../../scope/06_advanced_rag_and_finetuning.md) ("Flowchart / table / diagram retrieval").
Depends on: [`design/03_data_model_mongo.md`](../data_model/03_data_model_mongo.md) (`figures_blobs` collection already defined), [`design/02_data_model_postgres.md`](../data_model/02_data_model_postgres.md), and the existing OCR ingestion pipeline that already produces per-page rendered images under `cataloguesearch_shastra_id`.

OCRed shastra pages frequently contain pre-existing flowcharts, tables, graphs (line/bar), and decorative images. A scanner worker detects these visual structures, persists their crop in Mongo + an index row in Postgres, and exposes them to the AI page (and reader) for interactive re-rendering. Flowcharts re-render as `react-flow` / `mermaid` graphs, tables as sortable HTML tables, and graphs as Plotly/Recharts charts when structured data can be recovered.

## Phase A — detector worker

### Files

```
workers/figure_scanner/
├── __init__.py
├── main.py                  Celery worker entry: tasks.scan_page(shastra_id, page_index)
├── config.py                Settings (DATABASE_URL, MONGO_URL, S3_BUCKET, LAYOUT_MODEL,
│                            CONFIDENCE_THRESHOLD=0.55, MIN_BBOX_AREA_PX=12000, PORT=N/A)
├── detector/
│   ├── __init__.py
│   ├── layout.py            layoutparser PrimaLayout / PubLayNet wrapper
│   ├── heuristics.py        post-processing: bbox merge, aspect-ratio gating,
│   │                        type re-classification (table vs graph vs flowchart)
│   ├── crop.py              PIL crop + WEBP encode for Mongo
│   └── ocr_glue.py          re-OCR the crop in isolation (Tesseract / paddleocr)
├── extractors/
│   ├── __init__.py
│   ├── flowchart.py         crop → node-edge JSON (uses LLM via model-serving)
│   ├── table.py             crop → 2D array (img2table primary, LLM fallback)
│   └── graph_chart.py       crop → {axes, series} JSON (LLM extractor, best-effort)
├── tasks.py                 Celery tasks: scan_page, scan_shastra, reextract_figure
└── tests/
    ├── conftest.py
    ├── fixtures/
    │   ├── flowchart_sample.png      (one synthetic flowchart)
    │   ├── table_sample.png          (one 3x4 table)
    │   └── graph_sample.png          (one bar chart)
    ├── test_detector_goldens.py
    ├── test_heuristics_bbox_merge.py
    ├── test_flowchart_round_trip.py
    ├── test_table_round_trip.py
    └── test_chart_round_trip.py
```

### Detector pipeline

```python
# workers/figure_scanner/detector/layout.py
import layoutparser as lp

MODEL = lp.Detectron2LayoutModel(
    config_path="lp://PubLayNet/mask_rcnn_X_101_32x8d_FPN_3x/config",
    extra_config=["MODEL.ROI_HEADS.SCORE_THRESH_TEST", 0.55],
    label_map={0: "text", 1: "title", 2: "list", 3: "table", 4: "figure"},
)

def detect(image) -> list[dict]:
    """Returns [{type, bbox:(x0,y0,x1,y1), score}]."""
```

Heuristic post-processing in `heuristics.py`:

1. **Merge overlapping bboxes** of the same `type` when IoU > 0.4 (likely an over-segmented figure).
2. **Reclassify `figure` → {flowchart, graph, image}** using:
   - `flowchart` if interior has ≥ 3 distinct connected components separated by whitespace and the OCR sees arrow glyphs (`→ ↑ ↓ ←` or words `then`, `तब`, `फिर`).
   - `graph` if axes-like straight lines detected (Hough transform finds ≥ 2 long perpendicular lines along bbox edges).
   - `image` otherwise (decorative/photo).
3. **Drop tiny boxes** below `MIN_BBOX_AREA_PX`.
4. **Drop boxes intersecting the page header/footer** by more than 60%.

Final type enum: `flowchart | table | graph | image`.

### Postgres schema (migration `0038_figures_index.py`)

```sql
CREATE TYPE figure_type   AS ENUM ('flowchart','table','graph','image');
CREATE TYPE figure_status AS ENUM ('detected','extracted','review','published','rejected');

CREATE TABLE figures_index (
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  shastra_id            UUID NOT NULL REFERENCES shastras(id) ON DELETE CASCADE,
  cataloguesearch_shastra_id TEXT NOT NULL,        -- redundant for fast lookup w/o join
  source_page_index     INT NOT NULL,              -- 0-based page in cataloguesearch
  source_page_ref       TEXT NOT NULL,             -- printable page label, e.g. 'p.124'
  type                  figure_type NOT NULL,
  bbox                  JSONB NOT NULL,            -- {x0:int, y0:int, x1:int, y1:int, w:int, h:int}
  detector_score        REAL NOT NULL,
  mongo_blob_id         TEXT NOT NULL,             -- _id in figures_blobs collection
  ocr_text              TEXT,                      -- re-OCRed text inside the bbox
  structured_data       JSONB,                     -- type-specific payload (see below)
  nearest_gatha_id      UUID REFERENCES gathas(id) ON DELETE SET NULL,
  nearest_topic_natural_key TEXT,
  status                figure_status NOT NULL DEFAULT 'detected',
  reviewer_id           UUID REFERENCES users(id) ON DELETE SET NULL,
  reviewer_notes        TEXT,
  created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (shastra_id, source_page_index, bbox)
);

CREATE INDEX idx_figures_shastra_page  ON figures_index(shastra_id, source_page_index);
CREATE INDEX idx_figures_type_status   ON figures_index(type, status);
CREATE INDEX idx_figures_nearest_gatha ON figures_index(nearest_gatha_id);
```

`bbox` is stored as JSONB so additional fields (`page_width`, `page_height`, `rotation_deg`) can be appended without migration.

### `structured_data` shape per type

**flowchart:**

```json
{
  "format": "react-flow",
  "nodes": [
    {"id": "n1", "label": "जीव", "position": {"x": 0, "y": 0}, "type": "default"},
    {"id": "n2", "label": "अजीव", "position": {"x": 200, "y": 0}, "type": "default"}
  ],
  "edges": [
    {"id": "e1", "source": "n1", "target": "n2", "label": "विरोधी"}
  ],
  "mermaid": "graph LR; n1[जीव] -- विरोधी --> n2[अजीव]"
}
```

Both `react-flow` and a `mermaid` string are emitted. The UI prefers `react-flow`; `mermaid` is the fallback when the layout is too rich for the auto-positioner.

**table:**

```json
{
  "headers": ["गुणस्थान", "क्रम", "ज्ञान"],
  "rows": [
    ["मिथ्यात्व", "1", "अल्प"],
    ["सासादन",   "2", "अल्प"]
  ],
  "row_count": 2,
  "col_count": 3
}
```

`headers` is the first row only when the extractor is confident; otherwise it is `null` and the UI renders without a header band.

**graph (chart):**

```json
{
  "chart_type": "bar",
  "x_axis": {"label": "गुणस्थान", "values": ["1","2","3","4"]},
  "series": [
    {"name": "जीव संख्या", "values": [10, 8, 6, 4]}
  ]
}
```

`chart_type ∈ {bar, line, pie, scatter, unknown}`. When `unknown`, the UI falls back to rendering the original image crop.

**image:** `structured_data` is `null`; the crop is shown as-is.

### Mongo collection (already in `03_data_model_mongo.md`)

```
figures_blobs:
{
  _id: "<uuid>",                       // matches figures_index.mongo_blob_id
  shastra_id: "<uuid>",
  source_page_index: <int>,
  webp_bytes: BinData,                 // crop, WEBP quality 85
  width_px: <int>, height_px: <int>,
  created_at: ISODate
}
```

Index: `{ shastra_id: 1, source_page_index: 1 }`.

### Tests (TDD — write first)

1. `test_detector_goldens.py::test_detects_flowchart_in_fixture` — `fixtures/flowchart_sample.png` detector finds ≥ 1 bbox; `type` lands on `flowchart` after heuristics.
2. `test_detector_goldens.py::test_detects_table_in_fixture` — table fixture → `type == 'table'`.
3. `test_heuristics_bbox_merge.py::test_overlapping_boxes_merge` — two boxes IoU=0.6 → 1 merged box.
4. `test_heuristics_bbox_merge.py::test_disjoint_boxes_kept` — IoU=0.0 → both kept.
5. `test_flowchart_round_trip.py::test_react_flow_payload_validates` — emitted JSON validates against `react-flow` JSON schema (vendored).
6. `test_table_round_trip.py::test_table_array_roundtrip` — known fixture decodes to expected `headers` + 2-row matrix.
7. `test_chart_round_trip.py::test_chart_type_inferred` — bar fixture → `chart_type == 'bar'`.
8. `test_chart_round_trip.py::test_unknown_falls_back` — noise image → `chart_type == 'unknown'`, no `series`.

## Phase B — storage + admin review API

### Files

```
services/data-service/app/routers/
└── figures.py               admin + public endpoints

packages/jain_kb_common/db/postgres/figures.py    SQLAlchemy model
packages/jain_kb_common/db/mongo/figures.py       Motor helper
```

### Endpoints (on existing `data-service`, port 8001)

**Public (auth optional, no PII):**

```
GET /v1/figures?shastra_natural_key=&page_index=&type=&status=published
  → page<FigureOut>

GET /v1/figures/{id}                       → FigureOut
GET /v1/figures/{id}/blob                  → image/webp (proxied from Mongo)

GET /v1/figures/by-gatha/{gatha_id}        → list<FigureOut>  (nearest_gatha_id match)
GET /v1/figures/by-topic/{topic_nk}        → list<FigureOut>  (nearest_topic_natural_key)
```

**Admin (`require_role('admin','reviewer')`):**

```
GET    /admin/figures?status=detected&type=flowchart&shastra_id=
POST   /admin/figures/{id}/status          body: { status: 'review'|'published'|'rejected', notes? }
POST   /admin/figures/{id}/reextract       force re-run of extractor with override prompt
PUT    /admin/figures/{id}/structured-data body: structured_data JSON; sets status='published'
POST   /admin/figures/scan                 body: { shastra_id, pages?:[int] } → 202
```

### Pydantic contracts

```python
class FigureBbox(BaseModel):
    x0: int; y0: int; x1: int; y1: int
    w: int; h: int

class FigureOut(BaseModel):
    id: UUID
    shastra_id: UUID
    cataloguesearch_shastra_id: str
    source_page_index: int
    source_page_ref: str
    type: Literal['flowchart','table','graph','image']
    bbox: FigureBbox
    detector_score: float
    blob_url: str                                  # /v1/figures/{id}/blob
    ocr_text: str | None
    structured_data: dict | None
    nearest_gatha_id: UUID | None
    nearest_topic_natural_key: str | None
    status: Literal['detected','extracted','review','published','rejected']
    created_at: datetime
```

### Nearest-gatha resolution

Run after detection: for each figure box, find the gatha whose bbox/page index minimises Manhattan distance on the same page. `query-service` already exposes `gatha_bbox_for_page(shastra_id, page_index)`; reuse it. If no gatha on the same page, leave `nearest_gatha_id = NULL`.

### Tests (TDD)

1. `test_figures_router.py::test_public_published_only` — `GET /v1/figures` hides non-`published` rows.
2. `test_figures_router.py::test_admin_sees_all_statuses`.
3. `test_figures_router.py::test_blob_proxy_streams_webp` — `Content-Type: image/webp`, body bytes match Mongo blob.
4. `test_figures_router.py::test_status_transition_review_to_published`.
5. `test_figures_router.py::test_reject_clears_from_public_view`.
6. `test_figures_router.py::test_structured_data_put_validates_against_type` — flowchart JSON in table row → 422.
7. `test_figures_router.py::test_by_gatha_returns_only_matching`.
8. `test_scan_endpoint.py::test_scan_enqueues_celery_task` — `POST /admin/figures/scan` → Celery message captured.

## Phase C — AI page render (interactive viewer)

### Files

```
ui/components/AIPage/
├── FigureViewer.tsx              decides which renderer based on type
├── FlowchartRenderer.tsx         react-flow when nodes/edges present; else mermaid; else image
├── TableRenderer.tsx             sortable HTML table; CSV download
├── ChartRenderer.tsx             Recharts (bar/line/pie/scatter); image fallback
├── ImageRenderer.tsx             <img> with zoom (react-medium-image-zoom)
└── FigureCitation.tsx            badge: shastra name + page ref + "view in reader"

ui/lib/api/figures.ts             fetch helpers (typed)
ui/lib/figures/flowchartLayout.ts elk.js layout for react-flow when positions missing
```

### Behaviour

- The AI page chat already attaches `citation_tiles` to assistant messages. When a tile references a `figure_id`, render `<FigureViewer figure={...} />` inline beneath the message.
- `FigureViewer` reads `figure.type` and dispatches:
  - `flowchart` → `FlowchartRenderer`. If `structured_data.nodes` lacks positions, run `flowchartLayout(nodes, edges)` (elk.js layered direction LR) before passing to `react-flow`.
  - `table` → `TableRenderer`. Headers row sticky; per-column sort; CSV export pulls from props.
  - `graph` → `ChartRenderer`. Maps `chart_type` to Recharts component. `unknown` → `ImageRenderer`.
  - `image` → `ImageRenderer`.
- All renderers display `<FigureCitation>` at the bottom: `{shastra title} · {source_page_ref}` with a "view in reader" link to `/reader/{shastra_natural_key}?page={index}&highlight-figure={id}`.

### Reader integration (light)

The shastra reader (spec 03) draws a faint outline on figures of `status='published'` and on click opens the same `FigureViewer` in a modal. This is one-line wiring: reader already calls `GET /v1/figures?shastra_natural_key=...&page_index=...` per visible page.

### Tests

1. `FigureViewer.test.tsx::renders_react_flow_when_nodes_present`.
2. `FigureViewer.test.tsx::renders_mermaid_when_only_mermaid_string`.
3. `FigureViewer.test.tsx::renders_image_for_unknown_chart_type`.
4. `TableRenderer.test.tsx::sort_by_column_reorders_rows`.
5. `ChartRenderer.test.tsx::renders_bar_chart_for_chart_type_bar`.
6. `FlowchartRenderer.test.tsx::layout_runs_when_positions_missing`.
7. Playwright `figures.spec.ts::clicking_outline_in_reader_opens_modal`.
8. Playwright `figures.spec.ts::ai_page_citation_renders_figure_inline`.

## Manual verification

```bash
# 0. Prereq: a shastra is ingested + OCRed in cataloguesearch.
SHASTRA_ID=$(psql -tAc "SELECT id FROM shastras WHERE natural_key='gomatsar_jiv_kand' LIMIT 1")

# 1. Run migration + start worker
alembic upgrade 0038
celery -A workers.figure_scanner.main worker -l info -Q figures &

# 2. Trigger a scan
curl -X POST http://localhost:8001/admin/figures/scan \
  -b cookies.txt -H 'content-type: application/json' \
  -d "{\"shastra_id\":\"$SHASTRA_ID\"}"

# 3. Poll detected rows
psql -c "SELECT type, count(*) FROM figures_index WHERE shastra_id='$SHASTRA_ID' GROUP BY type;"

# 4. Pull one figure's blob
FIG=$(psql -tAc "SELECT id FROM figures_index WHERE type='flowchart' LIMIT 1")
curl -OJ http://localhost:8001/v1/figures/$FIG/blob

# 5. Publish it
curl -X POST http://localhost:8001/admin/figures/$FIG/status \
  -b cookies.txt -H 'content-type: application/json' \
  -d '{"status":"published"}'

# 6. UI smoke
open "http://localhost:3000/reader/gomatsar_jiv_kand?page=12"
# Expect: figure outline on page 12; click → modal with FigureViewer; flowchart renders interactively.
```

## Definition of done

- [ ] Migration `0038_figures_index.py` applies cleanly; `figures_blobs` Mongo index created.
- [ ] All Phase A detector tests green against the three fixtures.
- [ ] All Phase B router tests green; admin RBAC enforced.
- [ ] Phase C renderers handle every `type` including the `unknown` chart fallback.
- [ ] End-to-end: scan one OCRed shastra → ≥ 1 flowchart published → renders as an interactive `react-flow` inside the AI page chat.
- [ ] `nearest_gatha_id` populated for ≥ 80% of rows where a gatha exists on the same page (measured in manual run).
- [ ] Reader outline + modal works without a full page reload.

## Implementation notes

_(to be filled in after merge)_
