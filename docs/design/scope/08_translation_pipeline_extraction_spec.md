# 08 — Translation Pipeline: Extraction (Stage A + Stage B) Spec

Scope context: [`scope/04_translation_enrichment_pipeline.md`](../../scope/04_translation_enrichment_pipeline.md).

Implements **Stage A** (topic spans) and **Stage B** (keyword spans) of the 3-stage enrichment pipeline. Stage C (hierarchy) is specced separately in [`11_topic_hierarchy_ai_spec.md`](./11_topic_hierarchy_ai_spec.md). LLM prompts + JSON schemas live in [`09_translation_pipeline_ai_flow_spec.md`](./09_translation_pipeline_ai_flow_spec.md) (this spec calls into them via a Python contract).

The extraction worker reads bhaavarth / hindi_chhand / teeka chunks from Mongo (see `docs/design/03_data_model_mongo.md`), fans out per-chunk LLM calls, writes character-span rows into the new `extraction_spans` table, and lands every span as a row in the existing `ingestion_review_queue` flavor for admin approval. Approved spans back-fill `gathas.keyword_ids` / `gathas.topic_ids` (see `docs/design/02_data_model_postgres.md#gathas`) and trigger graph sync.

## Phase A — Schema + Pydantic models

### Files

```
packages/jain_kb_common/db/postgres/
├── enums.py                 # extend: extraction_span_kind, extraction_run_status
├── extraction.py            # ExtractionSpan, EnrichmentRun ORM models
└── upserts.py               # upsert_extraction_span(...)

packages/jain_kb_common/enrichment/
├── __init__.py
├── chunks.py                # iter_chunks(gatha_id, lang) -> list[Chunk]
└── schemas.py               # Pydantic models shared with workers + UI
```

### Postgres schema (migration `0020_extraction_spans.py`)

```sql
CREATE TYPE extraction_span_kind AS ENUM ('topic', 'keyword');

CREATE TYPE extraction_confidence AS ENUM ('high', 'medium', 'low');

CREATE TYPE extraction_run_status AS ENUM (
  'pending', 'running', 'success', 'partial', 'failed', 'cancelled'
);

CREATE TYPE extraction_stage AS ENUM ('A_topic', 'B_keyword', 'C_hierarchy');

CREATE TABLE enrichment_runs (
  id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  stage              extraction_stage NOT NULL,
  scope_kind         TEXT NOT NULL,            -- 'shastra' | 'adhikaar' | 'gatha'
  scope_natural_key  TEXT NOT NULL,
  triggered_by       TEXT NOT NULL,
  status             extraction_run_status NOT NULL DEFAULT 'pending',
  llm_model          TEXT,                     -- resolved at task start
  started_at         TIMESTAMPTZ,
  finished_at        TIMESTAMPTZ,
  stats              JSONB NOT NULL DEFAULT '{}'::jsonb,
                                              -- {chunks, spans_emitted, llm_calls, usd_spent}
  iterator_state     JSONB NOT NULL DEFAULT '{}'::jsonb,
                                              -- {last_gatha_id, last_chunk_idx}
  error_log          TEXT,
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_enrichment_runs_status ON enrichment_runs(stage, status);

CREATE TABLE extraction_spans (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id            UUID NOT NULL REFERENCES enrichment_runs(id) ON DELETE CASCADE,
  gatha_id          UUID REFERENCES gathas(id) ON DELETE CASCADE,  -- nullable for keyword-page chunks
  mongo_doc_id      TEXT NOT NULL,            -- chunk source
  mongo_collection  TEXT NOT NULL,            -- e.g. 'teeka_gatha_mapping'
  lang              TEXT NOT NULL,            -- ISO-639-3, usually 'hin'
  kind              extraction_span_kind NOT NULL,
  entity_id         UUID,                     -- topics.id OR keywords.id when resolved
  candidate_text    TEXT,                     -- only when proposing a brand-new entity
  span_start        INT NOT NULL,             -- UTF-8 codepoint offset into chunk text
  span_end          INT NOT NULL,
  span_text         TEXT NOT NULL,            -- denormalised for review UI (chunk[start:end])
  vitrag_en_candidate TEXT,                   -- Stage B only; see spec 14
  confidence        extraction_confidence NOT NULL,
  llm_model         TEXT NOT NULL,
  status            candidate_status NOT NULL DEFAULT 'pending',
  reviewed_by       TEXT,
  reviewed_at       TIMESTAMPTZ,
  reject_reason     TEXT,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (span_end > span_start),
  CHECK ((entity_id IS NOT NULL) OR (candidate_text IS NOT NULL))
);

CREATE INDEX idx_extraction_spans_run ON extraction_spans(run_id);
CREATE INDEX idx_extraction_spans_gatha_kind ON extraction_spans(gatha_id, kind);
CREATE INDEX idx_extraction_spans_status ON extraction_spans(status);
CREATE INDEX idx_extraction_spans_entity ON extraction_spans(entity_id) WHERE entity_id IS NOT NULL;
CREATE UNIQUE INDEX uq_extraction_spans_dedupe
  ON extraction_spans(mongo_doc_id, kind, span_start, span_end, COALESCE(entity_id::text, candidate_text));
```

### Pydantic models (`packages/jain_kb_common/enrichment/schemas.py`)

```python
class Chunk(BaseModel):
    mongo_doc_id: str
    mongo_collection: str
    gatha_id: UUID | None
    lang: str = "hin"
    text: str                                  # NFC normalised, UTF-8 codepoints

class ProposedSpan(BaseModel):
    kind: Literal['topic', 'keyword']
    entity_natural_key: str | None             # filled when index hit
    candidate_text: str | None                 # filled when proposing_new=True
    span_start: int                            # codepoint index into chunk.text
    span_end: int
    vitrag_en_candidate: str | None = None     # Stage B only
    confidence: Literal['high', 'medium', 'low']
    proposing_new: bool = False

class ExtractionResult(BaseModel):
    chunk: Chunk
    spans: list[ProposedSpan]
    llm_model: str
    usd_spent: float
    raw_response_id: str                       # FK into llm_calls (spec 09)
```

## Phase B — Workers

### Files

```
workers/enrichment/
├── __init__.py
├── extraction.py            # Celery tasks: run_stage_a, run_stage_b, extract_chunk
├── prompts.py               # imports from packages/jain_kb_common/llm/prompts/extraction_*
├── chunker.py               # gatha → list[Chunk] (one chunk per Mongo doc, ≤ 4K chars)
├── index_view.py            # build_topic_index(neighbourhood), build_keyword_index()
└── tests/
    ├── fixtures/
    │   ├── samaysaar_adhikaar1_chunks.json
    │   └── golden_spans.json
    ├── test_chunker_splits_by_4k.py
    ├── test_stage_a_emits_topic_spans.py
    ├── test_stage_b_emits_keyword_spans_with_vitrag.py
    ├── test_span_dedupe_on_rerun.py
    ├── test_proposing_new_lands_as_candidate.py
    └── test_run_state_partial_resume.py
```

### Celery task graph

```python
# workers/enrichment/extraction.py
@celery.task(bind=True, name="enrichment.run_stage_a")
def run_stage_a(self, *, scope_kind: str, scope_nk: str, triggered_by: str) -> str:
    run = create_enrichment_run(stage='A_topic', scope_kind=scope_kind,
                                scope_natural_key=scope_nk, triggered_by=triggered_by)
    for gatha_id, chunks in iter_gatha_chunks(scope_kind, scope_nk, lang='hin'):
        for chunk in chunks:
            extract_chunk.delay(run_id=str(run.id), kind='topic',
                                chunk=chunk.model_dump())
    return str(run.id)

@celery.task(name="enrichment.extract_chunk", autoretry_for=(LLMTransient,),
             retry_backoff=True, retry_backoff_max=300, max_retries=5)
def extract_chunk(*, run_id: str, kind: str, chunk: dict) -> dict:
    c = Chunk.model_validate(chunk)
    if kind == 'topic':
        result = call_topic_extractor(c, neighbourhood=resolve_parent_keyword(c))
    else:
        result = call_keyword_extractor(c, vitrag_lookup=vitrag_view())
    persist_spans(run_id, result)
    return {"spans_emitted": len(result.spans)}
```

Stage B is a separate beat task `run_stage_b(...)` with identical shape but `kind='keyword'`. Stage A and B run **independently** per scope — admins can re-run either without touching the other.

### Span persistence

```python
def persist_spans(run_id: UUID, result: ExtractionResult) -> None:
    with pg.transaction() as tx:
        for s in result.spans:
            entity_id = resolve_entity(tx, s) if not s.proposing_new else None
            stmt = pg_insert(ExtractionSpan).values(
                run_id=run_id,
                gatha_id=result.chunk.gatha_id,
                mongo_doc_id=result.chunk.mongo_doc_id,
                mongo_collection=result.chunk.mongo_collection,
                lang=result.chunk.lang,
                kind=s.kind,
                entity_id=entity_id,
                candidate_text=s.candidate_text,
                span_start=s.span_start,
                span_end=s.span_end,
                span_text=result.chunk.text[s.span_start:s.span_end],
                vitrag_en_candidate=s.vitrag_en_candidate,
                confidence=s.confidence,
                llm_model=result.llm_model,
                status='pending',
            ).on_conflict_do_nothing(
                index_elements=['mongo_doc_id', 'kind', 'span_start',
                                'span_end', 'entity_id', 'candidate_text']
            )
            tx.execute(stmt)
        tx.execute(update(EnrichmentRun).where(EnrichmentRun.id == run_id).values(
            stats=EnrichmentRun.stats.op('||')(
                jsonb_build_object('spans_emitted', len(result.spans),
                                   'usd_spent', result.usd_spent))))
```

Dedupe key is `(mongo_doc_id, kind, span_start, span_end, entity_id|candidate_text)` — re-running on the same chunk yields zero net inserts (matches the idempotency convention from `08_ingestion_jainkosh.md`).

### Span validation

- `span_end <= len(chunk.text)` (codepoints, not bytes).
- `chunk.text[span_start:span_end]` must NFC-normalise equal to the LLM's claimed surface form (LLM returns `surface_text` alongside indices; mismatch → reject the span with `reject_reason='span_text_mismatch'`).
- Overlapping spans of the *same kind* are allowed (admin resolves); overlapping spans across kinds are common (a keyword may sit inside a topic) and never blocked.

## Phase C — Review queue integration

### Files

```
services/data_service/
├── routers/admin/
│   └── extraction_review.py    # list, approve, reject endpoints
└── tests/
    └── test_extraction_review_endpoints.py

ui/app/admin/extraction-review/
├── page.tsx                    # uses existing review-queue components from 13_admin_ui.md
└── components/
    ├── SpanCard.tsx            # renders chunk text with span highlighted
    └── VitragSuggestion.tsx    # Stage B only — accept/edit en_candidate
```

### Endpoints

```
GET    /admin/extraction-spans?status=pending&kind=topic&scope_nk=...&page=...
POST   /admin/extraction-spans/{id}/approve
       body: { entity_natural_key?: str, create_new_entity?: bool, en_text?: str }
POST   /admin/extraction-spans/{id}/reject  body: { reason: str }
POST   /admin/extraction-spans/bulk-approve body: { ids: [str], default_action: "...
```

### Approval algorithm

```python
async def approve_span(span_id: UUID, *, reviewer: str,
                       entity_natural_key: str | None,
                       create_new_entity: bool,
                       en_text: str | None) -> None:
    async with pg.transaction() as tx:
        span = await get_span(tx, span_id)
        if create_new_entity:
            if span.kind == 'topic':
                topic = await pg.upsert_topic(tx,
                    natural_key=build_topic_natural_key(parent=resolve_parent(span),
                                                       heading=span.candidate_text),
                    display_text=[{"lang":"hin","script":"Deva","text": span.candidate_text}],
                    source='enrichment')
                entity_id = topic.id
            else:
                keyword = await pg.create_keyword_stub(tx,
                    natural_key=nfc(span.candidate_text),
                    display_text=nfc(span.candidate_text))
                entity_id = keyword.id
        else:
            entity_id = await pg.resolve_entity_id(tx, span.kind, entity_natural_key)

        await pg.update_span(tx, span_id,
                             entity_id=entity_id, status='approved',
                             reviewed_by=reviewer)

        # backfill gathas.{keyword_ids|topic_ids}
        if span.gatha_id:
            await pg.append_gatha_entity(tx, span.gatha_id, span.kind, entity_id)

        # Stage B: if en_text given, write into keyword_translations (spec 15)
        if span.kind == 'keyword' and en_text:
            await pg.upsert_keyword_translation(tx, keyword_id=entity_id,
                lang='eng', script='Latn', text=en_text,
                source='ai', confidence=span.confidence)

    # post-commit fan-out
    graph_sync.delay(entity_kind=span.kind, entity_id=str(entity_id))
    counters_recompute.delay(scope='global', entity_kind=span.kind, entity_id=str(entity_id))
```

### Review UI

Extends `13_admin_ui.md` review-queue grid:

- Default sort: `confidence ASC, created_at DESC` (low-confidence on top per scope-04).
- Each row renders the source chunk with the span underlined; clicking opens a side-panel showing other spans on the same chunk for context.
- Bulk approve action: select N rows, choose `accept LLM-resolved entity` or `reject all`.
- Stage B rows additionally show the `vitrag_en_candidate` chip with an inline edit.

### Tests (TDD — write before implementing)

1. `test_chunker_splits_by_4k.py` — a 9K-char teeka splits into 3 chunks at sentence boundaries; UTF-8 codepoint counted, not bytes.
2. `test_stage_a_emits_topic_spans.py` — golden fixture (`samaysaar_adhikaar1`) → stub LLM returns 5 spans → 5 rows in `extraction_spans` with `kind='topic'`.
3. `test_stage_b_emits_keyword_spans_with_vitrag.py` — Stage B run on same fixture, with Vitrag lookup stubbed; each emitted span carries `vitrag_en_candidate`.
4. `test_span_dedupe_on_rerun.py` — run Stage A twice on the same fixture → row count unchanged after second run; dedupe index hit count > 0.
5. `test_proposing_new_lands_as_candidate.py` — LLM returns `proposing_new=true` → row has `entity_id=null, candidate_text != null`; approval upserts new topic/keyword.
6. `test_run_state_partial_resume.py` — kill the run mid-way → `iterator_state.last_chunk_idx` set → resume task picks up after that idx.
7. `test_extraction_review_endpoints.py` — list, approve, reject; approve backfills `gathas.keyword_ids`.
8. `test_span_text_mismatch_rejected.py` — LLM returns indices that don't slice to its `surface_text` → span auto-rejected.

## Manual verification

```bash
# 1. Apply migrations
alembic upgrade head

# 2. Trigger Stage A for one adhikaar
python -m workers.enrichment.extraction run-stage-a \
  --scope-kind adhikaar --scope-nk "samaysaar:1" --triggered-by anu@local

# 3. Watch the run
psql -c "SELECT id, status, stats FROM enrichment_runs ORDER BY created_at DESC LIMIT 1;"

# 4. Inspect pending spans
psql -c "SELECT kind, span_text, confidence FROM extraction_spans WHERE status='pending' LIMIT 20;"

# 5. Approve via admin API
curl -X POST http://localhost:8001/admin/extraction-spans/<id>/approve \
  -H 'authorization: Bearer <admin_jwt>' \
  -d '{"entity_natural_key":"jainkosh:आत्मा:बहिरात्मादि-3-भेद"}'

# 6. Verify gatha backfill
psql -c "SELECT topic_ids FROM gathas WHERE natural_key='samaysaar:001';"

# 7. Stage B run
python -m workers.enrichment.extraction run-stage-b --scope-kind adhikaar --scope-nk "samaysaar:1"
```

## Definition of done

- [ ] Migration `0020_extraction_spans.py` applies clean.
- [ ] `extraction_spans` UNIQUE dedupe key holds across reruns (proven by `test_span_dedupe_on_rerun.py`).
- [ ] Stage A and Stage B Celery tasks runnable independently per scope.
- [ ] All 8 tests pass.
- [ ] Admin review UI renders ≥ 20 pending spans on the demo dataset with confidence-asc sort.
- [ ] Approval backfills `gathas.keyword_ids` / `gathas.topic_ids` and triggers `graph_sync` + `counters_recompute`.
- [ ] One adhikaar of samaysaar runs E2E with ≥ 50 topic spans + ≥ 100 keyword spans landed.

## Implementation notes

_(to be filled in after merge)_
