# 05 — Drush-taant Image Generation Spec

Scope context: [`scope/03_shastra_reader.md`](../../scope/03_shastra_reader.md) (Drush-taant section), open question Q5 in [`scope/09_open_questions.md`](../../scope/09_open_questions.md).

A drush-taant in a Jain teeka is a worldly analogy. For every gatha with a bhaavarth we can generate one illustrative image. Pipeline:

1. LLM rewrites bhaavarth → safe image prompt.
2. Image provider generates the picture; blob → S3.
3. Admin reviews; on approval the row is published.
4. Reader renders the image inside the `drushtaant` panel (spec 03).

All artefacts are reproducible: `(provider, model, prompt, seed, ts)` recorded per [`scope/09 Q24`](../../scope/09_open_questions.md).

Depends on:
- The `gathas` table from [`02_data_model_postgres.md`](../data_model/02_data_model_postgres.md).
- The `<DrushtaantPanel>` slot defined in [`03_shastra_reader_ui_spec.md`](./03_shastra_reader_ui_spec.md).
- The Mongo `teeka_gatha_mapping` collection from [`03_data_model_mongo.md`](../data_model/03_data_model_mongo.md) (source of the bhaavarth text).
- Auth role gating from [`01_user_accounts_spec.md`](./01_user_accounts_spec.md).

## Phase A — generation worker

### Files

```
workers/enrichment/drushtaant/
├── __init__.py
├── tasks.py              # Celery: gen_drushtaant_for_gatha(gatha_id), retry policy
├── prompt_builder.py     # build_prompt(bhaavarth: str, gatha_meta: dict) -> ImagePrompt
├── providers/
│   ├── base.py           # ImageProvider protocol
│   ├── openai_image.py   # gpt-image-1 / dall-e-3
│   ├── stability.py      # SDXL via Stability API
│   └── google_imagen.py
├── safety.py             # safety_filter(prompt) — strict deny list
├── storage.py            # upload_to_s3(blob), put_mongo_doc(...)
└── tests/
    ├── test_prompt_builder.py
    ├── test_safety_filter.py
    ├── test_provider_dispatch.py
    ├── test_idempotent_generation.py
    └── test_budget_cap.py
```

### Postgres schema (migration `0021_drushtaant_jobs.py`)

```sql
CREATE TYPE drushtaant_status AS ENUM (
  'queued','generating','pending_review','approved','rejected','failed'
);

CREATE TABLE drushtaant_jobs (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  gatha_id        UUID NOT NULL REFERENCES gathas(id) ON DELETE CASCADE,
  status          drushtaant_status NOT NULL DEFAULT 'queued',
  provider        TEXT NOT NULL,                 -- 'openai_image' | 'stability' | 'google_imagen'
  model           TEXT NOT NULL,                 -- e.g. 'gpt-image-1', 'sdxl-1.0', 'imagen-3'
  prompt          TEXT NOT NULL,                 -- final image-gen prompt
  seed            BIGINT,                        -- if provider supports
  blob_url        TEXT,                          -- s3://bucket/key (set after success)
  thumbnail_url   TEXT,                          -- s3://...
  width_px        INT,
  height_px       INT,
  cost_usd        NUMERIC(10,4),                 -- per-call cost (best-effort)
  triggered_by    UUID REFERENCES users(id),
  reviewed_by     UUID REFERENCES users(id),
  reviewed_at     TIMESTAMPTZ,
  reject_reason   TEXT,
  error           TEXT,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_drushtaant_status ON drushtaant_jobs(status);
CREATE INDEX idx_drushtaant_gatha ON drushtaant_jobs(gatha_id);

-- one approved image per (gatha) acts as the published image
CREATE UNIQUE INDEX idx_drushtaant_one_approved_per_gatha
  ON drushtaant_jobs(gatha_id) WHERE status = 'approved';
```

### Mongo collection (`drushtaant_images`)

Added to [`03_data_model_mongo.md`](../data_model/03_data_model_mongo.md) catalogue:

```json
{
  "_id": "<stable_id from natural_key>",
  "natural_key": "drushtaant:samaysaar:039:v1",
  "gatha_natural_key": "samaysaar:039",
  "job_id": "<uuid from drushtaant_jobs>",
  "provider": "openai_image",
  "model": "gpt-image-1",
  "prompt": "...",
  "seed": 12345,
  "blob_url": "s3://saar-drushtaant/samaysaar/039/v1.png",
  "thumbnail_url": "s3://saar-drushtaant/samaysaar/039/v1_thumb.webp",
  "captions": [
    {"lang": "hi", "text": "..."},
    {"lang": "en", "text": "..."}
  ],
  "reviewed_at": ISODate("..."),
  "created_at": ISODate("...")
}
```

Indexes: `{natural_key: 1}` UNIQUE; `{gatha_natural_key: 1}`.

### Pipeline (`tasks.py`)

```python
@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
async def gen_drushtaant_for_gatha(self, gatha_id: str, *, triggered_by: str | None = None):
    async with get_session() as s:
        gatha = await load_gatha_with_bhaavarth(s, gatha_id)
        if not gatha.bhaavarth_text:
            return _record_failure(s, gatha_id, "no_bhaavarth")

        # 1) Build prompt (LLM rewrite)
        prompt = await prompt_builder.build_prompt(gatha)
        if not safety.passes(prompt):
            return _record_failure(s, gatha_id, "safety_filter_blocked")

        # 2) Budget gate
        if await month_cost_exceeds_cap(s, settings.DRUSHTAANT_MONTHLY_USD_CAP):
            raise self.retry(countdown=3600)        # retry hourly until next month

        # 3) Provider call
        job = await create_job_row(s, gatha_id, prompt, triggered_by)
        provider = providers.get(settings.DRUSHTAANT_PROVIDER)
        result = await provider.generate(prompt, seed=settings.DRUSHTAANT_SEED)

        # 4) Store
        await storage.upload(job, result)
        await mark_pending_review(s, job.id)
```

### Prompt skeleton (`prompt_builder.py`)

```python
PROMPT_TEMPLATE = """
You are illustrating a Jain shastra commentary for a respectful, scholarly audience.

Bhaavarth (Hindi): {bhaavarth}
Gatha context: shastra={shastra}, gatha_number={n}, heading={heading_hi}

Write ONE concise English image-generation prompt (< 60 words) that:
- Depicts ONLY the *worldly analogy* (drushtaant), never any Tirthankar, Siddha,
  Acharya, deity, or sacred symbol.
- Uses traditional Indian / dharmic visual language (e.g. lotus pond, river,
  potter at wheel, lamp & flame, cloud & mountain).
- Specifies medium ("watercolor on handmade paper, soft natural light").
- Avoids text, calligraphy, idols, faces of saints, religious iconography.
- Avoids violence, gore, sensual or political content.

Return JSON: { "image_prompt": "...", "caption_hi": "...", "caption_en": "..." }
"""
```

The rewrite uses the `llm_call` abstraction (see [`scope/09 Q23`](../../scope/09_open_questions.md)) so model selection (Anthropic/OpenAI/finetuned) is configurable. JSON-mode required.

### Safety filter (`safety.py`)

Hard deny list applied to BOTH the rewritten prompt and the gatha title:

```python
DENY_PHRASES = {
    "tirthankar","siddha","arihant","kevali","jina","jin idol","jain temple idol",
    "depict the lord","depict god","draw bhagwan","face of mahavir",
    "nude","sexual","erotic","blood","gore","weapon used to kill",
    # extend in deny_list.yaml
}
```

If any phrase appears (case-insensitive, ASCII-folded), `passes()` returns `False` and the job records `error="safety_filter_blocked"`. Per Q5: drush-taant images **must not** depict Tirthankars / Siddhas / idols.

### Budget cap

`DRUSHTAANT_MONTHLY_USD_CAP` env var. `month_cost_exceeds_cap` sums `cost_usd` of all jobs this month; if ≥ cap, task retries with 1h backoff so manual review can raise the cap or wait for month rollover.

### Reproducibility

`drushtaant_jobs.{provider, model, prompt, seed}` + `created_at` is the reproducibility tuple. Re-running the same gatha produces a new row (v2, v3, …) — never overwrites.

### Tests (Phase A — TDD)

1. `test_prompt_builder.py::test_excludes_tirthankar_terms` — bhaavarth containing "तीर्थंकर" yields a prompt that does NOT include the term (LLM stub returns sanitised template).
2. `test_safety_filter.py::test_idol_terms_blocked` — `"a temple idol of mahavir"` → blocked.
3. `test_safety_filter.py::test_neutral_analogy_passes` — `"watercolor of a lotus rising from muddy water"` → passes.
4. `test_provider_dispatch.py::test_provider_switch_via_env` — `DRUSHTAANT_PROVIDER=stability` → `StabilityProvider.generate` called.
5. `test_idempotent_generation.py::test_failed_job_can_be_retried` — first call fails (safety), second call with edited prompt succeeds; both rows present.
6. `test_idempotent_generation.py::test_only_one_approved_per_gatha` — approve job A, try to approve job B for same gatha → 409.
7. `test_budget_cap.py::test_over_cap_raises_retry` — set cap to 0.01, simulate $1 spent this month → task retries; row stays `queued`.

## Phase B — admin review UI

### Files

```
ui/app/admin/drushtaant-review/
├── page.tsx                  # paginated list of pending_review jobs
├── [job_id]/page.tsx         # side-by-side: gatha+bhaavarth vs generated image
├── ApprovalActions.tsx       # Approve / Reject (with reason) / Regenerate
└── tests/
    └── e2e_review_flow.spec.ts
```

### API endpoints (on data-service or new admin sub-router)

```
GET    /admin/drushtaant/jobs?status=pending_review&limit=50
GET    /admin/drushtaant/jobs/{id}
POST   /admin/drushtaant/jobs/{id}/approve         body: {}                          -> {ok}
POST   /admin/drushtaant/jobs/{id}/reject          body: {reason}                    -> {ok}
POST   /admin/drushtaant/jobs/{id}/regenerate      body: {prompt_override?, seed?}   -> {new_job_id}
```

All `/admin/drushtaant/*` require `require_role("admin","reviewer")`.

On approval:
1. Set `status='approved'`, `reviewed_by`, `reviewed_at`.
2. Upsert `drushtaant_images` Mongo doc with stable id.
3. Bust the public CDN cache for the gatha unit URL.

### UI page

Two columns:

- Left: rendered bhaavarth (read-only `<BhaavarthPanel>`), gatha header, prompt + model + seed.
- Right: image preview (full + thumbnail), Approve / Reject / Regenerate buttons; reject opens a reason textarea (free-form).

### Tests (Phase B)

1. `test_admin_approve_endpoint.py::test_approve_creates_mongo_doc` — approve job → Mongo `drushtaant_images` document exists with matching `job_id`.
2. `test_admin_reject_endpoint.py::test_reject_sets_reason` — reason persisted; status flips.
3. `test_admin_regenerate.py::test_regenerate_queues_new_job` — regenerate → new row with `status=queued`, original untouched.
4. Playwright `e2e_review_flow.spec.ts::approve_publishes_to_reader` — approve in admin → public reader URL renders the image.

## Phase C — reader integration

### `<DrushtaantPanel>` behaviour

- Server fetches `unit.drushtaant` (from `UnitPayload` in spec 03). When present, renders the image (Next `<Image>` with `s3://` → CDN URL rewrite) + caption in selected `lang`.
- When absent:
  - Guest / regular user → renders empty (panel may be collapsed by default per `layout.drushtaant.visible_default`).
  - Admin / reviewer → renders a "Generate" button that POSTs to `/admin/drushtaant/jobs` for this gatha and toasts the job id.
- Provenance footer: "AI-generated, admin-approved on YYYY-MM-DD" (see [`14_public_ui.md`](../archived/14_public_ui.md) provenance footer pattern).

### API endpoint (already in spec 03)

`unit.drushtaant` field of `UnitPayload`:

```python
class DrushtaantImage(BaseModel):
    natural_key: str
    image_url: str                # CDN URL (signed or public)
    thumbnail_url: str
    width_px: int
    height_px: int
    caption_hi: str | None
    caption_en: str | None
    approved_at: datetime
```

Built from `drushtaant_images` joined with the approved row in `drushtaant_jobs`.

### Tests (Phase C)

1. `test_unit_payload_includes_drushtaant.py::test_approved_image_appears` — approve fixture job → `GET /v1/shastras/.../units/...` includes `drushtaant`.
2. `test_unit_payload_excludes_pending.py::test_pending_image_hidden_from_public` — pending → `drushtaant: null`.
3. Playwright `drushtaant_renders.spec.ts::shows_image_for_approved_gatha` — visit reader URL, image visible.

## Configuration

```bash
DRUSHTAANT_PROVIDER=openai_image          # openai_image | stability | google_imagen
DRUSHTAANT_MODEL=gpt-image-1
DRUSHTAANT_MONTHLY_USD_CAP=50
DRUSHTAANT_SEED=                           # blank for non-deterministic
S3_BUCKET_DRUSHTAANT=saar-drushtaant
S3_REGION=ap-south-1
LLM_PROMPT_REWRITER_MODEL=anthropic:claude-3-5-sonnet
```

## Manual verification

```bash
# Trigger generation for one gatha
celery -A workers call workers.enrichment.drushtaant.tasks.gen_drushtaant_for_gatha \
       --args='["<gatha_id>"]'

# Tail job
psql -c "SELECT id, status, error FROM drushtaant_jobs ORDER BY created_at DESC LIMIT 5;"

# Review
open http://localhost:3000/admin/drushtaant-review

# Approve and verify on the reader
open http://localhost:3000/shastra-explorer/samaysaar/adhikaar/1/gatha/039
```

## Definition of done

- [ ] Migration `0021_drushtaant_jobs.py` applied.
- [ ] `drushtaant_images` Mongo collection + indexes set up via `ensure_indexes()`.
- [ ] Safety filter blocks at least the listed deny phrases (unit tests green).
- [ ] One approved drushtaant image renders in `<DrushtaantPanel>` for samaysaar gatha 039.
- [ ] Reject + regenerate flow produces a new job; old row remains.
- [ ] Budget cap enforced; over-cap task retries instead of charging.
- [ ] All listed tests pass.

## Implementation notes

_(to be filled in after merge)_
