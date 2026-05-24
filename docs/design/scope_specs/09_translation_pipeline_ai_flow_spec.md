# 09 — Translation Pipeline: AI Flow (Prompts, Schemas, Router) Spec

Scope context: [`scope/04_translation_enrichment_pipeline.md`](../../scope/04_translation_enrichment_pipeline.md).

Defines the **LLM-facing layer** of the enrichment pipeline: exact prompts, JSON response schemas, the cross-provider router (`packages/jain_kb_common/llm/router.py`), cost caps, retry/backoff, prompt-cache strategy, and the `llm_calls` audit table. Consumed by Stage A + B workers ([`08_translation_pipeline_extraction_spec.md`](./08_translation_pipeline_extraction_spec.md)) and Stage C hierarchy proposer ([`11_topic_hierarchy_ai_spec.md`](./11_topic_hierarchy_ai_spec.md)).

Hindi is canonical (per scope-05). All prompts are language-agnostic via a `target_lang` parameter, defaulting to `hin`.

## Files

```
packages/jain_kb_common/llm/
├── __init__.py
├── router.py                # pick_provider(task, budget) -> LLMClient
├── clients/
│   ├── anthropic.py         # Claude (claude-sonnet-4-5, claude-haiku-4-5)
│   ├── openai.py            # gpt-4o, gpt-4o-mini
│   ├── ollama.py            # local hosted (llama-3.1, qwen-2.5)
│   └── registry.py          # in-house finetuned models (see spec 23)
├── budget.py                # USD caps + token accounting
├── cache.py                 # prompt-cache wrappers (Anthropic system cache + Redis local cache)
├── prompts/
│   ├── extraction_topic.md          # Stage A
│   ├── extraction_keyword.md        # Stage B
│   ├── hierarchy_proposal.md        # Stage C
│   ├── _system_jain_context.md      # shared system block (cached)
│   └── _few_shot_extraction.json
├── schemas.py               # Pydantic JSON-schema response models
└── calls.py                 # log_call(...), audit table writers

services/data_service/routers/admin/
└── llm_calls.py             # GET /admin/llm-calls (audit viewer)

tests/llm/
├── test_router_falls_back_on_cap.py
├── test_anthropic_cache_hits.py
├── test_extraction_topic_schema_round_trip.py
├── test_extraction_keyword_schema_round_trip.py
├── test_hierarchy_proposal_schema_round_trip.py
└── test_retry_on_transient.py
```

## Postgres schema (migration `0021_llm_calls.py`)

```sql
CREATE TYPE llm_task AS ENUM (
  'extraction_topic',         -- Stage A
  'extraction_keyword',       -- Stage B
  'hierarchy_proposal',       -- Stage C
  'categorisation',           -- spec 13
  'translation_keyword',      -- spec 15 (AI fill)
  'translation_topic',
  'misc'
);

CREATE TYPE llm_provider AS ENUM ('anthropic', 'openai', 'ollama', 'registry');

CREATE TABLE llm_calls (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  task              llm_task NOT NULL,
  provider          llm_provider NOT NULL,
  model             TEXT NOT NULL,                   -- e.g. 'claude-sonnet-4-5'
  enrichment_run_id UUID REFERENCES enrichment_runs(id) ON DELETE SET NULL,
  caller            TEXT NOT NULL,                   -- module/task name
  request_payload   JSONB NOT NULL,                  -- prompt + params (NOT redacted; admin-only table)
  response_payload  JSONB,                           -- decoded JSON response
  raw_response_text TEXT,                            -- pre-parse string (for debugging)
  input_tokens      INT,
  output_tokens     INT,
  cache_read_tokens INT NOT NULL DEFAULT 0,
  cache_write_tokens INT NOT NULL DEFAULT 0,
  usd_cost          NUMERIC(10, 6),
  latency_ms        INT,
  retries           INT NOT NULL DEFAULT 0,
  status            TEXT NOT NULL,                   -- 'ok' | 'schema_invalid' | 'rate_limited' | 'budget_exceeded' | 'error'
  error             TEXT,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_llm_calls_task_created ON llm_calls(task, created_at DESC);
CREATE INDEX idx_llm_calls_run ON llm_calls(enrichment_run_id) WHERE enrichment_run_id IS NOT NULL;
CREATE INDEX idx_llm_calls_status ON llm_calls(status) WHERE status <> 'ok';

CREATE TABLE llm_budget_state (
  provider          llm_provider PRIMARY KEY,
  month             DATE NOT NULL,                   -- first day of UTC month
  usd_spent         NUMERIC(10, 6) NOT NULL DEFAULT 0,
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

## Env vars

```
ANTHROPIC_API_KEY=...
OPENAI_API_KEY=...
OLLAMA_BASE_URL=http://ollama:11434
LLM_MONTHLY_USD_CAP_ANTHROPIC=200
LLM_MONTHLY_USD_CAP_OPENAI=100
LLM_MONTHLY_USD_CAP_OLLAMA=0           # local, untracked
LLM_DEFAULT_PROVIDER=anthropic
LLM_DEFAULT_MODEL_EXTRACTION=claude-sonnet-4-5
LLM_FALLBACK_PROVIDER=openai
LLM_FALLBACK_MODEL_EXTRACTION=gpt-4o-mini
LLM_RETRY_MAX=5
LLM_RETRY_INITIAL_S=1
PROMPT_CACHE_TTL_S=900
```

## Router contract

```python
# packages/jain_kb_common/llm/router.py
class LLMClient(Protocol):
    name: str
    provider: Literal['anthropic','openai','ollama','registry']
    model: str

    async def call_json(self, *, system: list[SystemBlock], messages: list[Msg],
                        response_schema: dict, max_tokens: int,
                        cache_keys: list[str] | None = None,
                        task: LLMTask, caller: str,
                        enrichment_run_id: UUID | None = None) -> LLMResult: ...

class LLMResult(BaseModel):
    parsed: dict                              # validated against response_schema
    raw_text: str
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    usd_cost: float
    latency_ms: int
    model: str
    provider: str

def pick_provider(task: LLMTask, *, prefer: str | None = None) -> LLMClient:
    """Selects provider based on env + monthly cap. On cap exhausted, returns fallback."""
```

Provider selection rules:
1. If `prefer=` given and provider not capped → use it.
2. Else `LLM_DEFAULT_PROVIDER` if not capped.
3. Else `LLM_FALLBACK_PROVIDER` if not capped.
4. Else `ollama` (always available).
5. Capped means `llm_budget_state.usd_spent >= LLM_MONTHLY_USD_CAP_<PROVIDER>` for the current UTC month.

## Retry / backoff

- Transient errors (HTTP 429/500/502/503/504, connection reset): exponential backoff with jitter, `LLM_RETRY_INITIAL_S * 2^attempt + uniform(0, 1)`, max `LLM_RETRY_MAX` attempts, then raise `LLMTransient` for Celery to retry the whole task.
- Schema validation failure: retry **once** with a system note `"Your previous response did not match the schema. Return ONLY valid JSON matching: <schema>"`. If still invalid, log `status='schema_invalid'` and re-raise so the worker can mark the chunk as failed (the chunk is retried in next run).
- Budget-exceeded: raise `LLMBudgetExceeded`; router catches and re-resolves with fallback.

## Prompt cache strategy

- **Anthropic native cache** (`cache_control: ephemeral`): mark the `_system_jain_context.md` block and the index neighbourhood block as cached. TTL = 5 min default, extended via `cache_control: { type: "ephemeral", ttl: "1h" }` for Stage A/B index blocks (re-used across all chunks of a shastra).
- **Local Redis cache** (read-through): keyed by `sha256(prompt_template_version + system_blocks + user_msg + response_schema_name + model)`. Hits return cached `LLMResult`; misses call provider then store with `PROMPT_CACHE_TTL_S`.
- The router emits cache stats into the `llm_calls.cache_read_tokens` column for accounting.

## JSON response schemas (Pydantic → schemas.py)

### Stage A — `extraction_topic`

```python
class TopicSpan(BaseModel):
    surface_text: str                           # the exact substring of chunk_text
    span_start: int                             # UTF-8 codepoint offset
    span_end: int
    topic_natural_key: str | None               # null if proposing_new
    proposing_new: bool = False
    candidate_text: str | None                  # required if proposing_new
    confidence: Literal['high','medium','low']
    rationale: str                              # one-sentence justification, ≤ 200 chars

class ExtractionTopicResponse(BaseModel):
    spans: list[TopicSpan]
```

`response_format` for Anthropic: tool_use forcing `record_topic_spans(spans: list[TopicSpan])`. For OpenAI: `response_format={"type":"json_schema","json_schema":{...}}` with `strict: true`.

### Stage B — `extraction_keyword`

```python
class KeywordSpan(BaseModel):
    surface_text: str
    span_start: int
    span_end: int
    keyword_natural_key: str | None
    proposing_new: bool = False
    candidate_text: str | None
    vitrag_en_candidate: str | None             # MUST be exact entry from vitrag dict view
    vitrag_match_kind: Literal['exact','sense','none']
    confidence: Literal['high','medium','low']
    rationale: str

class ExtractionKeywordResponse(BaseModel):
    spans: list[KeywordSpan]
```

### Stage C — `hierarchy_proposal`

```python
class ProposedEdge(BaseModel):
    parent_topic_natural_key: str
    relation: Literal['IS_A','PART_OF','RELATED_TO']
    confidence: Literal['high','medium','low']
    rationale: str

class HierarchyProposalResponse(BaseModel):
    proposed_edges: list[ProposedEdge]          # empty list allowed
```

## Prompts (exact templates)

### `_system_jain_context.md` (shared, cached)

```
You are an expert annotator of Jain śāstra literature, fluent in Hindi
(Devanagari), Sanskrit, and Prakrit. You extract structured metadata
from translated Hindi commentary (bhāvārtha, anvayārtha) and from
JainKosh dictionary pages.

Hard rules:
- Output ONLY a JSON object matching the supplied schema. No prose.
- Span indices are UTF-8 CODEPOINT offsets into the chunk text (NOT bytes).
- The `surface_text` field must equal `chunk_text[span_start:span_end]` exactly
  after NFC normalisation. Mismatches will be auto-rejected downstream.
- Never invent an entity not present in the supplied index unless you set
  `proposing_new=true` AND provide `candidate_text`.
- `confidence='high'` is reserved for unambiguous matches against the index
  (exact NFC equality or one well-known alias). Use `medium` for paraphrases,
  `low` for inferred / partial matches.
- Hindi (`hin`) is canonical. Treat Sanskrit chhāyā as supporting evidence,
  not a substitute for the surface form.
```

### `extraction_topic.md` (Stage A user prompt)

```
TASK: Extract every mention of a *topic* in the chunk below. A topic is
a named concept that maps to an existing row in the topic index (provided)
or warrants creating a new one. Topics are typically multi-word headings
such as "बहिरात्मादि-3-भेद" or "द्रव्य के लक्षण".

PARENT_KEYWORD_NEIGHBOURHOOD: {{parent_keyword_natural_key}}
TOPIC_INDEX (filtered to parent neighbourhood, max 200 rows):
{{topic_index_jsonl}}     # one row per line: {"nk": "...", "heading_hi": "..."}

CHUNK_TEXT (NFC, target_lang={{target_lang}}):
'''
{{chunk_text}}
'''

Emit zero or more topic spans. Prefer matching against TOPIC_INDEX entries.
Propose new topics ONLY when the heading is clearly nameable as a Jain
concept AND no existing row covers it.
```

### `extraction_keyword.md` (Stage B user prompt)

```
TASK: Extract every mention of a *keyword* (atomic Jain term) in the chunk.

KEYWORD_INDEX (filtered to the chunk's adhikaar neighbourhood, max 500):
{{keyword_index_jsonl}}     # {"nk": "आत्मा", "aliases": ["आतम"]}

VITRAG_DICT_VIEW (constrained Hin→En vocabulary; see spec 14):
{{vitrag_view_jsonl}}        # {"hi": "आत्मा", "en": "Soul", "pos": "n", "example": "..."}

CHUNK_TEXT (NFC, target_lang={{target_lang}}):
'''
{{chunk_text}}
'''

For every keyword span, propose the most appropriate Vitrag English entry
in `vitrag_en_candidate`. Set `vitrag_match_kind`:
  - 'exact'  if the Hindi headword in VITRAG_DICT_VIEW equals the surface
  - 'sense'  if the surface is a contextual synonym of a VITRAG_DICT_VIEW entry
  - 'none'   if no entry fits; leave `vitrag_en_candidate=null`

DO NOT invent English translations not present in VITRAG_DICT_VIEW.
```

### `hierarchy_proposal.md` (Stage C user prompt)

```
TASK: For the candidate topic below, propose zero or more parent-relation
edges into the existing topic graph. Use only topics from CANDIDATE_PARENTS
(vector-similarity neighbourhood; max 30 rows).

CANDIDATE_TOPIC:
  heading_hi: {{candidate_heading}}
  parent_keyword: {{parent_keyword_natural_key}}
  extract_excerpt: '''{{extract_first_2000_chars}}'''

CANDIDATE_PARENTS:
{{candidate_parents_jsonl}}   # {"nk": "...", "heading_hi": "...", "cosine": 0.83}

Relation semantics:
  - IS_A:        candidate is a sub-type / specialisation of the parent.
  - PART_OF:     candidate is a sub-section / division of the parent.
  - RELATED_TO:  topical association, no hierarchy.

Propose at most 3 edges. Prefer RELATED_TO when uncertain; IS_A/PART_OF
require high confidence.
```

## Token budgets

| Task | input cap | output cap | typical model |
|---|---|---|---|
| `extraction_topic` | 8K (incl. ≤4K chunk + ≤3K index) | 2K | `claude-sonnet-4-5` |
| `extraction_keyword` | 12K (incl. Vitrag view) | 3K | `claude-sonnet-4-5` |
| `hierarchy_proposal` | 6K | 1K | `claude-haiku-4-5` |
| `categorisation` (spec 13) | 4K | 0.5K | `claude-haiku-4-5` |
| `translation_keyword` (spec 15) | 2K | 0.5K | `gpt-4o-mini` |

Each task has env overrides `LLM_MAX_TOKENS_<TASK>=...`.

## Cost cap enforcement

```python
# packages/jain_kb_common/llm/budget.py
async def check_and_reserve(provider: str, est_usd: float) -> None:
    async with pg.transaction() as tx:
        row = await tx.scalar(select(LlmBudgetState).where(
            LlmBudgetState.provider == provider,
            LlmBudgetState.month == first_of_month_utc()).with_for_update())
        cap = float(os.environ[f"LLM_MONTHLY_USD_CAP_{provider.upper()}"])
        if (row.usd_spent if row else 0) + est_usd > cap:
            raise LLMBudgetExceeded(provider=provider, cap=cap)
        # reserve optimistically; reconciled in record_actual()
        await tx.execute(insert(LlmBudgetState).values(provider=provider,
            month=first_of_month_utc(), usd_spent=est_usd)
            .on_conflict_do_update(index_elements=['provider','month'],
                set_={'usd_spent': LlmBudgetState.usd_spent + est_usd}))
```

Reserve happens before the call, reconciled to actual after the response. Reservations on failed calls are rolled back via a finally-block.

## Tests (TDD)

1. `test_router_falls_back_on_cap.py` — set `LLM_MONTHLY_USD_CAP_ANTHROPIC=0`, request a Stage A call → router resolves to `openai`. With both capped → resolves to `ollama`.
2. `test_anthropic_cache_hits.py` — stub Anthropic client; two calls with identical system block → second reports `cache_read_tokens > 0`.
3. `test_extraction_topic_schema_round_trip.py` — feed a known JSON response → parses into `ExtractionTopicResponse`; malformed JSON triggers single retry then `status='schema_invalid'`.
4. `test_extraction_keyword_schema_round_trip.py` — Vitrag-en candidates outside the supplied dict view → flagged in `rationale` but stored; downstream review handles.
5. `test_hierarchy_proposal_schema_round_trip.py` — empty `proposed_edges` array is valid.
6. `test_retry_on_transient.py` — stub raises 429 twice, success on third try → `retries=2, status='ok'`.
7. `test_llm_calls_audit_row_written.py` — every call writes one row; on retry, only the final call row is written but `retries` column reflects attempts.
8. `test_budget_reservation_rolled_back_on_failure.py` — provider raises → `llm_budget_state.usd_spent` unchanged.

## Manual verification

```bash
# 1. Apply migration
alembic upgrade head

# 2. Smoke-call the router end-to-end against a fixture
python -m jain_kb_common.llm.router smoke \
  --task extraction_topic --provider anthropic \
  --fixture tests/llm/fixtures/samaysaar_chunk_1.json

# 3. Inspect audit table
psql -c "SELECT task, provider, model, status, usd_cost FROM llm_calls ORDER BY created_at DESC LIMIT 5;"

# 4. Confirm cache hit on second invocation
python -m jain_kb_common.llm.router smoke --task extraction_topic --fixture <same>
psql -c "SELECT cache_read_tokens FROM llm_calls ORDER BY created_at DESC LIMIT 1;"  # > 0

# 5. Trip the cap
export LLM_MONTHLY_USD_CAP_ANTHROPIC=0
python -m jain_kb_common.llm.router smoke --task extraction_topic
psql -c "SELECT provider FROM llm_calls ORDER BY created_at DESC LIMIT 1;"  # 'openai' or 'ollama'

# 6. Browse audit via admin API
curl -H 'authorization: Bearer <admin>' \
  'http://localhost:8001/admin/llm-calls?task=extraction_topic&limit=20'
```

## Definition of done

- [ ] Migration `0021_llm_calls.py` applies clean.
- [ ] `router.pick_provider` selects per cap state; all 8 tests pass.
- [ ] All four prompts (`_system_jain_context`, `extraction_topic`, `extraction_keyword`, `hierarchy_proposal`) committed under `packages/jain_kb_common/llm/prompts/`.
- [ ] Anthropic prompt cache verified live: cache hit on the 2nd Stage A call of a shastra session.
- [ ] `llm_calls` table populated for every call; admin API lists them paginated.
- [ ] Budget cap demoably stops Anthropic and falls back to OpenAI.

## Implementation notes

_(to be filled in after merge)_
