# 22 — Finetune Training Infra Spec

Scope context: [`scope/06_advanced_rag_and_finetuning.md`](../../scope/06_advanced_rag_and_finetuning.md), [`scope/09_open_questions.md`](../../scope/09_open_questions.md) Q17–Q20 defaults (Qwen-2.5-7B graph, Llama-3.1-70B main, Modal-hosted, LoRA SFT only in v1).
Depends on: [`design/scope/21_finetune_dataset_export_spec.md`](./21_finetune_dataset_export_spec.md) (input datasets), [`design/scope/23_model_serving_registry_spec.md`](./23_model_serving_registry_spec.md) (outputs).

Train LoRA adapters on rented GPUs (Modal primary, RunPod fall-back) using HF TRL `SFTTrainer` + PEFT. Outputs are checkpoints in S3 and a `finetune_jobs` row.

## Phase A — Modal training app

### Files

```
workers/finetune/
├── training_app.py              Modal app entry: @app.function(gpu=...) train(job_id)
├── runpod_app.py                Same contract over RunPod (used when FINETUNE_RUNTIME=runpod)
├── recipes/
│   ├── __init__.py
│   ├── base.py                  Recipe ABC: load_model, build_lora_config, build_trainer, eval_hook
│   ├── lora_sft.py              PEFT LoRA + TRL SFTTrainer
│   ├── full_sft.py              Stub (raises NotImplementedError in v1)
│   └── dpo.py                   Stub (raises NotImplementedError in v1)
├── hp_defaults.py               Per-(task, base_model) default hyperparams (see below)
├── cost.py                      Modal cost estimator + hard cap check
├── trigger.py                   FastAPI controller that creates a finetune_jobs row + invokes runtime
└── tests/
    ├── test_hp_defaults.py
    ├── test_cost_estimator.py
    ├── test_trigger_creates_job.py
    ├── test_lora_sft_smoke.py     CPU-only smoke (1-step, tiny base) gated by env
    └── test_runtime_switch.py
```

### Modal app contract

```python
# workers/finetune/training_app.py
import modal

image = (
    modal.Image.debian_slim()
    .pip_install("torch", "transformers", "trl", "peft", "accelerate",
                 "datasets", "bitsandbytes", "boto3", "sqlalchemy", "asyncpg",
                 "pydantic", "jain_kb_common")
)
app = modal.App("jinvani-finetune", image=image)

GPU_CLASSES = {
    "A100-80GB": modal.gpu.A100(size="80GB"),
    "A100-40GB": modal.gpu.A100(size="40GB"),
    "L40S":      modal.gpu.L40S(),
    "H100":      modal.gpu.H100(),
}

@app.function(timeout=60*60*24, secrets=[modal.Secret.from_name("jinvani-finetune")])
def train(job_id: str, gpu_class: str = "A100-80GB") -> dict:
    """Single-GPU LoRA SFT job. Returns {checkpoint_s3_uri, logs_url, eval_scores}."""
    # 1. Fetch finetune_jobs row from PG
    # 2. Download dataset from S3 (uri from finetune_datasets row)
    # 3. Load base model (HF) + tokenizer
    # 4. Build LoraConfig from hp + recipe defaults
    # 5. SFTTrainer.train()
    # 6. Save adapter to S3 under jinvani-finetune-checkpoints/<model_id>/<job_id>/
    # 7. Update finetune_jobs.status, finished_at, checkpoint_s3_uri, logs_url
    # 8. Enqueue eval (spec 24) — emit Celery task `finetune.eval.run(job_id)`
    ...
```

Function selection at runtime:

```python
def submit(job_id: str, *, runtime: str = "modal", gpu_class: str = "A100-80GB"):
    if runtime == "modal":
        return train.spawn(job_id, gpu_class)
    if runtime == "runpod":
        from .runpod_app import submit_runpod
        return submit_runpod(job_id, gpu_class)
    raise ValueError(f"unknown runtime {runtime}")
```

Env: `FINETUNE_RUNTIME=modal|runpod`. RunPod fall-back uses the RunPod serverless template `jinvani-finetune` (config out-of-scope here; just defines the same `train(job_id, gpu_class)` entry).

### Default hyperparameters (`hp_defaults.py`)

Keyed by `(task, base_model_family)`:

| Task | Base | rank `r` | alpha | dropout | target_modules | lr | batch | grad_acc | epochs | max_seq_len |
|---|---|---|---|---|---|---|---|---|---|---|
| `graph_cypher` | Qwen-2.5-7B | 16 | 32 | 0.05 | `q_proj,k_proj,v_proj,o_proj,gate_proj,up_proj,down_proj` | 2e-4 | 8 | 4 | 3 | 4096 |
| `jainism_main` | Llama-3.1-70B | 32 | 64 | 0.05 | `q_proj,k_proj,v_proj,o_proj` | 1e-4 | 1 | 32 | 2 | 8192 |
| `jainism_main` | Qwen-2.5-13B | 32 | 64 | 0.05 | all linear | 1.5e-4 | 2 | 16 | 3 | 8192 |
| `sa_pr` | IndicTrans2-1B | 16 | 32 | 0.1 | encoder+decoder attn | 3e-4 | 16 | 2 | 5 | 512 |
| `sa_pr` | Llama-3.1-8B | 16 | 32 | 0.05 | `q_proj,k_proj,v_proj,o_proj` | 2e-4 | 8 | 4 | 4 | 2048 |
| `kn_gu` | IndicTrans2-1B | 16 | 32 | 0.1 | encoder+decoder attn | 3e-4 | 16 | 2 | 5 | 512 |
| `research_domains` | Jainism-main-ft | 8 | 16 | 0.05 | `q_proj,v_proj` | 5e-5 | 2 | 16 | 2 | 8192 |

LR schedule: cosine with 3% warmup. Optimizer: `paged_adamw_8bit`. Mixed precision: bf16 on A100/H100/L40S. Gradient checkpointing always on. QLoRA (4-bit nf4) for 70B; LoRA (16-bit) for ≤13B.

These are *defaults*; the admin can override any field via the `hp` JSONB on the job row.

### Cost cap

```python
# workers/finetune/cost.py
USD_PER_HOUR = {
    "A100-80GB": 4.0,   # Modal list price snapshot
    "A100-40GB": 2.5,
    "L40S":      1.8,
    "H100":      9.0,
}

def estimate_usd(gpu_class: str, est_hours: float) -> float:
    return USD_PER_HOUR[gpu_class] * est_hours

HARD_CAP_USD = float(os.environ["FINETUNE_HARD_CAP_USD"])  # required, no default
```

Before `train.spawn`, controller computes `estimate_usd(gpu_class, hp.epochs * rows / throughput)` using a per-recipe throughput table (`hp_defaults.THROUGHPUT_ROWS_PER_SEC`). If estimate > `HARD_CAP_USD` and `force=False`, return 402 Payment Required with the estimate.

## Phase B — Postgres tracking + admin endpoints

### Schema (migration `0041_finetune_jobs.py`)

```sql
CREATE TYPE finetune_recipe AS ENUM ('lora_sft','full_sft','dpo');
CREATE TYPE finetune_status AS ENUM ('queued','running','succeeded','failed','cancelled');
CREATE TYPE gpu_class       AS ENUM ('A100-80GB','A100-40GB','L40S','H100');

CREATE TABLE finetune_jobs (
  id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  dataset_id         UUID NOT NULL REFERENCES finetune_datasets(id) ON DELETE RESTRICT,
  base_model         TEXT NOT NULL,                  -- HF repo id, e.g. 'Qwen/Qwen2.5-7B-Instruct'
  recipe             finetune_recipe NOT NULL DEFAULT 'lora_sft',
  hp                 JSONB NOT NULL DEFAULT '{}'::jsonb,
  gpu_class          gpu_class NOT NULL DEFAULT 'A100-80GB',
  runtime            TEXT NOT NULL DEFAULT 'modal',  -- 'modal' | 'runpod'
  status             finetune_status NOT NULL DEFAULT 'queued',
  estimated_usd      NUMERIC(10,2),
  actual_usd         NUMERIC(10,2),
  started_at         TIMESTAMPTZ,
  finished_at        TIMESTAMPTZ,
  checkpoint_s3_uri  TEXT,                            -- s3://jinvani-finetune-checkpoints/...
  logs_url           TEXT,                            -- modal/runpod logs link
  eval_scores        JSONB,                           -- written by spec 24
  error_log          TEXT,
  created_by         UUID REFERENCES users(id) ON DELETE SET NULL,
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_finetune_jobs_status  ON finetune_jobs(status, created_at DESC);
CREATE INDEX idx_finetune_jobs_dataset ON finetune_jobs(dataset_id);
```

Note the shape mirrors `ingestion_runs`: `status` enum, `started_at`/`finished_at`, `stats`-equivalent (`hp` + `eval_scores` JSONB), `error_log` TEXT, `created_by` matches `triggered_by`.

### Pydantic contracts

```python
# packages/jain_kb_common/schemas/finetune.py
class FinetuneJobIn(BaseModel):
    dataset_id: UUID
    base_model: str
    recipe: Literal['lora_sft','full_sft','dpo'] = 'lora_sft'
    hp: dict = Field(default_factory=dict)            # overrides over hp_defaults
    gpu_class: Literal['A100-80GB','A100-40GB','L40S','H100'] = 'A100-80GB'
    runtime: Literal['modal','runpod'] = 'modal'
    force: bool = False                                # bypass cost cap

class FinetuneJobOut(BaseModel):
    id: UUID
    dataset_id: UUID
    base_model: str
    recipe: Literal['lora_sft','full_sft','dpo']
    hp: dict
    gpu_class: str
    runtime: str
    status: Literal['queued','running','succeeded','failed','cancelled']
    estimated_usd: Decimal | None
    actual_usd: Decimal | None
    started_at: datetime | None
    finished_at: datetime | None
    checkpoint_s3_uri: str | None
    logs_url: str | None
    eval_scores: dict | None
    created_at: datetime
```

### Admin endpoints (on `metadata-service`)

```
POST   /admin/finetune/jobs               body: FinetuneJobIn  → FinetuneJobOut (202 queued)
GET    /admin/finetune/jobs               query: status, dataset_id, page → page<FinetuneJobOut>
GET    /admin/finetune/jobs/{id}          → FinetuneJobOut
POST   /admin/finetune/jobs/{id}/cancel   → 200; sets status='cancelled', best-effort kill via Modal/RunPod
POST   /admin/finetune/jobs/{id}/retry    → spawns a new job row copying hp/dataset/base
```

All require `require_role('admin')`.

### Job state machine

```
queued → running → succeeded
queued → running → failed
queued → cancelled
running → cancelled
```

Transitions are made by the training worker via direct PG updates (no Celery message round-trip required); use `SELECT … FOR UPDATE` to avoid races with the admin cancel endpoint.

## Phase C — Admin UI page

```
ui/app/admin/finetune-jobs/
├── page.tsx                    list view: filter by status/dataset, badges, eval scores
├── new/page.tsx                form: dataset picker, base model dropdown, recipe, gpu, hp JSON editor
├── [id]/page.tsx               detail: live status, logs link, eval scores, retry/cancel
└── components/
    ├── HpEditor.tsx            JSON-schema-validated form
    ├── CostEstimate.tsx        shows estimated_usd vs HARD_CAP_USD before submit
    └── EvalScoresChart.tsx     bar chart of latest scores
```

UI calls `metadata-service` admin endpoints. Polls `/admin/finetune/jobs/{id}` every 5 s while `status in ('queued','running')`.

## Tests (TDD)

1. `test_hp_defaults.py`: every `(task, base)` pair listed above resolves to a complete config; unknown pair raises `KeyError`.
2. `test_cost_estimator.py`: estimator returns expected USD for known throughputs; exceeds-cap path returns the estimate.
3. `test_trigger_creates_job.py`: POST creates a row in `queued`, spawns a stubbed runtime callable, and returns 202.
4. `test_trigger_cap_block.py`: with `FINETUNE_HARD_CAP_USD=1.0` and a large dataset, POST returns 402; with `force=True`, succeeds.
5. `test_runtime_switch.py`: `FINETUNE_RUNTIME=runpod` routes to `runpod_app.submit_runpod`; default routes to Modal.
6. `test_lora_sft_smoke.py` (gated by `RUN_GPU_TESTS=1`): tiny base (e.g. `sshleifer/tiny-gpt2`), 1 step, 10-row dataset → checkpoint uploaded to mocked S3, row transitions queued → running → succeeded.
7. `test_cancel_transitions.py`: cancel a `queued` job → ok; cancel `succeeded` → 409.
8. `test_eval_hook_enqueued.py`: on `succeeded`, Celery task `finetune.eval.run` is queued with the job id (spec 24 ingests it).
9. `test_admin_ui_rbac.py`: non-admin GET → 403.

## Manual verification

```bash
# Pre-req: a finetune_datasets row exists (spec 21)
DATASET_ID=$(psql -tAc "SELECT id FROM finetune_datasets WHERE name='graph_cypher' ORDER BY created_at DESC LIMIT 1")

# Submit a job (will use defaults from hp_defaults.py)
curl -X POST http://localhost:8001/admin/finetune/jobs \
  -b cookies.txt -H 'content-type: application/json' \
  -d "{\"dataset_id\":\"$DATASET_ID\",\"base_model\":\"Qwen/Qwen2.5-7B-Instruct\",\"gpu_class\":\"A100-80GB\"}"

# Poll
curl http://localhost:8001/admin/finetune/jobs/<id> -b cookies.txt | jq '.status, .logs_url, .checkpoint_s3_uri'

# On success, the checkpoint exists in S3
aws s3 ls s3://jinvani-finetune-checkpoints/<job_id>/

# UI: open http://localhost:3000/admin/finetune-jobs
```

## Definition of done

- [ ] Migrations `0041_finetune_jobs.py` applies cleanly.
- [ ] `hp_defaults.py` covers all `(task, base)` pairs listed.
- [ ] Cost cap blocks over-budget jobs unless `force=True`; admin-only.
- [ ] Modal smoke job completes against a tiny base on CPU runner (CI-gated) and writes a checkpoint to mocked S3.
- [ ] State transitions match the diagram, with the cancel-race guard test green.
- [ ] On `succeeded`, a Celery message is published to the eval queue (verified by a captured-message test).
- [ ] UI list + new + detail pages render and poll live status.
- [ ] RunPod runtime swap proven by `test_runtime_switch.py` (real RunPod not required).

## Implementation notes

_(to be filled in after merge)_
