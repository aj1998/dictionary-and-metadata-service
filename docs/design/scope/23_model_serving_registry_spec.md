# 23 — Model Serving Registry Spec

Scope context: [`scope/06_advanced_rag_and_finetuning.md`](../../scope/06_advanced_rag_and_finetuning.md) ("serving" + "AI page model picker").
Depends on: [`design/scope/22_finetune_training_infra_spec.md`](./22_finetune_training_infra_spec.md) (checkpoint URIs), [`design/15_deployment.md`](../15_deployment.md) (where the new service lives).

Build a registry of models (base + finetuned + external API), a single FastAPI gateway that exposes an OpenAI-compatible `/v1/chat/completions` endpoint and routes per-`model_id` to the actual backend (vLLM HTTP, Ollama HTTP, or upstream provider), and a cost-cap enforcer. Existing services call the gateway through `jain_kb_common.llm.router` — they do not pick backends themselves.

## Phase A — registry schema + admin CRUD

### Postgres schema (migration `0042_model_registry.py`)

```sql
CREATE TYPE model_kind         AS ENUM ('base','finetune','external_api');
CREATE TYPE model_serve_target AS ENUM ('vllm','ollama','anthropic','openai','disabled');
CREATE TYPE model_status       AS ENUM ('staging','active','retired');

CREATE TABLE model_registry (
  id              TEXT PRIMARY KEY,                       -- 'jinvani-graph-ft-v1', 'claude-opus-4-7', 'qwen2.5-7b-base'
  kind            model_kind NOT NULL,
  base_model      TEXT,                                   -- HF id; required if kind!='external_api'
  finetune_job_id UUID REFERENCES finetune_jobs(id) ON DELETE SET NULL,   -- only for kind='finetune'
  checkpoint_s3_uri TEXT,                                 -- mirrors finetune_jobs row when finetune
  serve_target    model_serve_target NOT NULL,
  endpoint_url    TEXT,                                   -- vLLM http url, ollama, or provider override
  supports        JSONB NOT NULL DEFAULT '{}'::jsonb,     -- {graph_cypher:true,hindi:true,english:true,sanskrit:false,...}
  eval_scores     JSONB,                                  -- last eval (from spec 24)
  status          model_status NOT NULL DEFAULT 'staging',
  context_window  INT,                                    -- tokens
  max_output      INT,
  unit_cost_usd_per_1k_input  NUMERIC(10,6),              -- self-hosted: amortised; external: provider price
  unit_cost_usd_per_1k_output NUMERIC(10,6),
  notes           TEXT,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_model_registry_status ON model_registry(status);
CREATE INDEX idx_model_registry_kind   ON model_registry(kind);

CREATE TABLE model_usage_meter (
  id         BIGSERIAL PRIMARY KEY,
  model_id   TEXT NOT NULL REFERENCES model_registry(id) ON DELETE CASCADE,
  env        TEXT NOT NULL,                              -- 'prod' | 'staging' | 'dev'
  month      DATE NOT NULL,                              -- first-of-month
  in_tokens  BIGINT NOT NULL DEFAULT 0,
  out_tokens BIGINT NOT NULL DEFAULT 0,
  usd        NUMERIC(12,4) NOT NULL DEFAULT 0,
  UNIQUE (model_id, env, month)
);
```

`finetune_job_id` is FK back to spec 22 — when a finetune job promotes to a model row, both rows reference each other (the job has `checkpoint_s3_uri`; the registry row copies it for fast read).

### Pydantic contracts

```python
# packages/jain_kb_common/schemas/model_registry.py
class ModelIn(BaseModel):
    id: str
    kind: Literal['base','finetune','external_api']
    base_model: str | None = None
    finetune_job_id: UUID | None = None
    checkpoint_s3_uri: str | None = None
    serve_target: Literal['vllm','ollama','anthropic','openai','disabled']
    endpoint_url: str | None = None
    supports: dict = Field(default_factory=dict)
    context_window: int | None = None
    max_output: int | None = None
    unit_cost_usd_per_1k_input: Decimal | None = None
    unit_cost_usd_per_1k_output: Decimal | None = None
    notes: str | None = None

class ModelOut(ModelIn):
    status: Literal['staging','active','retired']
    eval_scores: dict | None
    created_at: datetime
    updated_at: datetime

class ModelStatusFlip(BaseModel):
    status: Literal['staging','active','retired']
```

### Admin endpoints (on `metadata-service`)

```
GET    /admin/models                              list, filter by kind/status
POST   /admin/models                              create
GET    /admin/models/{id}
PUT    /admin/models/{id}                         update mutable fields
POST   /admin/models/{id}/status                  body ModelStatusFlip
DELETE /admin/models/{id}                         allowed only if no usage_meter rows in last 30d
GET    /admin/models/{id}/usage?env=&since=       returns rolling meter
```

Status flips trigger `model-serving-service` to reload its routing table (HTTP `POST /internal/reload`).

## Phase B — model-serving-service (port 8008)

Single FastAPI app, deployed as its own container (no GPU itself; GPU lives in the vLLM container it forwards to).

### Files

```
services/model_serving_service/
├── __init__.py
├── main.py                       FastAPI app, /healthz, /v1/chat/completions, /v1/models, /internal/reload
├── config.py                     Settings (PG url, registry refresh interval, cost cap envs, port 8008)
├── routing.py                    in-memory routing table built from model_registry rows; refreshes on /internal/reload
├── backends/
│   ├── __init__.py
│   ├── base.py                   Backend ABC: async chat(request, model_row) -> stream/non-stream
│   ├── vllm.py                   httpx → vLLM OpenAI-compatible endpoint (one per model)
│   ├── ollama.py                 httpx → Ollama /api/chat
│   ├── anthropic.py              Anthropic SDK
│   └── openai.py                 OpenAI SDK
├── meter.py                      counts tokens (provider response or tiktoken estimate), writes model_usage_meter
├── caps.py                       per-(env, model_id) USD caps from env: SERVE_CAP_<env>_<modelid>=USD
└── tests/
    ├── test_routing.py
    ├── test_meter.py
    ├── test_cap_block.py
    ├── test_vllm_proxy.py
    ├── test_ollama_proxy.py
    ├── test_anthropic_proxy.py
    └── test_reload.py
```

### Public contract

`POST /v1/chat/completions` is OpenAI-compatible. Request body:

```json
{
  "model": "jinvani-graph-ft-v1",
  "messages": [{"role":"user","content":"..."}],
  "max_tokens": 1024,
  "temperature": 0.2,
  "stream": false
}
```

Behaviour:
1. Look up `model_id` in routing table. If `status!='active'`, return 503 with `{"error":"model not active"}`.
2. Check `caps.check(env, model_id, projected_usd=estimate(in_tokens, max_tokens))`. If exceeded, return 429 with `{"error":"cap exceeded","cap_usd":X,"used_usd":Y}`.
3. Call the appropriate backend; stream through.
4. After completion, `meter.record(env, model_id, in_tokens, out_tokens, usd)` upserts `model_usage_meter`.

`GET /v1/models` returns the active models in OpenAI format.

`POST /internal/reload` (auth via `SERVE_INTERNAL_TOKEN`) reloads the routing table from PG.

### vLLM topology

For each `active` finetune/base model with `serve_target='vllm'`, run one vLLM container:

```
docker run --gpus all -p 8101:8000 \
  vllm/vllm-openai:latest \
  --model Qwen/Qwen2.5-7B-Instruct \
  --enable-lora \
  --lora-modules jinvani-graph-ft-v1=s3://jinvani-finetune-checkpoints/<job_id>/adapter
```

`endpoint_url` in `model_registry` is `http://vllm-graph-ft:8000`. The serve gateway sends `model` field as-is (vLLM resolves to the LoRA adapter name).

Multiple LoRA adapters on the same base can share one vLLM container by passing multiple `--lora-modules`. The registry's `endpoint_url` may therefore be shared across rows.

### Ollama topology

Dev-local fall-back. Same OpenAI shape via Ollama's `/v1/chat/completions`. Registry row uses `serve_target='ollama'` and `endpoint_url=http://ollama:11434`.

### Per-(env, model) cost caps

`caps.py` reads env vars at startup and on `/internal/reload`:

```
SERVE_CAP_PROD_JINVANI_GRAPH_FT_V1_USD=200
SERVE_CAP_PROD_CLAUDE_OPUS_4_7_USD=500
SERVE_CAP_DEV_DEFAULT_USD=20            # fallback for unspecified models in dev
```

Naming: `SERVE_CAP_<ENV>_<MODEL_ID_UPPER_UNDERSCORED>_USD`. The cap is monthly; a request is blocked when `meter.usd_for_this_month + projected > cap`. Estimate uses `unit_cost_*` from the registry row.

### Compose addition (`docker-compose.yml` excerpt — for `15_deployment.md`)

```yaml
  model-serving-service:
    build: { context: ., dockerfile: services/model_serving_service/Dockerfile }
    env_file: *env_files
    ports: ["8008:8008"]
    depends_on: [postgres]

  vllm-graph-ft:
    image: vllm/vllm-openai:latest
    runtime: nvidia
    command: >
      --model Qwen/Qwen2.5-7B-Instruct --enable-lora
      --lora-modules jinvani-graph-ft-v1=/checkpoints/jinvani-graph-ft-v1/adapter
    volumes:
      - ./data/checkpoints:/checkpoints:ro
    expose: ["8000"]
```

(70B models use a separate compose file `docker-compose.gpu-large.yml` so a small box can omit them.)

## Phase C — router update in jain_kb_common

```python
# packages/jain_kb_common/llm/router.py  (extended; existing module exists from llm_call abstraction)
from .clients import openai_compatible_client

class LLMRouter:
    def __init__(self, serving_url: str = os.environ["MODEL_SERVING_URL"]):
        self._client = openai_compatible_client(base_url=f"{serving_url}/v1")

    async def chat(self, *, model_id: str, messages, **kwargs):
        return await self._client.chat.completions.create(model=model_id, messages=messages, **kwargs)
```

Callers (`query-service`, `cataloguesearch-chat`, research tools) talk only to this router. The router does not know whether a model is base / finetune / external — the gateway decides.

Env addition: `MODEL_SERVING_URL=http://model-serving-service:8008`.

## Admin UI

```
ui/app/admin/models/
├── page.tsx                       list: id, kind, status, latest eval scores, monthly usage
├── new/page.tsx                   create row (mostly used for external_api; finetune rows are auto-created on job success)
├── [id]/page.tsx                  detail: status flip, supports JSON edit, usage chart, eval history
└── components/
    ├── StatusBadge.tsx
    ├── EvalScoresTable.tsx
    └── UsageChart.tsx
```

When a finetune_jobs row hits `succeeded`, a Celery task `finetune.registry.auto_register(job_id)` creates a `model_registry` row in `staging` with id `<task>-ft-v<n>` (n increments). Admin manually flips to `active` after reviewing eval scores.

## Tests (TDD)

1. `test_routing.py`: registry with 2 active rows + 1 retired → `/v1/models` lists 2; retired returns 503.
2. `test_reload.py`: change row status via admin endpoint → `/internal/reload` → next request hits new table.
3. `test_vllm_proxy.py`: stub vLLM with `respx`; assert request forwards body, response returns intact, tokens are metered.
4. `test_ollama_proxy.py`: same against Ollama path.
5. `test_anthropic_proxy.py`: provider response is converted to OpenAI shape; usage is metered correctly.
6. `test_cap_block.py`: monthly cap exceeded → 429 with cap+used fields; under cap → 200.
7. `test_meter.py`: two concurrent requests UPSERT correctly (no double-add) — use `INSERT … ON CONFLICT DO UPDATE SET in_tokens = model_usage_meter.in_tokens + EXCLUDED.in_tokens`.
8. `test_auto_register_on_finetune_success.py`: simulate job→succeeded → registry row exists in `staging` with `finetune_job_id` populated.
9. `test_status_delete_guard.py`: DELETE on a model with usage in last 30d → 409.
10. `test_router_ignores_backend.py`: `LLMRouter.chat` sends only `model_id`; never references backend specifics.

## Manual verification

```bash
# Bring up serving + a vllm container (small base)
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d model-serving-service vllm-graph-ft

# Register a base model
curl -X POST http://localhost:8001/admin/models -b cookies.txt -H 'content-type: application/json' \
  -d '{"id":"qwen2.5-7b-base","kind":"base","base_model":"Qwen/Qwen2.5-7B-Instruct",
       "serve_target":"vllm","endpoint_url":"http://vllm-graph-ft:8000","supports":{"hindi":true}}'
curl -X POST http://localhost:8001/admin/models/qwen2.5-7b-base/status -b cookies.txt -d '{"status":"active"}'

# Call through the gateway
curl -X POST http://localhost:8008/v1/chat/completions -H 'content-type: application/json' \
  -d '{"model":"qwen2.5-7b-base","messages":[{"role":"user","content":"नमस्ते"}],"max_tokens":64}'

# Meter row should appear
psql -c "SELECT * FROM model_usage_meter ORDER BY id DESC LIMIT 5;"
```

## Definition of done

- [ ] Migrations `0042_model_registry.py` applies cleanly.
- [ ] `model-serving-service` ships with Dockerfile + healthz; reachable at port 8008.
- [ ] All 4 backends pass their proxy test against `respx` stubs.
- [ ] Cap enforcement proven by `test_cap_block.py`.
- [ ] Auto-register-on-finetune-success integration test green.
- [ ] `LLMRouter` in `jain_kb_common` updated and consumed by at least `query-service` as a smoke check.
- [ ] Admin UI list/detail/status pages work end-to-end with a real vLLM container.
- [ ] `15_deployment.md` patched with the new service + GPU compose file.

## Implementation notes

_(to be filled in after merge)_
