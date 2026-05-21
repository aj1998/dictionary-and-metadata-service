# 24 — Finetune Eval Harness Spec

Scope context: [`scope/06_advanced_rag_and_finetuning.md`](../../scope/06_advanced_rag_and_finetuning.md) ("Eval (cross-cutting)" — three suites).
Depends on: [`design/scope/22_finetune_training_infra_spec.md`](./22_finetune_training_infra_spec.md) (job triggers), [`design/scope/23_model_serving_registry_spec.md`](./23_model_serving_registry_spec.md) (the model under test is invoked via the gateway).

Three evaluation suites — extraction, relation, Q/A — each a stand-alone script callable as `python -m workers.finetune.eval.<suite> --model-id <id> [--job-id <id>]`. Scores are written to `model_registry.eval_scores` and a new `model_eval_runs` audit table. CI integration: every successful `finetune_jobs` row automatically triggers all three suites.

## Phase A — extraction eval

Tests whether the model can extract topic/keyword spans from a Hindi/English passage. Goldens are admin-curated span lists.

### Files

```
workers/finetune/eval/
├── __init__.py
├── extraction.py
├── relation.py
├── qa.py
├── common/
│   ├── runner.py                 invokes the model via spec 23 gateway
│   ├── llm_judge.py              for Q/A suite
│   ├── metrics.py                precision/recall/F1, span IOU, edge-set ops
│   └── persist.py                writes model_eval_runs + updates model_registry.eval_scores
├── prompts/
│   ├── extraction_system.txt
│   ├── relation_system.txt
│   └── qa_judge_rubric.txt       see Phase C
└── tests/
    ├── test_extraction_metrics.py
    ├── test_relation_metrics.py
    ├── test_qa_judge.py
    ├── test_runner.py
    └── test_ci_trigger.py

eval_datasets/
├── extraction/
│   ├── README.md
│   └── v1/                       JSONL goldens, see below
├── relation/
│   └── v1/
└── qa/
    └── v1/
```

### Golden format — extraction

`eval_datasets/extraction/v1/goldens.jsonl`, one row:

```json
{"id": "ext-0001",
 "passage": "<paragraph of Hindi text, ~200–500 chars>",
 "spans": [
   {"text": "आत्मा", "start": 12, "end": 17, "type": "Keyword", "kw_natural_key": "आत्मा"},
   {"text": "बहिरात्मादि-3-भेद", "start": 45, "end": 62, "type": "Topic",
    "topic_natural_key": "jainkosh:आत्मा:बहिरात्मादि-3-भेद"}
 ]}
```

Admin curates goldens via the admin UI (`ui/app/admin/eval-goldens/`); each golden has a `source_gatha_natural_key` so we can re-sample passages.

### Prompt + parser

```
# prompts/extraction_system.txt
You are a Jain-text annotator. Given a Hindi/English passage, list every Topic and Keyword span.
Output strict JSON: {"spans":[{"text":...,"start":...,"end":...,"type":"Topic"|"Keyword"}, ...]}
```

Parser: `json.loads`. On parse failure → row counts as zero recall, zero precision (penalised; not skipped).

### Metric: span-level P/R/F1 with IOU ≥ 0.5

```python
# metrics.py
def span_iou(a: Span, b: Span) -> float:
    if a.type != b.type: return 0.0
    inter = max(0, min(a.end, b.end) - max(a.start, b.start))
    union = max(a.end, b.end) - min(a.start, b.start)
    return inter / union if union else 0.0

def match_spans(gold: list[Span], pred: list[Span], iou_thresh: float = 0.5):
    """Greedy 1-1 matching maximising IOU."""
    ...
    return tp, fp, fn

def prf1(tp, fp, fn) -> tuple[float, float, float]:
    p = tp / (tp + fp) if (tp+fp) else 0.0
    r = tp / (tp + fn) if (tp+fn) else 0.0
    f = 2*p*r/(p+r) if (p+r) else 0.0
    return p, r, f
```

Report micro and macro (per-type) P/R/F1.

## Phase B — relation eval

Tests whether the model proposes the same `IS_A` / `PART_OF` / `RELATED_TO` edges as the admin-approved graph.

### Golden format — relation

`eval_datasets/relation/v1/goldens.jsonl`:

```json
{"id": "rel-0001",
 "passage": "<Hindi passage that grounds the edges>",
 "nodes": [
   {"nk": "आत्मा", "type": "Keyword"},
   {"nk": "बहिरात्मा", "type": "Keyword"}
 ],
 "edges": [
   {"from_nk": "बहिरात्मा", "to_nk": "आत्मा", "type": "IS_A"}
 ]}
```

Goldens are sampled from the graph: pick a small connected subgraph around a topic, take the Mongo extract that defines those nodes, save the (passage, nodes, edges) tuple.

### Prompt + metric

```
# prompts/relation_system.txt
Given a passage and a list of named nodes, propose every directed edge among them.
Allowed types: IS_A, PART_OF, RELATED_TO. RELATED_TO is undirected — emit (a,b) with type=RELATED_TO once.
Output: {"edges":[{"from_nk":...,"to_nk":...,"type":...}, ...]}
```

Metric: **edge-set P/R/F1**. `(from, to, type)` is the key; for `RELATED_TO`, treat as canonical sorted `(min(from,to), max(from,to), RELATED_TO)`.

```python
def edge_prf1(gold: set[Edge], pred: set[Edge]) -> tuple[float,float,float]:
    tp = len(gold & pred); fp = len(pred - gold); fn = len(gold - pred)
    return prf1(tp, fp, fn)
```

## Phase C — Q/A eval (LLM-as-judge)

Tests free-form Q/A answers against an expert-rated reference using an LLM judge with a fixed rubric.

### Golden format — Q/A

`eval_datasets/qa/v1/goldens.jsonl`:

```json
{"id": "qa-0001",
 "question": "आत्मा के तीन भेद कौन से हैं?",
 "reference_answer": "बहिरात्मा, अन्तरात्मा, परमात्मा।",
 "citations_required": ["jainkosh:आत्मा:बहिरात्मादि-3-भेद"],
 "domain": "philosophy|maths|sciences|astronomy|ethics|general"}
```

### Judge model

`anthropic:claude-opus-4-7` by default (via spec 23 gateway). Override via env `EVAL_JUDGE_MODEL_ID`.

### Rubric (verbatim — `prompts/qa_judge_rubric.txt`)

```
You are evaluating a Jain knowledge-system answer. Score on FIVE axes from 1 (worst) to 5 (best):

1. CORRECTNESS — facts in the answer match the reference. Hallucinations cap this at 2.
2. COMPLETENESS — every key element of the reference is present.
3. CITATION_FIDELITY — required citations (`citations_required`) appear and point at the right shastra/topic.
4. LANGUAGE — Hindi/English usage is fluent and appropriate to the question's language.
5. JAIN_ALIGNMENT — terminology and framing respect Jain tradition; no cross-tradition contamination.

Return strict JSON: {"correctness":N,"completeness":N,"citation_fidelity":N,"language":N,"jain_alignment":N,"comment":"..."}
where each N is an integer 1–5.

Overall = weighted mean: 0.30*correctness + 0.20*completeness + 0.20*citation_fidelity + 0.15*language + 0.15*jain_alignment.
```

The harness computes `overall` itself from the five integers — the judge does not return `overall`.

Aggregate over the suite: mean of overall plus per-axis means and per-domain breakdown.

### Anti-flake

- Each Q/A item is judged 3 times; the median of `overall` is used. Seeded by `(model_id, item_id, run_id)` for reproducibility (judge temperature 0).
- If parse fails, the item scores 1 across all axes (penalty over silent skip).

## Persistence

### Schema (migration `0043_model_eval_runs.py`)

```sql
CREATE TYPE eval_suite AS ENUM ('extraction','relation','qa');

CREATE TABLE model_eval_runs (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  model_id      TEXT NOT NULL REFERENCES model_registry(id) ON DELETE CASCADE,
  suite         eval_suite NOT NULL,
  goldens_path  TEXT NOT NULL,                  -- 'eval_datasets/extraction/v1/goldens.jsonl'
  goldens_sha   TEXT NOT NULL,                  -- sha256 of the goldens file at run time
  finetune_job_id UUID REFERENCES finetune_jobs(id) ON DELETE SET NULL,
  scores        JSONB NOT NULL,                 -- {micro_f1, macro_f1, by_type:{...}} or {overall, by_axis, by_domain}
  num_items     INT NOT NULL,
  duration_ms   INT NOT NULL,
  judge_model_id TEXT,                          -- for qa suite only
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_model_eval_runs_model ON model_eval_runs(model_id, created_at DESC);
```

After each run, the harness also writes a flat summary into `model_registry.eval_scores`:

```json
{
  "extraction": {"micro_f1": 0.71, "ran_at": "2026-05-21T..."},
  "relation":   {"micro_f1": 0.64, "ran_at": "..."},
  "qa":         {"overall": 4.12, "ran_at": "..."}
}
```

## CI integration

Spec 22 emits a Celery message `finetune.eval.run(job_id)` on `succeeded`. The handler:

```python
# workers/finetune/eval/tasks.py
@celery.task(name="finetune.eval.run")
def run_all_evals(job_id: str):
    job = pg.get(FinetuneJob, job_id)
    # The registry row was auto-created in 'staging' by spec 23's auto_register task
    model_id = pg.scalar(select(ModelRegistry.id).where(ModelRegistry.finetune_job_id==job_id))
    if model_id is None:
        raise Retry("registry row not yet created")
    for suite in ("extraction", "relation", "qa"):
        subprocess.run(["python","-m",f"workers.finetune.eval.{suite}",
                        "--model-id", model_id, "--job-id", str(job_id)], check=True)
```

The chained order is best-effort; failures in one suite do not block the others. Each subprocess writes its own `model_eval_runs` row.

## Pydantic contracts

```python
class ExtractionScores(BaseModel):
    micro_p: float; micro_r: float; micro_f1: float
    macro_p: float; macro_r: float; macro_f1: float
    by_type: dict[str, dict[str, float]]    # {'Keyword': {'p':..,'r':..,'f1':..}, 'Topic': {...}}
    num_items: int

class RelationScores(BaseModel):
    micro_p: float; micro_r: float; micro_f1: float
    by_type: dict[str, dict[str, float]]    # IS_A, PART_OF, RELATED_TO
    num_items: int

class QAScores(BaseModel):
    overall: float
    by_axis: dict[str, float]               # correctness, completeness, citation_fidelity, language, jain_alignment
    by_domain: dict[str, float]
    judge_model_id: str
    num_items: int
```

## Tests (TDD)

1. `test_extraction_metrics.py`: hand-crafted gold+pred → assert IOU≥0.5 matches exactly the expected pairings, P/R/F1 computed correctly; empty pred → P=0/R=0/F1=0.
2. `test_relation_metrics.py`: canonical-sort of `RELATED_TO` ensures `(a,b)` == `(b,a)`; direction matters for `IS_A`.
3. `test_qa_judge.py`: with a stubbed judge returning fixed JSON, harness computes `overall` matching the weighted formula; median-of-3 path exercised.
4. `test_runner.py`: model call routed through `LLMRouter` to the gateway (spec 23); parse failure penalises.
5. `test_persist.py`: writes `model_eval_runs` row with goldens_sha; updates `model_registry.eval_scores` json.
6. `test_ci_trigger.py`: simulating `finetune_jobs.status='succeeded'` → all three suites enqueued; failure in one does not block others.
7. `test_goldens_validation.py`: malformed JSONL goldens (missing field, bad span offsets) → harness errors before invoking the model.

Fixtures: 5-row goldens in each suite; use a tiny stubbed model returning canned JSON.

## Admin UI

```
ui/app/admin/eval/
├── page.tsx                       latest eval per (model, suite) — table with sortable score columns
├── [model_id]/page.tsx            historical chart of scores per suite for a model
└── goldens/
    ├── page.tsx                   list of goldens with edit / add
    └── [suite]/[id]/page.tsx      goldens editor (span picker for extraction; node/edge picker for relation; Q/A form)
```

Adding/editing a golden bumps a new version directory (`eval_datasets/<suite>/v<n>/`). The next eval run picks the latest version unless `--goldens-version` is passed.

## Manual verification

```bash
# Make sure a model is active in registry
curl http://localhost:8008/v1/models | jq .

# Run all three suites
python -m workers.finetune.eval.extraction --model-id jinvani-graph-ft-v1
python -m workers.finetune.eval.relation   --model-id jinvani-graph-ft-v1
python -m workers.finetune.eval.qa         --model-id jinvani-graph-ft-v1

# Inspect
psql -c "SELECT suite, scores, num_items FROM model_eval_runs
         WHERE model_id='jinvani-graph-ft-v1' ORDER BY created_at DESC LIMIT 3;"
psql -c "SELECT id, eval_scores FROM model_registry WHERE id='jinvani-graph-ft-v1';"
```

## Definition of done

- [ ] Migration `0043_model_eval_runs.py` applies cleanly.
- [ ] Three suite scripts run end-to-end against the gateway and persist rows.
- [ ] Each metric file has ≥3 unit tests covering edge cases (empty, perfect, partial).
- [ ] Judge median-of-3 + parse-failure-penalty paths exercised.
- [ ] CI hook proven: a stubbed `finetune_jobs.status='succeeded'` triggers all three suites.
- [ ] Admin UI shows scores per model and lets goldens be edited; new versions appear in `eval_datasets/<suite>/`.
- [ ] At least 30 goldens per suite seeded under `eval_datasets/<suite>/v1/` (curated separately; spec only requires the format + count).

## Implementation notes

_(to be filled in after merge)_
