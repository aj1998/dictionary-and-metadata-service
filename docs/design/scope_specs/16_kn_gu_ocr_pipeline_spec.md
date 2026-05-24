# 16 — Kannada + Gujarati OCR Pipeline Spec

Scope context: [`scope/05_multilingual_strategy.md`](../../scope/05_multilingual_strategy.md). The bulk of canonical Jain content is already digital Hindi/Sanskrit. Kannada and Gujarati translations exist mostly as scanned PDFs (Digambar / Sthānakvāsī samājs in Karnataka and Gujarat). This spec defines an OCR pipeline that turns those PDFs into `shastras → adhikaars → gathas/paragraphs` rows with `lang in {kn, gu}` overlays, mapped to the canonical Hindi keyword via the Vitrag dictionary (spec 14) and a fuzzy alias table.

Depends on:
- **Spec 14** — Vitrag dictionary (used as a constrained Hi↔En anchor; for Kn/Gu we treat Hi as the canonical pivot).
- **Spec 15** — multilingual label storage (Kn/Gu surface forms land in `keyword_aliases_multilingual` and as additional entries in `label_multilingual`).

Three phases:

- **Phase A** — OCR scaffold: ingest PDF, run Tesseract per page (primary), fall back to Google Vision per page on low confidence; persist `ocr_pages`.
- **Phase B** — Keyword mapping: for each OCR page, resolve Kn/Gu surface forms to canonical Hindi keyword ids via Vitrag exact-match and a fuzzy alias table.
- **Phase C** — Ingestion: split normalised OCR text into shastra/adhikaar/paragraph rows; emit multilingual entries; idempotent.

## Module paths

```
workers/ocr_kn_gu_worker/
├── __init__.py
├── main.py                      # Celery entrypoints: enqueue_pdf, ocr_page, map_keywords, ingest_doc
├── tesseract.py                 # subprocess wrapper, per-language config
├── gvision.py                   # Google Vision fallback
├── normalise.py                 # Unicode NFC + script-specific fixups
├── mapper.py                    # alias + fuzzy lookup
├── splitter.py                  # OCR text → shastra/adhikaar/paragraph segments
├── tests/
│   ├── conftest.py
│   ├── fixtures/
│   │   ├── golden_kn_page.png
│   │   ├── golden_gu_page.png
│   │   ├── golden_kn_text.txt
│   │   ├── alias_seed.sql
│   │   └── tiny_pdf.pdf
│   ├── test_ocr_golden_image.py
│   ├── test_kn_gu_unicode_normalisation.py
│   ├── test_alias_mapping_fuzz_threshold.py
│   ├── test_ingestion_idempotency.py
│   └── test_gvision_fallback_on_low_confidence.py

services/data-service/app/routers/
└── ocr_jobs.py                  # admin endpoints for jobs + page review

packages/jain_kb_common/db/postgres/
├── enums.py                     # extend with ocr_job_status, alias_source
└── ocr.py                       # ORM models
```

## Phase A — OCR scaffold

### Postgres schema (migration `0035_ocr_pipeline.py`)

```sql
CREATE TYPE ocr_job_status AS ENUM (
  'pending','downloading','running','review','ingested','failed','cancelled');

CREATE TABLE ocr_jobs (
  id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  source_pdf_s3_key  TEXT NOT NULL,
  source_pdf_sha256  TEXT NOT NULL,
  lang               TEXT NOT NULL CHECK (lang IN ('kn','gu')),
  shastra_natural_key TEXT,                   -- nullable until ingest phase
  status             ocr_job_status NOT NULL DEFAULT 'pending',
  pages_total        INT NOT NULL DEFAULT 0,
  pages_done         INT NOT NULL DEFAULT 0,
  pages_low_conf     INT NOT NULL DEFAULT 0,
  errors             JSONB NOT NULL DEFAULT '[]'::jsonb,
  triggered_by       TEXT NOT NULL,
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT uq_ocr_jobs_pdf UNIQUE (source_pdf_sha256, lang)
);
CREATE INDEX idx_ocr_jobs_status ON ocr_jobs(status);

CREATE TABLE ocr_pages (
  id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  job_id             UUID NOT NULL REFERENCES ocr_jobs(id) ON DELETE CASCADE,
  page_no            INT NOT NULL,
  raw_text           TEXT,                    -- Tesseract output (may be empty)
  fallback_text      TEXT,                    -- Google Vision output if invoked
  chosen_source      TEXT NOT NULL DEFAULT 'tesseract'
                       CHECK (chosen_source IN ('tesseract','gvision','manual')),
  normalised_text    TEXT,                    -- NFC + script fixups
  confidence         NUMERIC(4,3),            -- mean per-word confidence, 0..1
  word_boxes         JSONB,                   -- [{w, conf, bbox:[x,y,w,h]}]
  manual_override    TEXT,                    -- reviewer's edit
  reviewed_by        UUID,
  reviewed_at        TIMESTAMPTZ,
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT uq_ocr_pages UNIQUE (job_id, page_no)
);
CREATE INDEX idx_ocr_pages_job ON ocr_pages(job_id);
CREATE INDEX idx_ocr_pages_low_conf ON ocr_pages(job_id) WHERE confidence < 0.75;
```

### Pydantic contracts

```python
class OCRJobOut(BaseModel):
    id: UUID
    source_pdf_s3_key: str
    lang: Literal['kn','gu']
    shastra_natural_key: str | None
    status: Literal['pending','downloading','running','review','ingested','failed','cancelled']
    pages_total: int
    pages_done: int
    pages_low_conf: int
    created_at: datetime

class OCRPageOut(BaseModel):
    id: UUID
    page_no: int
    raw_text: str | None
    fallback_text: str | None
    chosen_source: Literal['tesseract','gvision','manual']
    normalised_text: str | None
    confidence: float | None
```

### Celery tasks

```python
LOW_CONF_THRESHOLD = float(os.getenv('OCR_LOW_CONF_THRESHOLD', '0.75'))
TESS_LANGS = {'kn': 'kan', 'gu': 'guj'}

@celery.task(name='ocr.enqueue_pdf')
def enqueue_pdf(*, s3_key: str, lang: str, triggered_by: str) -> str:
    sha = sha256_of_s3_object(s3_key)
    job = upsert_job(s3_key=s3_key, sha=sha, lang=lang, triggered_by=triggered_by)
    download_and_paginate.delay(job_id=str(job.id))
    return str(job.id)

@celery.task(name='ocr.download_and_paginate')
def download_and_paginate(*, job_id: str):
    pdf = s3.download(job.source_pdf_s3_key)
    pages = pdf_to_pngs(pdf, dpi=300)
    update_job(job_id, status='running', pages_total=len(pages))
    for i, png in enumerate(pages, start=1):
        ocr_page.delay(job_id=job_id, page_no=i, png_s3_key=upload_page_png(png))

@celery.task(name='ocr.ocr_page', autoretry_for=(OCRTransient,), retry_backoff=True,
             max_retries=4)
def ocr_page(*, job_id: str, page_no: int, png_s3_key: str):
    job = get_job(job_id)
    png = s3.download(png_s3_key)
    tess = run_tesseract(png, lang=TESS_LANGS[job.lang])  # returns text + word_boxes + mean_conf
    chosen, text, conf, boxes = 'tesseract', tess.text, tess.mean_conf, tess.word_boxes
    if tess.mean_conf < LOW_CONF_THRESHOLD:
        gv = run_gvision(png, lang=job.lang)
        if gv.mean_conf > tess.mean_conf + 0.05:
            chosen, text, conf, boxes = 'gvision', gv.text, gv.mean_conf, gv.word_boxes
    normalised = normalise_text(text, lang=job.lang)
    upsert_page(job_id=job_id, page_no=page_no,
                raw_text=tess.text, fallback_text=gv.text if chosen=='gvision' else None,
                chosen_source=chosen, normalised_text=normalised,
                confidence=conf, word_boxes=boxes)
    bump_progress(job_id, low_conf=(conf < LOW_CONF_THRESHOLD))
    if all_pages_done(job_id):
        update_job(job_id, status='review')
        map_keywords_for_job.delay(job_id=job_id)
```

### Normalisation (`workers/ocr_kn_gu_worker/normalise.py`)

```python
def normalise_text(text: str, *, lang: str) -> str:
    s = unicodedata.normalize('NFC', text)
    # script-specific fixups
    if lang == 'kn':
        s = _fix_kannada_zwj(s)         # strip stray ZWJ/ZWNJ between consonant + halant
        s = _collapse_kn_visarga(s)      # ‵ ’ → ः when standalone after vowel
    elif lang == 'gu':
        s = _fix_gujarati_nukta(s)
    s = re.sub(r'[ \t]+', ' ', s)
    s = re.sub(r'\n{3,}', '\n\n', s)
    return s.strip()
```

The exact fixup rules are frozen by `test_kn_gu_unicode_normalisation.py`.

## Phase B — Keyword mapping

### Postgres schema (migration `0036_keyword_alias_multilingual.py`)

```sql
CREATE TYPE alias_source AS ENUM ('manual','vitrag','fuzzy');

CREATE TABLE keyword_alias_multilingual (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  canonical_keyword_id UUID NOT NULL REFERENCES keywords(id) ON DELETE CASCADE,
  lang                TEXT NOT NULL,                 -- 'kn','gu','en','sa','pr',...
  script              TEXT NOT NULL,                 -- 'Knda','Gujr','Latn','Deva',...
  text                TEXT NOT NULL,                 -- NFC; the surface alias
  source              alias_source NOT NULL,
  confidence          NUMERIC(4,3) NOT NULL DEFAULT 1.0
                       CHECK (confidence BETWEEN 0 AND 1),
  reviewer_id         UUID,
  approved_at         TIMESTAMPTZ,
  created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT uq_keyword_alias UNIQUE (canonical_keyword_id, lang, script, text)
);
CREATE INDEX idx_alias_text ON keyword_alias_multilingual(text);
CREATE INDEX idx_alias_lang_script ON keyword_alias_multilingual(lang, script);
CREATE INDEX idx_alias_text_trgm ON keyword_alias_multilingual USING gin (text gin_trgm_ops);
```

### Mapper

```python
# workers/ocr_kn_gu_worker/mapper.py

FUZZY_THRESHOLD = float(os.getenv('OCR_ALIAS_FUZZ_THRESHOLD', '0.86'))

def map_surface(surface: str, *, lang: str, script: str) -> MapResult:
    s = nfc(surface)
    # 1. Exact alias hit (any source) -> 'high'
    if hit := pg.fetch_one("""SELECT canonical_keyword_id, confidence FROM keyword_alias_multilingual
                              WHERE lang=:l AND script=:s AND text=:t""",
                            l=lang, s=script, t=s):
        return MapResult(keyword_id=hit.canonical_keyword_id, source='exact',
                          confidence=float(hit.confidence))
    # 2. Vitrag bridge: kn/gu term ↔ canonical hindi term in vitrag_dict
    if bridge := vitrag_bridge_lookup(s, lang=lang):
        return MapResult(keyword_id=bridge.keyword_id, source='vitrag',
                          confidence=0.95)
    # 3. Trigram fuzzy against keyword_alias_multilingual within the same (lang,script)
    sims = pg.fetch_all("""SELECT canonical_keyword_id,
                                  similarity(text, :t) AS sim
                           FROM keyword_alias_multilingual
                           WHERE lang=:l AND script=:s AND similarity(text, :t) > :th
                           ORDER BY sim DESC LIMIT 3""",
                        l=lang, s=script, t=s, th=FUZZY_THRESHOLD)
    if sims:
        top = sims[0]
        return MapResult(keyword_id=top.canonical_keyword_id, source='fuzzy',
                          confidence=float(top.sim))
    return MapResult(keyword_id=None, source='none', confidence=0.0)
```

`vitrag_bridge_lookup` translates a Kn/Gu surface to its Hindi equivalent via two parallel mechanisms: (a) approved entries in `keyword_alias_multilingual` with `source='vitrag'` (preferred); (b) script-folded Hindi candidate via an Indic transliteration library (used as a hint only, never auto-approved).

Hits with `source='fuzzy'` create a **draft** alias row pending reviewer approval (no auto-promotion to the canonical keyword). Hits with `source='vitrag'` or exact alias are treated as confirmed.

```python
@celery.task(name='ocr.map_keywords_for_job')
def map_keywords_for_job(*, job_id: str):
    job = get_job(job_id)
    for page in iter_pages(job_id):
        surfaces = tokenise_indic(page.normalised_text, lang=job.lang)
        for s in surfaces:
            r = map_surface(s, lang=job.lang, script=script_of(job.lang))
            if r.keyword_id and r.source == 'fuzzy':
                upsert_alias_draft(canonical=r.keyword_id, lang=job.lang,
                                    script=script_of(job.lang), text=s,
                                    confidence=r.confidence)
```

## Phase C — Ingestion

```python
@celery.task(name='ocr.ingest_doc')
def ingest_doc(*, job_id: str, shastra_natural_key: str, reviewer_id: str):
    job = get_job(job_id)
    update_job(job_id, shastra_natural_key=shastra_natural_key)
    segments = splitter.split(load_full_normalised_text(job_id), lang=job.lang)
    with pg.transaction() as tx:
        for seg in segments:
            if seg.kind == 'adhikaar':
                upsert_adhikaar(tx, shastra_nk=shastra_natural_key,
                                  natural_key=seg.nk,
                                  heading_multilingual=[{
                                    'lang': job.lang,
                                    'script': script_of(job.lang),
                                    'text': seg.heading}])
            elif seg.kind == 'gatha':
                upsert_gatha_overlay(tx, natural_key=seg.nk,
                                     overlay_lang=job.lang,
                                     overlay_script=script_of(job.lang),
                                     text=seg.text,
                                     keyword_ids=seg.mapped_keyword_ids)
            elif seg.kind == 'paragraph':
                upsert_paragraph_overlay(tx, ...)  # same shape
    update_job(job_id, status='ingested')
```

Idempotency: `upsert_*` operations key on `(shastra_natural_key, natural_key, overlay_lang)` UNIQUE pairs (column already present per spec 15's multilingual additions). A second run of the same job yields zero net inserts.

### Admin endpoints (`services/data-service/app/routers/ocr_jobs.py`)

```
POST  /admin/ocr-jobs                          body: { s3_key, lang, triggered_by? }
GET   /admin/ocr-jobs?status=&page=
GET   /admin/ocr-jobs/{id}
GET   /admin/ocr-jobs/{id}/pages?low_conf=true
POST  /admin/ocr-jobs/{id}/pages/{page_no}/override   body: { manual_override }
POST  /admin/ocr-jobs/{id}/ingest              body: { shastra_natural_key }
POST  /admin/ocr-jobs/{id}/cancel
GET   /admin/keyword-aliases?status=draft&lang=kn
POST  /admin/keyword-aliases/{id}/approve
POST  /admin/keyword-aliases/{id}/reject
```

All gated by `require_role('reviewer','admin')`.

## Tests (TDD — write first)

1. `test_ocr_golden_image.py` — feed `golden_kn_page.png` through the Tesseract wrapper; output text matches `golden_kn_text.txt` (after normalisation) within a Levenshtein ratio ≥ 0.97; mean confidence > 0.8.
2. `test_kn_gu_unicode_normalisation.py` — given a Kannada string with stray `‌` / `‍` between consonant-halant pairs, `normalise_text` strips them; the output is bit-equal to the hand-curated NFC reference. Same for a Gujarati nukta fixture.
3. `test_alias_mapping_fuzz_threshold.py` — seed `alias_seed.sql` with one approved Kn alias `ಆತ್ಮ` → canonical `keywords.<आत्मा>`. `map_surface('ಆತ್ಮ', lang='kn', script='Knda')` returns `source='exact', confidence=1.0`. `map_surface('ಆತ್ಮಾ', ...)` (extra `ಾ`) returns `source='fuzzy', confidence>=0.86`, draft alias inserted. Surface below threshold (`'ಆಕಾಶ'`) returns `keyword_id=None, source='none'`.
4. `test_ingestion_idempotency.py` — run `ingest_doc` for a 3-page tiny job → 1 adhikaar + 5 gathas inserted. Run again → row counts unchanged; no duplicate overlay entries in `gathas.text_multilingual`.
5. `test_gvision_fallback_on_low_confidence.py` — stub Tesseract to return `mean_conf=0.5`; stub GVision to return `mean_conf=0.9` with different text → `ocr_pages.chosen_source='gvision'`, `normalised_text` derived from GVision's output. With both stubs below threshold → `chosen_source='tesseract'` (the higher of the two) and page is flagged `low_conf`.
6. `test_job_status_transitions.py` — a job moves `pending → running → review → ingested` exactly once; cancelling mid-run sets `cancelled` and no further page tasks process.
7. `test_admin_endpoint_role_gate.py` — guest/user get 401/403, reviewer gets 200.

## Manual verification

```bash
# 1. Apply migrations
alembic upgrade head

# 2. Upload a sample PDF to dev S3
aws s3 cp samples/samaysaar_kn.pdf s3://saar-dev/ocr/samaysaar_kn.pdf

# 3. Enqueue
curl -X POST -H 'authorization: Bearer <admin>' -H 'content-type: application/json' \
  -d '{"s3_key":"ocr/samaysaar_kn.pdf","lang":"kn"}' \
  http://localhost:8001/admin/ocr-jobs

# 4. Watch progress
watch -n 2 'psql -c "SELECT id, status, pages_done, pages_total, pages_low_conf FROM ocr_jobs ORDER BY created_at DESC LIMIT 3;"'

# 5. Inspect low-confidence pages
curl -H 'authorization: Bearer <reviewer>' \
  'http://localhost:8001/admin/ocr-jobs/<id>/pages?low_conf=true'

# 6. Override one
curl -X POST -H 'authorization: Bearer <reviewer>' \
  -d '{"manual_override":"<corrected NFC text>"}' \
  http://localhost:8001/admin/ocr-jobs/<id>/pages/12/override

# 7. Approve draft aliases produced by the fuzzy mapper
curl 'http://localhost:8001/admin/keyword-aliases?status=draft&lang=kn'
curl -X POST -H 'authorization: Bearer <reviewer>' \
  http://localhost:8001/admin/keyword-aliases/<alias_id>/approve

# 8. Ingest into the data model
curl -X POST -H 'authorization: Bearer <reviewer>' \
  -d '{"shastra_natural_key":"samaysaar:kn"}' \
  http://localhost:8001/admin/ocr-jobs/<id>/ingest

# 9. Verify multilingual entries landed
psql -c "SELECT natural_key, label_multilingual FROM keywords
         WHERE label_multilingual @> '[{\"lang\":\"kn\"}]'::jsonb LIMIT 10;"
psql -c "SELECT g.natural_key, g.text_multilingual
         FROM gathas g WHERE g.shastra_id =
           (SELECT id FROM shastras WHERE natural_key='samaysaar:kn') LIMIT 5;"
```

## Definition of done

- [ ] Migrations `0035_ocr_pipeline.py` and `0036_keyword_alias_multilingual.py` apply clean.
- [ ] All 7 tests pass.
- [ ] Tesseract + Google Vision both invoked end-to-end on the demo PDF; fallback observable in `ocr_pages.chosen_source`.
- [ ] Kn/Gu surfaces map to canonical Hindi keywords with ≥ 80% mapper hit-rate on the demo corpus (exact + vitrag + approved-fuzzy).
- [ ] Ingest produces `label_multilingual` entries with `lang in {kn,gu}` for every mapped keyword and `text_multilingual` overlays on gathas.
- [ ] Re-ingesting the same job is a no-op.
- [ ] Reviewer can override a low-confidence page and approve a draft alias in < 10 clicks.

## Implementation notes

_(to be filled in after merge)_
