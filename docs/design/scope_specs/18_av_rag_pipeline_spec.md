# 18 — A/V RAG Pipeline Spec (YouTube pravachan ingestion)

Scope context: [`scope/06_advanced_rag_and_finetuning.md`](../../scope/06_advanced_rag_and_finetuning.md) §A/V RAG; Q15 default = Whisper-v3 (AssemblyAI optional).

YouTube pravachans by verified authors (whitelist managed in `parser_configs/jinswara_authors.yaml`, see spec 19) get pulled, transcribed, segmented into chunks aligned to silence boundaries, enriched with topics/keywords by the existing extraction pipeline (spec 08), pushed into `cataloguesearch` alongside text chunks, and mirrored as `PravachanChunk` graph nodes so the GraphRAG re-rank (spec 17) and the AI page can cite them with timestamp deep-links.

`pravachans` already exists in Postgres (see `data_model_postgres.md`). This spec only **adds** `pravachan_chunks` and the worker/graph wiring.

## Expected upstream contracts (black box)

```
POST {CATALOGUESEARCH_URL}/ingest/chunks
  body: {
    "chunks": [{
      "external_chunk_id": str,          # we generate this; cataloguesearch echoes it
      "shastra_natural_key": null,
      "source_kind": "pravachan",
      "source_natural_key": "<pravachan_natural_key>",
      "text_hi": str,
      "metadata": {
        "pravachan_id": uuid,
        "sequence":     int,
        "start_s":      float,
        "end_s":        float,
        "youtube_url":  str,
        "topic_nks":    [str],
        "keyword_nks":  [str]
      }
    }]
  }
  resp: {"ingested": [{"external_chunk_id": str, "vector_id": str, "transcript_doc_id": str}]}
```

If cataloguesearch lacks `source_kind="pravachan"` support, fall back to `source_kind="text"` and rely on `metadata.source_kind` for filtering.

## Phase A — yt-dlp + STT worker

### Files

```
workers/ingestion/youtube_pravachans/
├── __init__.py
├── celery_app.py          re-export from packages/jain_kb_common/celery
├── config.py              YTPRAVACHAN_* env (STT_PROVIDER='whisper'|'assemblyai',
│                          WHISPER_MODEL='large-v3', WHISPER_DEVICE='cpu'|'cuda',
│                          ASSEMBLYAI_API_KEY, AUDIO_TMP_DIR='/var/tmp/jinvani/av',
│                          MAX_DURATION_S=21600, RETRIES=2)
├── tasks.py               ingest_pravachan_video(pravachan_id, youtube_url)
├── steps/
│   ├── fetch.py           yt_dlp.download_audio(url, out_dir) -> AudioFile
│   ├── stt.py             transcribe(audio: AudioFile) -> Transcript
│   │                       Transcript = [{"start": float, "end": float, "text": str}]
│   ├── chunk.py           segment(transcript, target_s=45, max_s=90, silence_db=-35)
│   │                       -> list[Chunk]
│   └── push.py            push_to_cataloguesearch(chunks); upsert pravachan_chunks
├── parser_configs/youtube_pravachans.yaml
│                          {default_provider, chunking: {target_s, max_s, min_s, silence_db,
│                           silence_min_s}, retry: {...}}
└── tests/
    ├── conftest.py
    ├── test_fetch_uses_ytdlp.py
    ├── test_chunk_aligned_to_silence.py
    ├── test_stt_provider_switch.py
    ├── test_idempotent_reingest.py
    └── test_pushes_to_cataloguesearch.py
```

Shared models: `packages/jain_kb_common/db/postgres/pravachan_chunks.py`.

### Postgres schema (migration `0031_pravachan_chunks.py`)

```sql
CREATE TABLE pravachan_chunks (
  id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  natural_key        TEXT NOT NULL UNIQUE,    -- '<pravachan_natural_key>:<seq:04d>'
  pravachan_id       UUID NOT NULL REFERENCES pravachans(id) ON DELETE CASCADE,
  sequence           INT  NOT NULL,
  start_s            DOUBLE PRECISION NOT NULL,
  end_s              DOUBLE PRECISION NOT NULL CHECK (end_s > start_s),
  transcript_doc_id  TEXT NOT NULL,            -- Mongo _id stringified
  vector_id          TEXT,                     -- cataloguesearch chunk id (nullable until push)
  topic_ids          JSONB NOT NULL DEFAULT '[]'::jsonb,
  keyword_ids        JSONB NOT NULL DEFAULT '[]'::jsonb,
  stt_provider       TEXT NOT NULL,            -- 'whisper-large-v3' | 'assemblyai'
  stt_confidence     DOUBLE PRECISION,
  status             TEXT NOT NULL DEFAULT 'pending'
                     CHECK (status IN ('pending','transcribed','enriched','indexed','failed')),
  ingestion_run_id   UUID REFERENCES ingestion_runs(id) ON DELETE SET NULL,
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (pravachan_id, sequence)
);
CREATE INDEX idx_pravachan_chunks_pravachan ON pravachan_chunks(pravachan_id);
CREATE INDEX idx_pravachan_chunks_status    ON pravachan_chunks(status);
CREATE INDEX idx_pravachan_chunks_topics    ON pravachan_chunks USING gin (topic_ids   jsonb_path_ops);
CREATE INDEX idx_pravachan_chunks_keywords  ON pravachan_chunks USING gin (keyword_ids jsonb_path_ops);
```

New `ingestion_source` enum value:

```sql
ALTER TYPE ingestion_source ADD VALUE IF NOT EXISTS 'youtube_pravachan';
```

### Mongo collection `pravachan_chunk_transcripts`

```json
{
  "_id": "<stable_id(natural_key)>",
  "natural_key": "<pravachan_nk>:0007",
  "pravachan_natural_key": "<pravachan_nk>",
  "sequence": 7,
  "start_s": 312.4,
  "end_s":   357.9,
  "text":  [{"lang":"hin","script":"Deva","text":"…"}],
  "words": [{"t": 312.5, "w": "आत्मा"}, ...],   // word-level timing if STT provides it
  "stt_provider": "whisper-large-v3",
  "stt_confidence": 0.93,
  "ingestion_run_id": "uuid",
  "created_at": ISODate(...),
  "updated_at": ISODate(...)
}
```

Indexes: `{natural_key:1}` UNIQUE; `{pravachan_natural_key:1, sequence:1}`.

### Pydantic contracts

```python
class Chunk(BaseModel):
    sequence: int
    start_s: float
    end_s:   float
    text_hi: str
    words:   list[dict] | None = None
    stt_confidence: float | None = None

class IngestVideoRequest(BaseModel):
    pravachan_id: UUID
    youtube_url: HttpUrl
    force_reingest: bool = False
```

### Worker entrypoint

```python
# tasks.py
@celery_app.task(bind=True, name="youtube_pravachan.ingest", max_retries=2)
def ingest_pravachan_video(self, pravachan_id: str, youtube_url: str,
                           force_reingest: bool = False) -> dict:
    # 1. Lookup pravachan; verify speaker_id is in jinswara_authors.yaml allowlist.
    # 2. Create ingestion_runs row (source='youtube_pravachan').
    # 3. fetch.download_audio -> mp3/wav at <AUDIO_TMP_DIR>/<pravachan_nk>.mp3
    # 4. stt.transcribe -> Transcript
    # 5. chunk.segment -> list[Chunk]
    # 6. For each Chunk: upsert Mongo transcript doc + pravachan_chunks row (status='transcribed').
    # 7. Enqueue enrichment.enrich_pravachan_chunk per chunk (Phase B).
    # 8. Mark ingestion_run success/partial/failed; return stats.
```

### Silence-aware chunking algorithm

```
Inputs:  transcript (list of word-level or 1-sec windows), target_s, max_s, min_s, silence_db
Output:  list[Chunk]

1. Compute silence intervals using ffmpeg `silencedetect=n=<silence_db>dB:d=<silence_min_s>`
   on the source audio. Result: ordered list of (silence_start, silence_end).
2. Walk transcript segments. Maintain `current = []`, `current_start = 0`.
3. For each segment s:
     append to current
     if (s.end - current_start) >= target_s:
         pick the closest silence midpoint within [current_start + min_s, current_start + max_s];
         if no silence boundary in that window: cut at exactly target_s.
         emit Chunk(current_start, cut_t, joined_text(current up to cut_t))
         current_start = cut_t
         current = remainder
4. Emit final chunk if current is non-empty.
```

Chunks must satisfy `min_s <= duration <= max_s` (defaults 20s / 90s; `target_s=45`).

### STT provider abstraction

```python
class STTProvider(Protocol):
    name: str
    async def transcribe(self, audio_path: Path, lang: str = "hi") -> Transcript: ...

class WhisperProvider:   # uses faster-whisper or openai-whisper locally
    name = "whisper-large-v3"
    ...

class AssemblyAIProvider:
    name = "assemblyai"
    ...

def make_provider(settings) -> STTProvider:
    if settings.STT_PROVIDER == "assemblyai":
        return AssemblyAIProvider(settings.ASSEMBLYAI_API_KEY)
    return WhisperProvider(model=settings.WHISPER_MODEL, device=settings.WHISPER_DEVICE)
```

## Phase B — enrichment (topic/keyword tagging + counter recompute)

A new Celery task wraps the existing extraction pipeline (spec 08) per chunk.

### Files (added)

```
workers/enrichment/pravachan_chunk_enrichment.py
    enrich_pravachan_chunk(chunk_id: UUID)
        - load transcript_doc_id text
        - call extraction pipeline (same one used for gathas / topics):
            extract_keywords_and_topics(text_hi) -> ExtractionResult
        - resolve to keyword UUIDs / topic UUIDs (create candidates for unknowns,
          gated by `ingestion_review_queue` exactly like gatha enrichment).
        - update pravachan_chunks.topic_ids / keyword_ids; status='enriched'.
        - trigger counter recompute (existing counters table maintenance task)
          for affected topic + keyword IDs.
        - enqueue push_chunk_to_cataloguesearch(chunk_id).
```

The extraction pipeline is imported from `packages/jain_kb_common/enrichment/extract.py` (already used for gathas). Do not duplicate; thread `source_kind="pravachan_chunk"` through so admin review queue rows can be filtered.

## Phase C — push to cataloguesearch + graph mirror

### `push_chunk_to_cataloguesearch(chunk_id)`

1. Build the `cataloguesearch /ingest/chunks` payload (one chunk per call to keep retries small).
2. POST with `Idempotency-Key: <pravachan_chunk natural_key>` to make replays safe.
3. Persist returned `vector_id` and `transcript_doc_id` on the `pravachan_chunks` row; flip `status='indexed'`.
4. Trigger `graph_sync.sync_pravachan_chunk(chunk_id)`.

### Neo4j extension (additive)

New node label and edges (additive — no migration system in Neo4j; constraints created in `ensure_constraints()`):

```cypher
CREATE CONSTRAINT pravachan_chunk_natural_key IF NOT EXISTS
  FOR (n:PravachanChunk) REQUIRE n.natural_key IS UNIQUE;
CREATE INDEX pravachan_chunk_pg_id IF NOT EXISTS FOR (n:PravachanChunk) ON (n.pg_id);
```

Node properties:

```
PravachanChunk { natural_key, pg_id, pravachan_natural_key, sequence,
                 start_s, end_s, vector_id, created_at, updated_at }
```

Edges (uppercase types, follow existing conventions; register in `parser_configs/_meta/edge_types.yaml`):

| Type | From → To | Properties | Meaning |
|---|---|---|---|
| `IN_PRAVACHAN`    | `PravachanChunk → Pravachan` (new `Pravachan` label, mirror of `pravachans` row) | — | Structural; excluded from semantic traversal like `IN_SHASTRA`. |
| `MENTIONS_TOPIC`   | `PravachanChunk → Topic`   | `weight`, `source='pravachan'` | Tagged by enrichment. |
| `MENTIONS_KEYWORD` | `PravachanChunk → Keyword` | `weight`, `source='pravachan'` | Tagged by enrichment. |

`STRUCTURAL_EDGE_TYPES` in `services/query_service/pipeline/traverse.py` gets `IN_PRAVACHAN` added so the GraphRAG traversal still skips structural backbone (no behavioural change for existing queries).

`sync_pravachan_chunk(pg_row, topic_nks, keyword_nks)` lives in `packages/jain_kb_common/db/neo4j/upserts.py`. Idempotent via `MERGE`.

### Update GraphRAG response

Existing `query-service /v1/query/graphrag` response shape includes `mentions[]` under each topic. Add a new mention kind without breaking existing consumers:

```json
{"kind": "pravachan_chunk",
 "pravachan_chunk_natural_key": "...",
 "pravachan_natural_key": "...",
 "start_s": 312.4,
 "end_s":   357.9,
 "vector_id": "cs-...",
 "youtube_url": "https://www.youtube.com/watch?v=...",
 "play_url":    "https://www.youtube.com/watch?v=...&t=312s"}
```

`play_url` is derived as `f"{youtube_url}&t={int(start_s)}s"` (or `?t=` if URL has no query string). This is computed in the hydration stage so old responses remain backwards-compatible.

## Phase D — AI page integration

`ui/app/[locale]/(content)/ai/` (`cataloguesearch-chat` re-mounted) gets a new citation tile component:

```
ui/src/components/citations/PravachanCitationTile.tsx
    Props: { pravachan_natural_key, pravachan_title, start_s, end_s, play_url, text_hi }
    Renders: speaker name + title, "▶ Play from <mm:ss>" link (opens YouTube in new tab),
             a 280-char text excerpt with `<mark>` highlights on matched keyword tokens.
```

The chat answer renderer picks this component when a citation's `kind === 'pravachan_chunk'`. No backend change beyond Phase C.

## Tests (TDD — write these first)

1. `test_fetch_uses_ytdlp.py`: stub yt-dlp; assert correct format/codec args; rejects > MAX_DURATION_S.
2. `test_chunk_aligned_to_silence.py`: synthetic transcript + silence map → boundaries land inside silence windows where present, fall back to target_s otherwise.
3. `test_chunk_size_bounds.py`: every emitted chunk has `min_s <= dur <= max_s`.
4. `test_stt_provider_switch.py`: env `STT_PROVIDER=assemblyai` → `make_provider` returns AssemblyAI; `whisper` is the default.
5. `test_idempotent_reingest.py`: run `ingest_pravachan_video` twice → same row count, same `vector_id`, no duplicate Mongo docs.
6. `test_pushes_to_cataloguesearch.py`: stub /ingest/chunks; assert payload shape + Idempotency-Key header.
7. `test_enrichment_tags_chunks.py`: stub extraction pipeline returning 2 topics, 3 keywords → row.topic_ids/keyword_ids populated; counters touched once per ID.
8. `test_graph_sync_creates_chunk_node.py`: real Neo4j testcontainer (or async mock) — sync creates `PravachanChunk` + 2 edges.
9. `test_play_url_appended.py`: hydration adds `play_url` with correct `&t=` suffix.
10. `test_speaker_allowlist_enforced.py`: pravachan whose `speaker_id` is **not** in `jinswara_authors.yaml` → task fails fast, no rows written.

## Manual verification

```bash
# Seed a pravachan row (one-time)
psql "$DATABASE_URL" -c "
  INSERT INTO pravachans (natural_key, title, speaker_id)
  VALUES ('test-pravachan-1',
          '[{\"lang\":\"hin\",\"script\":\"Deva\",\"text\":\"परीक्षण प्रवचन\"}]'::jsonb,
          (SELECT id FROM authors WHERE natural_key='kanjisaheb'));
"

# Trigger ingestion (manual, bypassing the admin UI button)
celery -A workers.ingestion.youtube_pravachans.celery_app call \
  youtube_pravachan.ingest \
  --args='["<PRAVACHAN_UUID>","https://www.youtube.com/watch?v=XXXX"]'

# Watch the run
psql "$DATABASE_URL" -c "SELECT id, status, stats FROM ingestion_runs
                        WHERE source='youtube_pravachan'
                        ORDER BY created_at DESC LIMIT 1;"

# Inspect chunks
psql "$DATABASE_URL" -c "SELECT sequence, start_s, end_s, status, vector_id
                        FROM pravachan_chunks
                        WHERE pravachan_id='<PRAVACHAN_UUID>'
                        ORDER BY sequence LIMIT 10;"

# Ask GraphRAG — should return pravachan_chunk mention
curl -X POST http://localhost:8004/v1/query/graphrag \
  -H 'content-type: application/json' \
  -d '{"tokens":["आत्मा"],"top_k":5,"include_extracts":false}' | jq '.topics[].mentions'
```

## Definition of done

- [ ] Migration `0031_pravachan_chunks.py` applies cleanly; enum addition committed.
- [ ] All Phase A–C tests pass.
- [ ] End-to-end: one real pravachan (≤ 30 min) is ingested, chunked, enriched, indexed, and a graph query returns a `pravachan_chunk` mention for at least one expected topic.
- [ ] AI page renders the `PravachanCitationTile` with a working "Play from mm:ss" link.
- [ ] `counters` are recomputed for all referenced topic/keyword IDs (verified by snapshot diff).
- [ ] Idempotency: re-running ingestion produces zero new rows and zero new Mongo docs.

## Implementation notes

_(to be filled in after merge)_
