# 29 — Research Models Index Spec

Scope context: [`scope/07_siri_bhoovalay_and_research_models.md`](../../scope/07_siri_bhoovalay_and_research_models.md) (Research models — index).
Depends on: [`design/scope/22_finetune_training_infra_spec.md`](./22_finetune_training_infra_spec.md) (`finetune_jobs`), [`design/scope/23_model_serving_registry_spec.md`](./23_model_serving_registry_spec.md) (`model_registry` + gateway), [`design/scope/24_finetune_eval_harness_spec.md`](./24_finetune_eval_harness_spec.md) (`eval_results`), [`design/scope/01_user_accounts_spec.md`](./01_user_accounts_spec.md) (`current_user_optional` for role-gated fields and per-user playground rate-limit).

A public, read-only **catalog page** at `/research/models` that lists every finetuned (and base) model in the registry along with the training data, eval metrics, deployment status, and a small playground for sample I/O. It is the public face of the finetuning programme — guests can see what exists and try them; admins additionally see internal cost and hyperparameter detail.

This spec is intentionally **single-phase, read-mostly**. All write paths (training, registry edits, eval) belong to specs 22/23/24. The only writes here are the playground rate-limit counter.

## Files

```
services/data-service/app/routers/
└── research_models.py            list + detail + playground endpoints

services/data-service/app/services/
├── research_models_query.py      joins across model_registry + finetune_jobs + eval_results
├── playground_rate_limit.py      token-bucket per (user_id|ip) + per model
└── playground_proxy.py           thin wrapper over jain_kb_common.llm.router

packages/jain_kb_common/schemas/research_models.py    Pydantic outputs

ui/pages/ResearchModels/
├── index.tsx                     /research/models — list with filters
├── [id].tsx                      /research/models/[id] — detail + playground
└── components/
    ├── ModelCard.tsx
    ├── FiltersBar.tsx            task, base_model, status, search
    ├── EvalHistoryTable.tsx
    ├── EvalMetricChart.tsx       chrF/BLEU/F1 over time
    ├── TrainingConfigPanel.tsx
    ├── DatasetCard.tsx           shows finetune_datasets row summary
    ├── SamplePromptsPanel.tsx    curated examples from training_config
    └── Playground.tsx            prompt input, response stream, "rate-limited" toast

ui/lib/api/research_models.ts     fetch helpers
ui/lib/research_models/role_gates.ts   client-side gate for admin-only fields

tests/                            see "Tests" section
```

No new database tables. Two small additions:

1. `model_registry.public_card` (JSONB, nullable) — admin-curated description, hero text, sample prompts. Migration `0058_model_registry_public_card.py`:

   ```sql
   ALTER TABLE model_registry ADD COLUMN public_card JSONB;
   ```

   Shape:

   ```json
   {
     "tagline_hi": "...",
     "tagline_en": "...",
     "description_md": "...",
     "sample_prompts": [
       {"label": "Parent topic", "prompt": "What is the parent of samyak_darshan?"},
       {"label": "Path", "prompt": "Shortest relation path from jiv to karm."}
     ],
     "default_max_tokens": 256,
     "default_temperature": 0.2
   }
   ```

2. `playground_usage` table for the rate-limiter. Migration `0059_playground_usage.py`:

   ```sql
   CREATE TABLE playground_usage (
     id            BIGSERIAL PRIMARY KEY,
     user_id       UUID REFERENCES users(id) ON DELETE CASCADE,    -- null for guests (keyed by ip_hash)
     ip_hash       TEXT,                                             -- sha256(ip + salt) for guests
     model_id      TEXT NOT NULL REFERENCES model_registry(id) ON DELETE CASCADE,
     requested_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
     tokens_in     INT NOT NULL DEFAULT 0,
     tokens_out    INT NOT NULL DEFAULT 0
   );
   CREATE INDEX idx_playground_user_time  ON playground_usage(user_id, requested_at DESC);
   CREATE INDEX idx_playground_ip_time    ON playground_usage(ip_hash, requested_at DESC);
   CREATE INDEX idx_playground_model_time ON playground_usage(model_id, requested_at DESC);
   ```

## API contracts

All routes mounted on the existing `data-service` (port 8001) under `/v1/research/models`. Guests are allowed everywhere; auth is checked only to decide which fields are returned and to scale rate limits.

```
GET /v1/research/models
  query:
    task?: 'graph_understanding' | 'sa_pr' | 'kn_gu' | 'jainism_main' | 'research_domains' | 'graph_cypher'
    base_model?: str           # HF id prefix match
    status?: 'staging' | 'active' | 'retired' | 'all'    (default: 'active')
    kind?: 'base' | 'finetune' | 'external_api'
    q?: str                    # free-text over id, base_model, public_card.description_md
    page?: int = 1
    page_size?: int = 20
  returns: Page<ResearchModelListItem>

GET /v1/research/models/{id}
  returns: ResearchModelDetail   (or 404)

POST /v1/research/models/{id}/playground
  body:    { prompt: str, max_tokens?: int, temperature?: float }
  returns: { output: str, tokens_in: int, tokens_out: int, model_id: str, served_by: str }
  errors:  429 if rate-limited; 503 if model not active.
```

### Pydantic shapes

```python
# packages/jain_kb_common/schemas/research_models.py

class ResearchModelListItem(BaseModel):
    id: str
    kind: Literal['base','finetune','external_api']
    base_model: str | None
    task: str | None                  # derived from finetune_jobs.dataset.task; null for base/external
    status: Literal['staging','active','retired']
    supports: dict
    tagline_hi: str | None
    tagline_en: str | None
    primary_metric: float | None      # macro score from eval_scores; null if not evaluated
    primary_metric_name: str | None   # 'macro_chrf' | 'macro_f1' | 'macro' | ...
    last_eval_at: datetime | None

class EvalHistoryPoint(BaseModel):
    eval_id: UUID
    run_at: datetime
    scores: dict                      # full eval_scores JSON

class TrainingConfigPublic(BaseModel):
    base_model: str
    recipe: str
    dataset_name: str
    dataset_rows: int
    hp: dict                          # filtered: lr, r, alpha, epochs, batch only (no env)
    gpu_class: str
    trained_at: datetime | None

class TrainingConfigAdmin(TrainingConfigPublic):
    full_hp: dict                     # entire JSONB
    actual_usd: Decimal | None
    estimated_usd: Decimal | None
    logs_url: str | None
    checkpoint_s3_uri: str | None

class ResearchModelDetail(BaseModel):
    id: str
    kind: Literal['base','finetune','external_api']
    status: Literal['staging','active','retired']
    base_model: str | None
    supports: dict
    public_card: dict | None
    eval_history: list[EvalHistoryPoint]
    latest_eval: dict | None
    training: TrainingConfigPublic | TrainingConfigAdmin | None
    sample_prompts: list[dict]
    deployment: dict                  # {serve_target, endpoint_reachable: bool}
    # admin-only (omitted for guests/users)
    monthly_usage: dict | None        # {usd, in_tokens, out_tokens}
    unit_cost_usd_per_1k_input: Decimal | None
    unit_cost_usd_per_1k_output: Decimal | None
```

### Role gating

Defined in `services/data-service/app/routers/research_models.py`:

```python
ADMIN_ONLY_FIELDS = {
    "TrainingConfigAdmin": {"full_hp", "actual_usd", "estimated_usd", "logs_url", "checkpoint_s3_uri"},
    "ResearchModelDetail": {"monthly_usage", "unit_cost_usd_per_1k_input", "unit_cost_usd_per_1k_output"},
}

def serialise_for(user: User | None, model_row, *, with_eval, with_training):
    detail = build_detail(model_row, with_eval=with_eval, with_training=with_training)
    if user is None or user.role not in ("admin",):
        # Strip admin-only fields; downgrade TrainingConfigAdmin → TrainingConfigPublic
        detail.training = downcast_training(detail.training)
        for f in ADMIN_ONLY_FIELDS["ResearchModelDetail"]:
            setattr(detail, f, None)
    return detail
```

`reviewer` is not granted admin fields here; only `admin` sees cost and full hyperparameter detail. `query_logs` and similar PII never appear on this endpoint regardless of role.

### Joining query

`research_models_query.py` does a single SQL with `LEFT JOIN`s:

```sql
SELECT
  mr.id, mr.kind, mr.base_model, mr.status, mr.supports, mr.eval_scores,
  mr.public_card, mr.unit_cost_usd_per_1k_input, mr.unit_cost_usd_per_1k_output,
  fj.id AS finetune_job_id, fj.hp, fj.gpu_class, fj.actual_usd, fj.estimated_usd,
  fj.logs_url, fj.checkpoint_s3_uri, fj.finished_at,
  fd.name AS dataset_name, fd.task AS dataset_task, fd.row_count AS dataset_rows,
  mr.updated_at
FROM model_registry mr
LEFT JOIN finetune_jobs     fj ON fj.id = mr.finetune_job_id
LEFT JOIN finetune_datasets fd ON fd.id = fj.dataset_id
WHERE (:status = 'all' OR mr.status = :status)
  AND (:kind IS NULL OR mr.kind = :kind)
  AND (:task IS NULL OR fd.task = :task)
  AND (:base_model IS NULL OR mr.base_model ILIKE :base_model || '%')
  AND (:q IS NULL OR mr.id ILIKE '%'||:q||'%' OR mr.base_model ILIKE '%'||:q||'%'
       OR mr.public_card->>'description_md' ILIKE '%'||:q||'%')
ORDER BY mr.status ASC, mr.updated_at DESC
LIMIT :limit OFFSET :offset;
```

`eval_history` is fetched in a follow-up `SELECT * FROM eval_results WHERE model_id=:id ORDER BY run_at DESC LIMIT 20` (spec 24's table).

### Playground

`POST /v1/research/models/{id}/playground` flow:

1. Look up the model in `model_registry`. If `status != 'active'`, return 503 with `{"error":"model_not_active"}`.
2. Resolve the rate-limit bucket key:
   - logged-in user: `f"user:{user.id}"`
   - guest: `f"ip:{sha256(client_ip + PLAYGROUND_SALT)}"`
3. Check the rate limit (see below). If exceeded, return 429 with `{"error":"rate_limited","retry_after_s":N}`.
4. Sanitise prompt: max `2000` characters, strip null bytes, reject when empty.
5. Apply defaults from `public_card` (`default_max_tokens`, `default_temperature`); cap `max_tokens <= 512`.
6. Call `LLMRouter.chat(model_id=id, messages=[{"role":"user","content":prompt}], max_tokens=..., temperature=...)` (spec 23 gateway).
7. Insert one row into `playground_usage` with `tokens_in`, `tokens_out`.
8. Return `{output, tokens_in, tokens_out, model_id, served_by}`.

### Rate limit (token bucket via SQL)

`playground_rate_limit.py` implements a fixed-window counter against `playground_usage`:

| Role     | Per minute | Per hour | Per day |
|----------|------------|----------|---------|
| guest    | 3          | 20       | 50      |
| user     | 10         | 100      | 400     |
| reviewer | 20         | 300      | 1500    |
| admin    | bypass     | bypass   | bypass  |

Window is a sliding `WHERE requested_at > now() - interval '1 minute'` count per key + model. The model-level dimension is intentional: a user can play with multiple models concurrently.

Returns `429` with `retry_after_s` set to the seconds until the most restrictive window opens.

### Env

```
PLAYGROUND_SALT=<random 32-byte hex>
PLAYGROUND_MAX_PROMPT_CHARS=2000
PLAYGROUND_MAX_TOKENS_CAP=512
```

## UI

### Catalog (`ui/pages/ResearchModels/index.tsx`)

- Server-side rendered grid of `ModelCard` tiles. Each card shows: model id, kind badge, base model, task pill, primary metric chip (with metric name), status dot, "Open" button.
- Filters bar across the top: task multi-select, base_model search, status toggle (`active` default), kind toggle.
- Empty state for `staging`-only list: "No active models yet — peek at staging" link with `?status=staging`.

### Detail (`ui/pages/ResearchModels/[id].tsx`)

Layout (1 column on mobile, 2 columns on desktop):

```
┌────────────────────────────────────────────────────────────┐
│ Header: id, kind, status badge, base_model                 │
│ Tagline (hi/en, switches with current locale)              │
│ Description (markdown from public_card.description_md)     │
├──────────────────────┬─────────────────────────────────────┤
│ Eval (left col)      │ Playground (right col, sticky)     │
│  • Metric chart      │  prompt textarea                    │
│  • History table     │  max_tokens, temperature sliders   │
│                      │  "Run" button                       │
│ Training config      │  Output panel (markdown)            │
│  • Dataset card      │  tokens-used + rate-limit footer    │
│  • HP table          │                                     │
│ Sample prompts       │                                     │
│  (click → fills      │                                     │
│   playground)        │                                     │
│ Deployment           │                                     │
│  • Serve target      │                                     │
│  • endpoint reachable│                                     │
└──────────────────────┴─────────────────────────────────────┘
```

- Admin-only fields render an additional "Admin" section below "Deployment" with cost + logs link + checkpoint S3 URI. Hidden entirely (no DOM) when `useSession()?.role !== 'admin'`.
- Playground shows a small banner for guests: "Sign in for 4× higher limits".
- 429 responses surface as a non-modal toast with the `retry_after_s` countdown.

## Tests (TDD)

Backend (Pytest):

1. `test_list_filters.py::test_default_only_active` — staging + retired rows hidden when `status` not set.
2. `test_list_filters.py::test_filter_by_task` — only rows whose dataset task matches.
3. `test_list_filters.py::test_filter_by_base_model_prefix`.
4. `test_list_filters.py::test_search_matches_id_or_description`.
5. `test_list_filters.py::test_pagination`.
6. `test_detail_joins.py::test_includes_dataset_summary` — `dataset_name`, `dataset_rows` populated.
7. `test_detail_joins.py::test_eval_history_ordered_desc`.
8. `test_detail_joins.py::test_base_row_has_no_training_config`.
9. `test_detail_joins.py::test_external_api_row_has_no_checkpoint`.
10. `test_role_gated_fields.py::test_guest_does_not_see_actual_usd`.
11. `test_role_gated_fields.py::test_user_does_not_see_full_hp`.
12. `test_role_gated_fields.py::test_admin_sees_everything`.
13. `test_role_gated_fields.py::test_reviewer_is_treated_as_non_admin_here`.
14. `test_playground_rate_limit.py::test_guest_blocked_after_3_per_minute`.
15. `test_playground_rate_limit.py::test_user_higher_quota`.
16. `test_playground_rate_limit.py::test_admin_bypass`.
17. `test_playground_rate_limit.py::test_per_model_independent` — model A quota exhausted does not block model B.
18. `test_playground_rate_limit.py::test_retry_after_set_correctly`.
19. `test_playground_proxy.py::test_calls_llm_router_with_correct_model_id` — `respx` stub gateway; verify forwarded body.
20. `test_playground_proxy.py::test_inactive_model_returns_503`.
21. `test_playground_proxy.py::test_prompt_too_long_returns_422`.
22. `test_playground_proxy.py::test_tokens_recorded_in_usage_table`.
23. `test_public_card_round_trip.py::test_admin_set_public_card_visible_in_detail` — admin PATCH (uses existing spec 23 admin PUT) → public detail reflects it.

Frontend (Playwright):

24. `research_models.spec.ts::catalog_renders_active_only_by_default`.
25. `research_models.spec.ts::filter_by_task_updates_grid`.
26. `research_models.spec.ts::detail_loads_eval_chart`.
27. `research_models.spec.ts::playground_run_displays_output`.
28. `research_models.spec.ts::guest_rate_limit_shows_toast`.
29. `research_models.spec.ts::admin_section_visible_for_admin`.
30. `research_models.spec.ts::admin_section_hidden_for_guest`.
31. `research_models.spec.ts::sample_prompt_click_fills_textarea`.

## Manual verification

```bash
# 0. Apply migrations
alembic upgrade 0059

# 1. Seed a public_card on an existing model
psql -c "UPDATE model_registry SET public_card = '{
  \"tagline_en\":\"Sanskrit/Prakrit → Hindi translation finetune.\",
  \"description_md\":\"Trained on 20k aligned verse pairs.\",
  \"sample_prompts\":[{\"label\":\"Simple\",\"prompt\":\"Translate Sanskrit to Hindi:\\nजीवाजीवौ हि सिद्धान्तस्य मूलम्\"}],
  \"default_max_tokens\":128, \"default_temperature\":0.0
}'::jsonb WHERE id='sa-pr-ft-v1';"

# 2. List
curl 'http://localhost:8001/v1/research/models?status=active&task=sa_pr' | jq '.items[].id'

# 3. Detail (guest)
curl http://localhost:8001/v1/research/models/sa-pr-ft-v1 | jq '.training.hp, .monthly_usage'
# Expect: hp present (filtered), monthly_usage null.

# 4. Detail (admin)
curl -b admin_cookies.txt http://localhost:8001/v1/research/models/sa-pr-ft-v1 \
  | jq '.training.full_hp, .training.actual_usd, .monthly_usage'

# 5. Playground (guest)
curl -X POST http://localhost:8001/v1/research/models/sa-pr-ft-v1/playground \
  -H 'content-type: application/json' \
  -d '{"prompt":"Translate Sanskrit to Hindi:\nजीवाजीवौ"}'

# 6. Trigger rate limit (guest, 4 quick calls — 4th returns 429)
for i in 1 2 3 4; do
  curl -s -o /dev/null -w "%{http_code}\n" -X POST \
    http://localhost:8001/v1/research/models/sa-pr-ft-v1/playground \
    -H 'content-type: application/json' \
    -d '{"prompt":"test"}'
done

# 7. UI smoke
open http://localhost:3000/research/models
open http://localhost:3000/research/models/sa-pr-ft-v1
```

## Definition of done

- [ ] Migrations `0058` and `0059` apply cleanly.
- [ ] All listed backend tests green.
- [ ] All listed Playwright tests green.
- [ ] Catalog page renders ≥ 1 active model end-to-end.
- [ ] Detail page renders eval history, training config (role-gated), and a working playground.
- [ ] Rate limit blocks guests at the documented threshold and admin bypasses it.
- [ ] Admin-only fields are never present in guest/user responses (verified by JSON snapshot tests).
- [ ] Sample prompts curated on `public_card` for every `active` model on first ship.

## Implementation notes

_(to be filled in after merge)_
