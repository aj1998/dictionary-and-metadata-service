# 07 — PDF Export Spec

Scope context: [`scope/03_shastra_reader.md`](../../scope/03_shastra_reader.md#pdf-export).

Server-side PDF rendering of a shastra unit (single leaf), a chapter / adhikaar range, or a whole shastra, triggered from the Shastra Reader's right-rail export menu (see [`03_shastra_reader_ui_spec.md`](./03_shastra_reader_ui_spec.md#right-rail)). Async job model: the API enqueues a Celery task, the worker renders HTML → PDF via WeasyPrint, uploads the blob to S3, and the UI polls / downloads via a signed URL.

WeasyPrint is chosen over Playwright headless print for: (a) deterministic output for content-hash caching, (b) much lower memory footprint per render, (c) first-class CSS Paged Media support (running headers, page numbers, TOC anchors), (d) no Chromium dependency in the worker image. The trade-off — no JS execution at render time — is acceptable because the export endpoint hits the existing data-service unit endpoints server-side and renders fully static HTML.

Depends on:
- [`01_user_accounts_spec.md`](./01_user_accounts_spec.md) for `current_user_optional` and role gating on private content.
- [`02_shastra_layout_configs_spec.md`](./02_shastra_layout_configs_spec.md) for resolving the panel order for the rendered template.
- [`03_shastra_reader_ui_spec.md`](./03_shastra_reader_ui_spec.md) for the unit payload contract (`UnitPayload`).
- [`05_drushtaant_image_gen_spec.md`](./05_drushtaant_image_gen_spec.md) for the drushtaant image URL contract (when `include_drushtaant=true`).

## Goal

A user (or a guest, for public shastras) can request a PDF export of any one of: a single unit, a contiguous chapter range, or a whole shastra. The request is asynchronous, deduplicated by a content hash, and the resulting PDF is downloadable via a signed S3 URL. Devanagari renders correctly with embedded Noto Sans Devanagari + Noto Serif Devanagari fonts.

## Module paths

```
services/data-service/app/routers/pdf.py          # job CRUD + download redirect
services/data-service/app/services/pdf_jobs.py    # job orchestration, content-hash, S3 keys
workers/pdf_export_worker/
├── __init__.py
├── main.py                                       # Celery app wiring + task entrypoint
├── render.py                                     # build HTML → WeasyPrint → bytes
├── templates/
│   ├── base.html                                 # @page rules, fonts, page numbers
│   ├── unit.html                                 # one leaf unit (all visible panels)
│   ├── range.html                                # adhikaar / chapter range
│   ├── shastra.html                              # whole shastra
│   └── partials/
│       ├── breadcrumb.html
│       ├── panel_prakrit.html
│       ├── panel_sanskrit_chhaaya.html
│       ├── panel_hindi_chhand.html
│       ├── panel_anvayartha.html
│       ├── panel_bhaavarth.html
│       ├── panel_drushtaant.html
│       ├── panel_glossary.html
│       └── toc.html
├── fonts/
│   ├── NotoSansDevanagari-Regular.ttf
│   ├── NotoSansDevanagari-Bold.ttf
│   ├── NotoSerifDevanagari-Regular.ttf
│   └── NotoSerifLatin-Regular.ttf                # fallback for English-only chunks
├── css/
│   ├── print.css                                 # @page, headings, panel rules
│   └── highlights.css                            # optional JainKosh-highlight rendering
├── hashing.py                                    # canonical_payload_hash(params, snapshot_versions)
├── glossary.py                                   # build glossary entries from spans (spec 12)
└── tests/
    ├── conftest.py
    ├── fixtures/
    │   ├── samaysaar_g001_unit_payload.json
    │   └── golden_unit.pdf                       # opt-in pixel-diff target
    ├── test_create_job.py
    ├── test_worker_renders_unit_pdf.py
    ├── test_devanagari_font_fallback.py
    ├── test_content_hash_dedupe.py
    ├── test_role_gated_private_shastra.py
    └── test_download_signed_url.py

packages/jain_kb_common/db/postgres/
└── pdf_jobs.py                                   # SQLAlchemy ORM mirror
```

## Phase A — single-phase implementation

### Postgres schema (migration `0024_pdf_export_jobs.py`)

```sql
CREATE TYPE pdf_export_status AS ENUM (
  'pending', 'running', 'success', 'failed', 'cancelled'
);

CREATE TYPE pdf_export_scope AS ENUM ('unit', 'range', 'shastra');

CREATE TABLE pdf_export_jobs (
  id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id            UUID REFERENCES users(id) ON DELETE SET NULL,  -- null for guest jobs
  shastra_id         UUID NOT NULL REFERENCES shastras(id) ON DELETE CASCADE,
  scope              pdf_export_scope NOT NULL,
  params             JSONB NOT NULL,                  -- see ExportParams below
  content_hash       TEXT NOT NULL,                   -- sha256 of canonical payload
  status             pdf_export_status NOT NULL DEFAULT 'pending',
  s3_bucket          TEXT,
  s3_key             TEXT,                            -- 'pdf-exports/{content_hash}.pdf'
  page_count         INT,
  byte_size          BIGINT,
  error              TEXT,
  celery_task_id     TEXT,
  started_at         TIMESTAMPTZ,
  finished_at        TIMESTAMPTZ,
  expires_at         TIMESTAMPTZ,                     -- S3 lifecycle delete target (90 d)
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_pdf_jobs_user        ON pdf_export_jobs(user_id);
CREATE INDEX idx_pdf_jobs_shastra     ON pdf_export_jobs(shastra_id);
CREATE INDEX idx_pdf_jobs_status      ON pdf_export_jobs(status);
CREATE UNIQUE INDEX uq_pdf_jobs_hash  ON pdf_export_jobs(content_hash)
  WHERE status IN ('pending','running','success');
```

The partial UNIQUE on `content_hash` is the dedupe primitive: two simultaneous requests with the same canonical payload collapse into the same row. A `failed`/`cancelled` job releases the slot, so the next request triggers a fresh render.

### Canonical content hash

```python
# workers/pdf_export_worker/hashing.py
def canonical_payload_hash(*, shastra_natural_key: str, scope: str,
                           params: dict, snapshot_versions: dict) -> str:
    """
    snapshot_versions = {
        "layout_version":      str,   # layout config rev
        "unit_payload_hash":   str,   # sha256 of UnitPayload JSON when scope=unit
        "range_payload_hash":  str,   # sha256 of concatenated unit hashes for the range
        "drushtaant_hashes":   list,  # included only when include_drushtaant=true
        "glossary_hash":       str,   # included only when include_glossary=true
        "spans_hash":          str,   # spec 08; included when include_highlights=true
        "fonts_version":       "v1",
    }
    """
    blob = {
        "v": 1,
        "shastra": shastra_natural_key,
        "scope": scope,
        "params": _canonical(params),
        "snap": _canonical(snapshot_versions),
    }
    return hashlib.sha256(
        json.dumps(blob, sort_keys=True, ensure_ascii=False, separators=(",", ":")
                  ).encode("utf-8")
    ).hexdigest()
```

The same `(shastra, scope, params)` tuple with the same upstream content always yields the same hash → same `s3_key` → S3 already has the blob → worker skips render and the job row points at the existing object.

### Pydantic contracts (`services/data-service/app/routers/pdf.py`)

```python
class ChapterRange(BaseModel):
    """Inclusive range of top-level chapter/adhikaar/parva indices."""
    from_index: int = Field(ge=1)
    to_index: int = Field(ge=1)

    @model_validator(mode='after')
    def _ordered(self):
        if self.to_index < self.from_index:
            raise ValueError("to_index must be >= from_index")
        return self

class ExportParams(BaseModel):
    shastra_id: UUID
    scope: Literal['unit', 'range', 'shastra']
    leaf_natural_key: str | None = None          # required when scope == 'unit'
    chapter_range: ChapterRange | None = None    # required when scope == 'range'
    lang: Literal['hi', 'en'] = 'hi'
    panels: list[str] | None = None              # optional override; default = layout panels
    include_drushtaant: bool = False
    include_glossary: bool = True
    include_highlights: bool = False             # render JainKosh-highlight underlines
    page_size: Literal['A4', 'Letter'] = 'A4'

    @model_validator(mode='after')
    def _scope_consistent(self):
        if self.scope == 'unit' and not self.leaf_natural_key:
            raise ValueError("leaf_natural_key required for scope='unit'")
        if self.scope == 'range' and not self.chapter_range:
            raise ValueError("chapter_range required for scope='range'")
        return self

class PdfJobOut(BaseModel):
    id: UUID
    status: Literal['pending','running','success','failed','cancelled']
    scope: str
    params: ExportParams
    page_count: int | None
    byte_size: int | None
    error: str | None
    download_url: str | None                     # set when status='success'
    created_at: datetime
    updated_at: datetime
```

### Endpoints

```
POST   /v1/pdf/jobs                              # create or dedupe; returns PdfJobOut (202 if new, 200 if existing)
GET    /v1/pdf/jobs/{job_id}                     # status poll
GET    /v1/pdf/jobs/{job_id}/download            # 302 → signed S3 URL (5 min TTL)
GET    /v1/pdf/jobs?mine=true&limit=20           # auth required; lists user's recent jobs
DELETE /v1/pdf/jobs/{job_id}                     # cancel pending; admins can cancel any
```

Role gating (via `current_user_optional` from spec 01):
- Public shastras (`shastras.visibility='public'`): guest or user can export.
- Private shastras (`visibility='restricted'`): require `role in {user, reviewer, admin}`.
- Whole-shastra export of any shastra requires `role in {user, reviewer, admin}` (rate-limited to 3 concurrent per user).
- `mine=true` listing and `DELETE` always require auth.

Per-user rate limit on `POST /v1/pdf/jobs`: 30 jobs / 24 h for `user`, unlimited for `admin`. Enforced via the existing `packages/jain_kb_common/ratelimit/` middleware.

### Router skeleton

```python
# services/data-service/app/routers/pdf.py
router = APIRouter(prefix="/v1/pdf", tags=["pdf"])

@router.post("/jobs", response_model=PdfJobOut)
async def create_job(
    params: ExportParams,
    user: User | None = Depends(current_user_optional),
    session: AsyncSession = Depends(get_session),
):
    await _enforce_export_permissions(session, params, user)
    snapshot = await pdf_jobs.collect_snapshot_versions(session, params)
    content_hash = canonical_payload_hash(
        shastra_natural_key=snapshot["shastra_nk"],
        scope=params.scope,
        params=params.model_dump(mode="json", exclude={"shastra_id"}),
        snapshot_versions=snapshot["versions"],
    )
    job, created = await pdf_jobs.create_or_attach(
        session, params=params, user=user, content_hash=content_hash,
    )
    if created and job.status == "pending":
        celery.send_task("pdf_export.render_job", args=[str(job.id)])
    return PdfJobOut.from_orm_with_url(job)
```

`create_or_attach` semantics:
1. If a `success` row exists for `content_hash` → return that row unchanged (no Celery dispatch).
2. If a `pending`/`running` row exists → return it (caller polls).
3. Else insert new `pending` row.

The partial UNIQUE makes step 3 atomic; on conflict we fall through to step 1 or 2.

### Worker entry point

```python
# workers/pdf_export_worker/main.py
@celery_app.task(bind=True, name="pdf_export.render_job",
                 autoretry_for=(TransientRenderError,), retry_backoff=True,
                 max_retries=3, acks_late=True)
def render_job(self, job_id: str) -> dict:
    with span("pdf_export.render_job", job_id=job_id):
        job = pg.get_job(job_id)
        try:
            pg.mark_running(job_id, task_id=self.request.id)

            # short-circuit if blob already in S3 from a previous run
            s3_key = f"pdf-exports/{job.content_hash}.pdf"
            if s3.exists(BUCKET, s3_key):
                pg.mark_success(job_id, s3_key=s3_key,
                                page_count=None, byte_size=s3.head(BUCKET, s3_key).size)
                return {"status": "cache_hit", "s3_key": s3_key}

            html = render.build_html(job)
            pdf_bytes, page_count = render.html_to_pdf(html)
            s3.put(BUCKET, s3_key, pdf_bytes,
                   content_type="application/pdf",
                   metadata={"content-hash": job.content_hash})
            pg.mark_success(job_id, s3_key=s3_key,
                            page_count=page_count, byte_size=len(pdf_bytes),
                            expires_at=now() + timedelta(days=90))
            return {"status": "rendered", "s3_key": s3_key, "page_count": page_count}
        except Exception as exc:
            pg.mark_failed(job_id, error=str(exc)[:2000])
            raise
```

### HTML → PDF renderer

```python
# workers/pdf_export_worker/render.py
def build_html(job: PdfExportJob) -> str:
    params = ExportParams.model_validate(job.params)
    layout = data_service.fetch_layout(params.shastra_id)
    panels = params.panels or [p.kind for p in layout.panels if p.visible_default]

    if params.scope == "unit":
        unit = data_service.fetch_unit(params.shastra_id, params.leaf_natural_key,
                                       lang=params.lang)
        ctx = {"unit": unit, "panels": panels, "params": params, "layout": layout}
        if params.include_glossary:
            ctx["glossary"] = build_glossary([unit])
        return _jinja.get_template("unit.html").render(**ctx)
    elif params.scope == "range":
        units = data_service.fetch_range(params.shastra_id, params.chapter_range,
                                         lang=params.lang)
        ctx = {"units": units, "panels": panels, "params": params, "layout": layout,
               "toc": build_toc(units)}
        if params.include_glossary:
            ctx["glossary"] = build_glossary(units)
        return _jinja.get_template("range.html").render(**ctx)
    else:  # 'shastra'
        units = data_service.fetch_all_units(params.shastra_id, lang=params.lang)
        return _jinja.get_template("shastra.html").render(
            units=units, panels=panels, params=params, layout=layout,
            toc=build_toc(units),
            glossary=build_glossary(units) if params.include_glossary else None,
        )

def html_to_pdf(html: str) -> tuple[bytes, int]:
    css = [CSS(filename=str(STATIC_DIR / "css" / "print.css")),
           CSS(filename=str(STATIC_DIR / "css" / "highlights.css"))]
    fontconfig = FontConfiguration()
    _register_devanagari_fonts(fontconfig)
    document = HTML(string=html, base_url=str(STATIC_DIR)).render(
        stylesheets=css, font_config=fontconfig, presentational_hints=False,
    )
    buf = io.BytesIO()
    document.write_pdf(target=buf)
    return buf.getvalue(), len(document.pages)
```

`_register_devanagari_fonts` declares `@font-face` rules pointing at the bundled TTFs so WeasyPrint embeds them as Type-3 subsets. The same `fonts_version` literal is included in the content hash; updating fonts forces a re-render of every cached export.

### Glossary builder

When `include_glossary=true`, the worker pulls approved spans for the in-scope units from the `spans` endpoint (spec 12) and emits a sorted, deduplicated appendix:

```
{
  "entries": [
    {"display_text": "आत्मा", "english": "Soul",
     "definition_excerpt": "...", "ref_label": "JainKosh: आत्मा"},
    ...
  ]
}
```

Sort order: Devanagari Unicode collation (`pyicu.Collator.createInstance(Locale('hi_IN'))`), one entry per distinct `entity_natural_key`.

### CSS for paged output

`print.css` essentials (excerpt):

```css
@page {
  size: A4;
  margin: 22mm 18mm 22mm 18mm;
  @top-left  { content: string(shastra-title); font-size: 9pt; color: #555; }
  @top-right { content: string(unit-breadcrumb); font-size: 9pt; color: #555; }
  @bottom-center { content: counter(page) " / " counter(pages); font-size: 9pt; }
}
h1.shastra-title { string-set: shastra-title content(); }
.breadcrumb       { string-set: unit-breadcrumb content(); }

body { font-family: "Noto Serif Devanagari", "Noto Serif", serif; font-size: 11.5pt; }
.lang-en { font-family: "Noto Serif", serif; }
.panel { break-inside: avoid-page; margin-bottom: 1.2em; }
.panel > h3 { font-family: "Noto Sans Devanagari", "Noto Sans", sans-serif; }
.toc a::after { content: leader(".") target-counter(attr(href), page); }
```

`highlights.css` is loaded only when `include_highlights=true`; it mirrors the colour palette from spec 12 but renders as solid underlines (no hover state).

### S3 layout

```
s3://saar-pdf-exports/
└── pdf-exports/
    └── {content_hash}.pdf       # immutable, content-addressed
```

Object metadata stores `content-hash`, `created-by-job`, `shastra-natural-key`. Bucket lifecycle rule deletes objects 90 days after creation (mirrored by the `expires_at` column).

Signed download URLs: `s3.generate_presigned_url('get_object', ..., ExpiresIn=300)` with `ResponseContentDisposition='attachment; filename="<shastra>_<scope>.pdf"'`.

### Tests (TDD — write these first)

1. `test_create_job.py::creates_pending_row_and_dispatches_task` — POST → 202, row `status='pending'`, Celery `send_task` called once.
2. `test_create_job.py::reuses_success_row_for_same_hash` — same params → second POST returns the first job's id, no Celery dispatch.
3. `test_create_job.py::reuses_pending_row_for_same_hash` — second POST during in-flight render returns the same id.
4. `test_create_job.py::failed_job_releases_hash_slot` — failed row → next POST creates a fresh `pending` row.
5. `test_worker_renders_unit_pdf.py::renders_minimal_unit` — stub data-service with `samaysaar_g001_unit_payload.json`; assert `render_job` writes a valid PDF to S3, page count ≥ 1, mark `success`.
6. `test_devanagari_font_fallback.py::embeds_noto_devanagari` — render a unit; PDF stream contains `/FontName .*NotoSansDevanagari` and `/Encoding /Identity-H`; ASCII-only block uses NotoSerifLatin.
7. `test_content_hash_dedupe.py::same_inputs_same_hash` — call `canonical_payload_hash` twice with same params, expect equal; flip `include_drushtaant` → different hash.
8. `test_content_hash_dedupe.py::param_order_irrelevant` — pass `panels=['a','b']` vs `panels=['b','a']` → semantically equal panel sets must produce equal hash (canonicaliser sorts panel list).
9. `test_role_gated_private_shastra.py::guest_blocked_for_restricted` — restricted shastra, no JWT → 403; `user` JWT → 202.
10. `test_role_gated_private_shastra.py::whole_shastra_requires_auth` — `scope='shastra'` as guest → 403.
11. `test_download_signed_url.py::redirects_on_success` — GET `/jobs/{id}/download` on `success` job → 302 with presigned URL; on `pending` → 409.
12. `test_download_signed_url.py::cache_hit_short_circuits_render` — pre-seed S3 with `{hash}.pdf`; new job for same hash → worker logs `cache_hit`, no `html_to_pdf` call.
13. `test_create_job.py::rate_limit_per_user` — 31st POST in 24 h as `user` → 429.
14. `test_create_job.py::cancel_pending` — DELETE `/jobs/{id}` on `pending` → row `cancelled`, no Celery side effects.

### Manual verification

```bash
# 0. Migrations + services
alembic upgrade head
docker compose up -d postgres redis minio data-service pdf-export-worker

# 1. Create a single-unit export
curl -X POST http://localhost:8001/v1/pdf/jobs \
  -H 'content-type: application/json' \
  -b cookies.txt \
  -d '{
    "shastra_id": "00000000-0000-0000-0000-000000000001",
    "scope": "unit",
    "leaf_natural_key": "samaysaar:001",
    "lang": "hi",
    "include_drushtaant": false,
    "include_glossary": true
  }'
# → { "id": "...", "status": "pending", ... }

# 2. Poll until success
watch -n 1 'curl -s http://localhost:8001/v1/pdf/jobs/<id> | jq .status'

# 3. Download
curl -L -o samaysaar_g001.pdf http://localhost:8001/v1/pdf/jobs/<id>/download
open samaysaar_g001.pdf   # Devanagari renders, page header shows breadcrumb

# 4. Re-post same params — should return existing job, no new render
curl -X POST http://localhost:8001/v1/pdf/jobs -d '...'   # same body

# 5. Range export
curl -X POST http://localhost:8001/v1/pdf/jobs -d '{
  "shastra_id": "...", "scope": "range",
  "chapter_range": {"from_index": 1, "to_index": 2},
  "include_glossary": true
}'

# 6. List my recent jobs
curl http://localhost:8001/v1/pdf/jobs?mine=true -b cookies.txt | jq

# 7. Inspect cache reuse
psql -c "SELECT id, status, content_hash, s3_key FROM pdf_export_jobs ORDER BY created_at DESC LIMIT 5;"
```

## Definition of done

- [ ] Migration `0024_pdf_export_jobs.py` applies clean.
- [ ] All 14 tests pass.
- [ ] Devanagari renders correctly on samaysaar gatha 001 (visual check) with embedded Noto fonts.
- [ ] Same canonical payload → identical `content_hash` → exactly one S3 object across N POSTs.
- [ ] Guest can export a public unit; cannot export a private shastra; cannot export whole-shastra scope.
- [ ] Worker handles cache hits without re-running WeasyPrint.
- [ ] Per-user rate limit (30/24h) enforced.
- [ ] S3 lifecycle rule cleans objects ≥ 90 days; `expires_at` set on job rows.
- [ ] Right-rail export menu in the Shastra Reader (spec 03) successfully posts to `/v1/pdf/jobs` and surfaces the polling state.

## Implementation notes

_(to be filled in after merge)_
