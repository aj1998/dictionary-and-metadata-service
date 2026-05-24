# 06 — Audio Reader (ElevenLabs) Spec

Scope context: [`scope/03_shastra_reader.md`](../../scope/03_shastra_reader.md) (Audio reader section), open question Q6 in [`scope/09_open_questions.md`](../../scope/09_open_questions.md).

TTS narration per *adhikaar* (chapter unit; not per gatha). One voice per shastra, configured in the layout YAML (`audio_voice_id` — see [`02_shastra_layout_configs_spec.md`](./02_shastra_layout_configs_spec.md)). Pre-generated, stored in S3, streamed via signed URL, played by an `<AudioStrip>` pinned to the reader. Resume position persisted per user.

Depends on:
- Layout config from [`02_shastra_layout_configs_spec.md`](./02_shastra_layout_configs_spec.md).
- `user_preferences` table from [`01_user_accounts_spec.md`](./01_user_accounts_spec.md) (extending its `ui` JSONB).
- The reader `<PanelStack>` slot from [`03_shastra_reader_ui_spec.md`](./03_shastra_reader_ui_spec.md).

## Phase A — generation worker

### Files

```
workers/enrichment/audio/
├── __init__.py
├── tasks.py                # Celery: gen_audio_for_adhikaar(adhikaar_natural_key)
├── script_builder.py       # build_script(adhikaar) -> str (Hindi prose)
├── providers/
│   ├── base.py             # TTSProvider protocol
│   ├── elevenlabs.py
│   ├── murf.py
│   └── playht.py
├── storage.py              # upload_mp3_to_s3(), put_mongo_chapter_doc()
└── tests/
    ├── test_script_builder.py
    ├── test_provider_dispatch.py
    ├── test_idempotent_generation.py
    └── test_resume_position.py
```

### Postgres schema (migration `0022_audio_jobs.py`)

```sql
CREATE TYPE audio_job_status AS ENUM (
  'queued','generating','pending_review','approved','rejected','failed'
);

CREATE TABLE audio_jobs (
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  chapter_natural_key   TEXT NOT NULL,           -- e.g. "samaysaar:adhikaar:1"
  shastra_id            UUID NOT NULL REFERENCES shastras(id) ON DELETE CASCADE,
  status                audio_job_status NOT NULL DEFAULT 'queued',
  provider              TEXT NOT NULL,           -- 'elevenlabs' | 'murf' | 'playht'
  voice_id              TEXT NOT NULL,           -- e.g. 'elevenlabs:rachel-hi-v1'
  model                 TEXT,                    -- 'eleven_multilingual_v2'
  script_text           TEXT NOT NULL,
  blob_url              TEXT,                    -- s3://saar-audio/samaysaar/adhikaar-1.mp3
  duration_s            INT,
  bytes                 BIGINT,
  cost_usd              NUMERIC(10,4),
  reviewed_by           UUID REFERENCES users(id),
  reviewed_at           TIMESTAMPTZ,
  error                 TEXT,
  created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (chapter_natural_key, voice_id)
);

CREATE INDEX idx_audio_jobs_status ON audio_jobs(status);

-- one approved per chapter
CREATE UNIQUE INDEX idx_audio_jobs_one_approved_per_chapter
  ON audio_jobs(chapter_natural_key) WHERE status = 'approved';
```

### Mongo collection (`audio_chapters`)

Added to [`03_data_model_mongo.md`](../data_model/03_data_model_mongo.md) catalogue:

```json
{
  "_id": "<stable_id from natural_key>",
  "natural_key": "audio:samaysaar:adhikaar:1",
  "chapter_natural_key": "samaysaar:adhikaar:1",
  "shastra_natural_key": "samaysaar",
  "voice_id": "elevenlabs:rachel-hi-v1",
  "blob_url": "s3://saar-audio/samaysaar/adhikaar-1.mp3",
  "duration_s": 1843,
  "transcript": [
    {"lang": "hi", "text": "..."}
  ],
  "segments": [
    {"gatha_natural_key": "samaysaar:001", "start_s": 0, "end_s": 47},
    {"gatha_natural_key": "samaysaar:002", "start_s": 47, "end_s": 91}
  ],
  "job_id": "<uuid>",
  "approved_at": ISODate(...),
  "created_at": ISODate(...),
  "updated_at": ISODate(...)
}
```

`segments` enables per-gatha seek in `<AudioStrip>`. Built by aligning concatenation boundaries during script_builder.

Indexes: `{natural_key: 1}` UNIQUE; `{shastra_natural_key: 1}`.

### Script builder

```python
# workers/enrichment/audio/script_builder.py
async def build_script(session, mongo, chapter_natural_key: str) -> tuple[str, list[Segment]]:
    """
    For an adhikaar, concatenate per-gatha:
      gatha-number   "गाथा एक"
      gatha (Hindi chhand)
      brief pause SSML
      anvayartha (Hindi) — if present
      bhaavarth (one teeka, default first in layout.teeka_order) — first 500 words capped
      drushtaant caption — if approved
      transition: "आगे की गाथा..."
    Return (script, segments). Segments record gatha boundaries for seek.
    """
```

Hindi-only in v1 (per Q6 default). The script is plain text with SSML `<break time="800ms"/>` between gathas — ElevenLabs and Murf accept SSML; PlayHT supports it via API flag.

### Provider — ElevenLabs (default)

```python
# workers/enrichment/audio/providers/elevenlabs.py
class ElevenLabsProvider:
    async def synthesize(self, *, script: str, voice_id: str, model: str = "eleven_multilingual_v2") -> bytes:
        ...
```

Returns MP3 bytes (44.1 kHz, 128 kbps). One voice per shastra; the layout config carries `audio_voice_id`. Multi-voice for dialogue puraans is explicitly out of v1.

### Pipeline (`tasks.py`)

```python
@celery_app.task(bind=True, max_retries=3, default_retry_delay=120)
async def gen_audio_for_adhikaar(self, chapter_natural_key: str, *, triggered_by: str | None = None):
    layout = await load_active_layout_for_chapter(chapter_natural_key)
    voice_id = layout.audio_voice_id
    if not layout.audio_enabled or not voice_id:
        return _record_failure(chapter_natural_key, "audio_disabled_for_shastra")

    script, segments = await build_script(s, mongo, chapter_natural_key)
    job = await create_job_row(s, chapter_natural_key, voice_id, script)
    mp3 = await providers.get(settings.AUDIO_PROVIDER).synthesize(script=script, voice_id=voice_id)
    blob_url = await storage.upload_mp3(job.id, mp3)
    await storage.put_chapter_doc(chapter_natural_key, segments=segments, blob_url=blob_url, ...)
    await mark_pending_review(s, job.id)
```

Admin reviews + approves in the same `/admin/drushtaant-review`-style queue at `/admin/audio-review`.

### Tests (Phase A — TDD)

1. `test_script_builder.py::test_concatenates_in_gatha_order` — adhikaar with 3 gathas → script contains all three in order.
2. `test_script_builder.py::test_caps_bhaavarth_at_500_words` — long bhaavarth → script truncated.
3. `test_script_builder.py::test_segments_align_to_gathas` — segments[i].gatha_natural_key matches input.
4. `test_provider_dispatch.py::test_provider_env_switch` — `AUDIO_PROVIDER=murf` → MurfProvider used.
5. `test_idempotent_generation.py::test_unique_chapter_voice_pair` — second run with same `(chapter_natural_key, voice_id)` upserts.
6. `test_idempotent_generation.py::test_only_one_approved_per_chapter` — approving a second job for same chapter → 409.

## Phase B — streaming endpoint

### Files

```
services/data_service/routers/audio.py        # new router on existing data-service
packages/jain_kb_common/auth/signed_urls.py   # presign helper (S3 v4)
```

### Endpoints

```
GET /v1/audio/chapters/{chapter_natural_key}
    -> { natural_key, duration_s, segments, voice_id, signed_url, expires_at }

GET /v1/audio/chapters/{chapter_natural_key}/segment/{gatha_natural_key}
    -> { start_s, end_s }
```

Signed URL TTL: 1 hour. Server caches the presigned URL in Redis for 50 minutes to avoid resigning on every request. Signing key in `S3_PRESIGN_KEY` env.

All audio endpoints public; rate-limited to 60 req/min/IP via existing rate limiter middleware.

### Resume position

Stored in `user_preferences.ui.audio_resume` (existing JSONB column from [`01_user_accounts_spec.md`](./01_user_accounts_spec.md)). Shape:

```json
{
  "audio_resume": {
    "samaysaar:adhikaar:1": {"position_s": 942, "updated_at": "2026-05-20T12:34:00Z"},
    "padma-puraan:parva:1:sarga:1": {"position_s": 0, "updated_at": "..."}
  }
}
```

Client writes via existing `PUT /v1/me/preferences` (debounced every 10 s and on `pause`/`ended` events). Guests use `localStorage` under key `saar:audio_resume`. Schema cap: `audio_resume` max 200 keys; client trims LRU.

### Tests (Phase B)

1. `test_signed_url_endpoint.py::test_returns_signed_url_for_approved` — approved chapter → 200 + signed URL.
2. `test_signed_url_endpoint.py::test_404_for_unapproved` — pending → 404.
3. `test_segment_endpoint.py::test_returns_start_end_for_known_gatha` — gatha inside chapter → correct seconds.
4. `test_audio_resume_persistence.py::test_put_preferences_round_trip` — write resume, GET shows same.
5. `test_audio_resume_cap.py::test_trims_to_200_chapters` — write 201 → only newest 200 kept.

## Phase C — `<AudioStrip>` UI component

### Files

```
ui/app/shastra-explorer/_components/AudioStrip.tsx       # Client Component
ui/lib/audio/
├── player.ts                                            # thin wrapper over HTMLAudioElement
├── resume_store.ts                                      # session→preferences or localStorage
└── hotkeys.ts                                           # space=play/pause, ArrowLeft/Right=seek 10s
```

### Component contract

```ts
type Props = {
  chapter_natural_key: string;
  active_gatha_natural_key: string;        // current unit on the reader
  voice_id: string;
};
```

Renders a sticky bottom bar:

```
[▶/⏸]  [⏪10] [⏩10]   ━━━━━●━━━━━━━━   14:23 / 30:43   [1×▾]   [♻ resume]   [voice: Rachel-Hi]
                    ↑ segment markers per gatha
```

Behaviour:
- On mount: fetches `/v1/audio/chapters/{chapter}` → sets `audio.src = signed_url`. Seeks to `resume_store.get(chapter)`.
- On `active_gatha_natural_key` change (user navigates units): if checkbox `follow_unit` is on (default), seek to `segments[gatha].start_s`.
- On `timeupdate`: every 10 s OR on `pause`, write resume via `useResumeStore().set(chapter, position_s)`.
- Speed dropdown: 0.5, 0.75, 1, 1.25, 1.5, 2 (sets `audio.playbackRate`).
- Re-signing: when current signed URL is within 5 min of expiry, refetch and switch sources at next zero-crossing of `timeupdate` to avoid an audible click.
- Voice label shows the human-readable voice mapped from `voice_id` via a static map.

### Hotkeys

| Key | Action |
|---|---|
| Space | play / pause (when reader has focus and no input/textarea is focused) |
| ← / → | seek 10 s |
| Shift+← / Shift+→ | seek 30 s |
| , / . | speed -/+ one step |

### Tests (Phase C)

1. `AudioStrip.test.tsx::seeks_to_resume_on_mount` — mock store returns 120 s → audio.currentTime set to 120.
2. `AudioStrip.test.tsx::writes_resume_every_10s` — fake-timers advance 10 s → store.set called.
3. `AudioStrip.test.tsx::follows_unit_when_enabled` — change `active_gatha` prop → currentTime jumps to segment.start_s.
4. `AudioStrip.test.tsx::guest_uses_local_storage` — `useSession()` null → resume_store reads/writes localStorage.
5. `AudioStrip.test.tsx::refreshes_signed_url_before_expiry` — set expires_at near now → refetch happens.
6. Playwright `audio_strip_play.spec.ts::plays_and_resumes` — load reader, play 5 s, refresh page, position restored within 1 s.

## Configuration

```bash
AUDIO_PROVIDER=elevenlabs                   # elevenlabs | murf | playht
ELEVENLABS_API_KEY=...
ELEVENLABS_MODEL=eleven_multilingual_v2
AUDIO_MONTHLY_USD_CAP=100
S3_BUCKET_AUDIO=saar-audio
S3_PRESIGN_KEY=...
```

## Manual verification

```bash
# Trigger one chapter
celery -A workers call workers.enrichment.audio.tasks.gen_audio_for_adhikaar \
       --args='["samaysaar:adhikaar:1"]'

# Watch
psql -c "SELECT id, status, duration_s, error FROM audio_jobs ORDER BY created_at DESC LIMIT 5;"

# Review + approve
open http://localhost:3000/admin/audio-review

# Stream
curl 'http://localhost:8002/v1/audio/chapters/samaysaar:adhikaar:1' | jq .signed_url

# Reader
open http://localhost:3000/shastra-explorer/samaysaar/adhikaar/1/gatha/001
# Use the bottom <AudioStrip>: play, pause, change speed, reload — position restored.
```

## Definition of done

- [ ] Migration `0022_audio_jobs.py` applied.
- [ ] `audio_chapters` collection set up by `ensure_indexes()`.
- [ ] At least one full adhikaar of samaysaar narrated in Hindi (per scope DoD).
- [ ] Signed URL TTL 1 h; renewal works mid-playback without audible glitch.
- [ ] Resume position persists for logged-in users (preferences) and guests (localStorage).
- [ ] Hotkeys work; ignored while typing in form fields.
- [ ] All listed tests pass.

## Implementation notes

_(to be filled in after merge)_
