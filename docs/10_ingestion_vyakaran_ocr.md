# 10 — Ingestion: Vyakaran Vishleshan OCR (scaffold)

This module is **stubbed for v1**. It documents the I/O contract so that when OCR rules are finalized, only `workers/ingestion/vyakaran_ocr/engine.py` needs implementation; the orchestrator, queue, and storage layers are pre-wired.

## Source

`vyakaran_vishleshan/<shastra_slug>/*.png` — scanned pages of vyakaran-vishleshan books (e.g. by Kamalchand Sogani Ji on Pravachansaar). Each PNG corresponds to a page that contains:

- Word-by-word Sanskrit/Prakrit grammatical breakdown of a gatha
- Tables of declensions / conjugations
- Hindi explanatory prose
- Cross-references to other gathas

`<shastra_slug>/rules/*.png` — scanned **rule pages** that document how to interpret the breakdowns (parser metadata).

## Pluggable engine interface

```python
# workers/ingestion/vyakaran_ocr/engine.py
from typing import Protocol

class OCREngine(Protocol):
    name: str

    async def ocr_page(self, image_path: str, hints: dict) -> "OCRPageResult":
        """Return text + tables + bbox structure for one PNG."""
        ...
```

Implementations (provide one):

- `TesseractEngine` (offline, free): `pytesseract` with `lang="hin+san"` traineddata.
- `GoogleVisionEngine` (cloud, paid): document text detection + table detection.
- `IndicOCREngine` (offline, model-heavy): future option.

For v1, ship only `TesseractEngine` as a stub returning `OCRPageResult(status="not_implemented", text=None, ...)`.

## I/O contract

```python
class OCRTable(BaseModel):
    rows: list[list[str]]
    bbox: tuple[int, int, int, int]   # x0, y0, x1, y1
    confidence: float

class OCRPageResult(BaseModel):
    status: Literal["ok", "low_confidence", "failed", "not_implemented"]
    image_path: str
    page_text: list[Multilingual]                # full-page text, language-tagged blocks
    tables: list[OCRTable]
    layout_blocks: list[dict]                    # raw word/line bboxes for downstream
    engine: str
    engine_version: str
    confidence: float
    raw_response: dict | None                    # vendor-specific JSON, optional
```

## Output mapping

For each PNG processed, produce one `ocr_pages` Mongo document:

```json
{
  "natural_key": "vyakaran_vishleshan:pravachansaar:gatha-1:page-1",
  "shastra_natural_key": "pravachansaar",
  "gatha_natural_key": "pravachansaar:001",
  "page": 1,
  "image_path": "vyakaran_vishleshan/pravachansaar/gatha1.png",
  "ocr_engine": "tesseract-5.x-hin+san",
  "ocr_text": [{"lang": "hin", "script": "Deva", "text": "..."}],
  "tables": [{"rows": [["...", "..."]], "bbox": [0,0,100,100], "confidence": 0.91}],
  "review_status": "raw",
  "ingestion_run_id": "uuid"
}
```

After admin review, the curator populates structured `gatha_word_meanings` documents for the corresponding gathas. For v2, an additional pass extracts grammatical features (case, gender, number) into a structured field — schema TBD when rules are formalized.

## Job structure (scaffold)

```
workers/ingestion/vyakaran_ocr/
├── orchestrator.py         # walks vyakaran_vishleshan/<shastra>/*.png, dispatches
├── engine.py               # OCREngine protocol
├── engines/
│   ├── tesseract.py        # v1 stub
│   ├── google_vision.py    # future
│   └── indic_ocr.py        # future
├── postprocess.py          # text cleaning, bbox merging (future)
└── tests/
```

## Parser config (`parser_configs/vyakaran_vishleshan/pravachansaar.yaml`)

```yaml
version: 0.1.0-stub
source: vyakaran_vishleshan
shastra_natural_key: pravachansaar
input:
  pages_glob: "vyakaran_vishleshan/pravachansaar/*.png"
  rules_glob: "vyakaran_vishleshan/pravachansaar/rules/*.png"
gatha_inference:
  # how to map filename → gatha_number; placeholder
  filename_pattern: 'gatha(?P<num>\d+)\.png'
  zero_pad_to: 3
ocr:
  engine: tesseract
  langs: ["hin", "san"]
  dpi: 300
  preprocess:
    deskew: true
    binarize: adaptive
  confidence_threshold: 0.65
review:
  auto_approve: false
```

## Definition of Done (v1 scaffold)

- [ ] `OCREngine` protocol and `OCRPageResult` Pydantic model are implemented and importable.
- [ ] `TesseractEngine` exists and returns `status="not_implemented"` (intentional stub).
- [ ] Orchestrator walks `vyakaran_vishleshan/pravachansaar/*.png`, creates `ingestion_runs` rows, and inserts `ocr_pages` Mongo docs in `not_implemented` state.
- [ ] Admin UI page for reviewing OCR rows exists (placeholder, see `13_*`).
- [ ] No production traffic depends on this module yet.
