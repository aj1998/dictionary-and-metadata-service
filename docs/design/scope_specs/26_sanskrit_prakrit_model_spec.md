# 26 — Sanskrit / Prakrit Translation Model Spec

Scope context: [`scope/06_advanced_rag_and_finetuning.md`](../../scope/06_advanced_rag_and_finetuning.md) (Language models row — Sa, Pr).
Depends on: [`design/scope/21_finetune_dataset_export_spec.md`](./21_finetune_dataset_export_spec.md) (dataset row), [`design/scope/22_finetune_training_infra_spec.md`](./22_finetune_training_infra_spec.md) (trainer), [`design/scope/23_model_serving_registry_spec.md`](./23_model_serving_registry_spec.md) (registry + serve), [`design/scope/24_finetune_eval_harness_spec.md`](./24_finetune_eval_harness_spec.md) (eval), [`design/scope/09_translation_pipeline_ai_flow_spec.md`](./09_translation_pipeline_ai_flow_spec.md) (consumer — supplementary translator).

Build a Sanskrit↔Hindi and Prakrit↔Hindi translation model by assembling parallel pairs from the existing shastra JSONs (every gatha already has `sanskrit_or_prakrit` source + `hi_translation` field), LoRA-training on a multilingual base (IndicTrans2-1B by default; Llama-3.1-8B as alt), and serving via the spec 23 registry. The output is consumed by the translation pipeline (spec 09) as a *supplementary* translator — it runs alongside the main LLM and its output is offered to reviewers as a second opinion, never as the sole truth.

## Phase A — parallel corpus assembly

### Files

```
workers/sa_pr_data_assembly/
├── __init__.py
├── main.py                  Celery worker entry: tasks.build_corpus(version, seed)
├── config.py                Settings (DATABASE_URL, MONGO_URL, S3_BUCKET,
│                            SHASTRA_JSON_ROOT="data/shastras/", SEED_DEFAULT=42,
│                            MIN_ALIGNMENT_CONFIDENCE=0.6)
├── extractors/
│   ├── __init__.py
│   ├── json_loader.py       walk parser_configs/shastras/*.json + Mongo gathas
│   ├── verse_align.py       verse-by-verse alignment using gatha_natural_key
│   ├── lang_id.py            fasttext lid.176; classify each source as 'san' or 'pra'
│   └── script_normalise.py  IAST/Devanagari/Kannada→Devanagari via aksharamukha
├── dedupe.py                cross-edition dedupe (different editions of same shastra)
├── filters.py               length filter, character-set filter, profanity filter (none here)
├── splitter.py              90/5/5 train/val/test by shastra_id (prevents leakage)
└── tests/
    ├── conftest.py
    ├── fixtures/
    │   ├── shastra_with_san.json
    │   └── shastra_with_pra.json
    ├── test_alignment_from_json.py
    ├── test_lang_id_san_vs_pra.py
    ├── test_dedupe_across_editions.py
    ├── test_script_normalise.py
    ├── test_splitter_no_shastra_leakage.py
    └── test_end_to_end_corpus.py
```

### Postgres schema (migration `0044_parallel_corpus.py`)

```sql
CREATE TYPE corpus_src_lang AS ENUM ('san','pra');
CREATE TYPE corpus_tgt_lang AS ENUM ('hin','eng');
CREATE TYPE corpus_status   AS ENUM ('extracted','reviewed','rejected','published');

CREATE TABLE parallel_corpus_pairs (
  id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  src_lang             corpus_src_lang NOT NULL,
  src_script           TEXT NOT NULL,                        -- 'deva' | 'iast' | 'kn' (pre-normalised)
  src_text             TEXT NOT NULL,
  src_text_norm        TEXT NOT NULL,                        -- normalised to Devanagari for dedupe
  tgt_lang             corpus_tgt_lang NOT NULL,
  tgt_text             TEXT NOT NULL,
  source_shastra_id    UUID NOT NULL REFERENCES shastras(id) ON DELETE CASCADE,
  source_verse_ref     TEXT NOT NULL,                        -- e.g. 'gatha:gomatsar_jiv_kand:42'
  gatha_id             UUID REFERENCES gathas(id) ON DELETE SET NULL,
  alignment_confidence REAL NOT NULL,                        -- 0..1
  status               corpus_status NOT NULL DEFAULT 'extracted',
  reviewer_id          UUID REFERENCES users(id) ON DELETE SET NULL,
  reviewer_notes       TEXT,
  created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (source_shastra_id, source_verse_ref, src_lang, tgt_lang)
);

CREATE INDEX idx_parallel_src_lang_status ON parallel_corpus_pairs(src_lang, status);
CREATE INDEX idx_parallel_gatha           ON parallel_corpus_pairs(gatha_id);
CREATE INDEX idx_parallel_src_text_norm   ON parallel_corpus_pairs USING hash(src_text_norm);
```

### Pydantic contracts

```python
class CorpusPairOut(BaseModel):
    id: UUID
    src_lang: Literal['san','pra']
    src_script: str
    src_text: str
    tgt_lang: Literal['hin','eng']
    tgt_text: str
    source_shastra_id: UUID
    source_verse_ref: str
    gatha_id: UUID | None
    alignment_confidence: float
    status: Literal['extracted','reviewed','rejected','published']

class CorpusReviewIn(BaseModel):
    status: Literal['reviewed','rejected','published']
    reviewer_notes: str | None = None
```

### Alignment

Each shastra JSON already lists gathas with fields `sanskrit_or_prakrit` and `hi_translation`. The aligner is therefore mostly bookkeeping:

```python
# workers/sa_pr_data_assembly/extractors/verse_align.py
def align_shastra(shastra_id: UUID, json_path: Path) -> Iterator[CorpusPair]:
    doc = json.loads(json_path.read_text())
    for verse in doc["gathas"]:
        src = verse.get("sanskrit_or_prakrit")
        tgt = verse.get("hi_translation")
        if not src or not tgt:
            continue
        lang = detect_san_vs_pra(src)            # 'san' or 'pra'
        norm = aksharamukha.transliterate(src, source="auto", target="Devanagari")
        confidence = score_alignment(src, tgt)   # heuristic: len ratio, named-entity overlap
        yield CorpusPair(
            src_lang=lang, src_script="deva", src_text=src, src_text_norm=norm,
            tgt_lang="hin", tgt_text=tgt,
            source_shastra_id=shastra_id,
            source_verse_ref=f"gatha:{doc['natural_key']}:{verse['number']}",
            gatha_id=resolve_gatha_id(shastra_id, verse["number"]),
            alignment_confidence=confidence,
        )
```

`detect_san_vs_pra` uses fasttext lid.176 if available, else a Prakrit-marker heuristic (presence of `ण` over `न`, `-त्ता`, `-स्स`, etc.). Confidence < `MIN_ALIGNMENT_CONFIDENCE` rows are still stored but with `status='extracted'`; the review UI surfaces them at the top.

### Dedupe across editions

Same gatha frequently appears in multiple editions (e.g. two PDFs of `Gomatsar Jiv Kand` with different OCR). Dedupe key: `(src_lang, src_text_norm, tgt_lang)`. When a duplicate is detected, keep the row with higher `alignment_confidence`; the loser is marked `status='rejected'` with `reviewer_notes='cross_edition_duplicate_of:<winner_id>'`.

### Output to dataset

After review, `published` rows are serialised by `tasks.export_dataset(version)` into JSONL for IndicTrans2's `<src_tag><tgt_tag>` format and Llama chat-SFT format (two separate dataset rows in `finetune_datasets`):

```
s3://jinvani-finetune-datasets/sa_pr/<version>/indictrans/
├── train.jsonl     {"src":"<2san> <2hin> <src_norm>", "tgt":"<tgt_hin>"}
├── val.jsonl
└── test.jsonl

s3://jinvani-finetune-datasets/sa_pr/<version>/chat_sft/
├── train.jsonl     {"messages":[{system, user="Translate Sanskrit to Hindi: ...", assistant=...}]}
├── val.jsonl
└── test.jsonl
```

### Splitter

By `source_shastra_id` modulo 20 → 0–17 train, 18 val, 19 test. Prevents memorisation across editions of the same shastra. Implementation in `splitter.py` mirrors spec 25's hash-based splitter.

### Tests (TDD — write first)

1. `test_alignment_from_json.py::test_one_gatha_yields_one_pair` — fixture shastra JSON → exactly 1 row per verse with both fields.
2. `test_alignment_from_json.py::test_missing_translation_skipped`.
3. `test_lang_id_san_vs_pra.py::test_classical_sanskrit_classified_as_san`.
4. `test_lang_id_san_vs_pra.py::test_jain_prakrit_classified_as_pra` — `ण-` and `-स्स` markers force `pra`.
5. `test_dedupe_across_editions.py::test_same_norm_text_dedup` — two rows with identical `src_text_norm` → one published, one rejected with cross-edition note.
6. `test_dedupe_across_editions.py::test_higher_confidence_wins`.
7. `test_script_normalise.py::test_iast_to_deva` — `"jīva"` → `"जीव"`.
8. `test_script_normalise.py::test_kannada_to_deva`.
9. `test_splitter_no_shastra_leakage.py::test_shastra_never_in_train_and_eval`.
10. `test_end_to_end_corpus.py::test_smoke_writes_rows_and_dataset` — run against the two fixture shastras; assert PG rows + S3 JSONL + `finetune_datasets` row.

### Admin review endpoints (on `metadata-service`)

```
GET    /admin/parallel-corpus?src_lang=san&status=extracted&min_conf=0.3
GET    /admin/parallel-corpus/{id}
POST   /admin/parallel-corpus/{id}/review     body: CorpusReviewIn
POST   /admin/parallel-corpus/bulk-publish    body: { ids: [UUID, ...] }
GET    /admin/parallel-corpus/stats           returns per-shastra counts by status
```

Standard `require_role('admin','reviewer')` on every route.

## Phase B — LoRA training

### Recipes

Two recipes under `recipes/finetune/sa_pr_translate/`:

```
recipes/finetune/sa_pr_translate/
├── recipe_indictrans2.yaml     base: ai4bharat/indictrans2-en-indic-1B (use indic-en variant for src→tgt direction)
├── recipe_llama8b.yaml         base: meta-llama/Llama-3.1-8B-Instruct
├── prompt.py                   format_prompt(src_text, src_lang, tgt_lang)
└── README.md
```

`recipe_indictrans2.yaml`:

```yaml
task: sa_pr
base_model: ai4bharat/indictrans2-indic-indic-1B
recipe: lora_sft
hp_overrides:
  r: 16
  lora_alpha: 32
  lora_dropout: 0.1
  target_modules: encoder+decoder attn          # resolved by trainer's family map
  lr: 3.0e-4
  per_device_train_batch_size: 16
  gradient_accumulation_steps: 2
  num_train_epochs: 5
  max_seq_length: 512
gpu_class: A100-40GB
```

`recipe_llama8b.yaml` mirrors the values from spec 22's `(sa_pr, Llama-3.1-8B)` row.

### Prompt format (chat-SFT path)

```python
SYSTEM = "You translate Jain canonical verses. Output Hindi only. Preserve proper nouns."

def format_prompt(src_text: str, src_lang: Literal['san','pra'], tgt_lang: Literal['hin']):
    lang_name = {'san': 'Sanskrit', 'pra': 'Prakrit'}[src_lang]
    return [
        {"role": "system",    "content": SYSTEM},
        {"role": "user",      "content": f"Translate {lang_name} to Hindi:\n{src_text}"},
    ]
```

### Trigger

```bash
DATASET_ID=$(psql -tAc "SELECT id FROM finetune_datasets WHERE name='sa_pr_v1_indictrans' ORDER BY created_at DESC LIMIT 1")

curl -X POST http://localhost:8001/admin/finetune/jobs \
  -b cookies.txt -H 'content-type: application/json' \
  -d "{\"dataset_id\":\"$DATASET_ID\",\"base_model\":\"ai4bharat/indictrans2-indic-indic-1B\",\"recipe\":\"lora_sft\",\"gpu_class\":\"A100-40GB\"}"
```

Auto-register on success creates `model_registry` row id `sa-pr-ft-v<n>` in `staging` (spec 23 hook).

### Tests (TDD)

1. `test_recipe_loads.py::test_indictrans_yaml_parses`.
2. `test_recipe_loads.py::test_llama_yaml_parses`.
3. `test_train_smoke.py::test_one_step_on_tiny_seq2seq` (gated by `RUN_GPU_TESTS=1`) — `Helsinki-NLP/opus-mt-mul-en` as tiny stand-in for IndicTrans2, 1 step, 10 rows → adapter exists.
4. `test_prompt_format.py::test_san_prompt_says_sanskrit`.
5. `test_prompt_format.py::test_pra_prompt_says_prakrit`.

## Phase C — eval + serve + pipeline integration

### Eval metrics (spec 24 harness extended)

- **chrF** (sacrebleu, `--metrics chrf`) — primary translation metric, character-level n-gram F-score.
- **BLEU** (sacrebleu, default tokeniser `13a`) — secondary, surfaced in admin UI for parity with common literature.
- **Manual scholar review queue** — top-100 lowest-chrF predictions are pushed to `admin/parallel-corpus-eval-queue` for scholar grading on a 1–5 scale; the average becomes `eval_scores.manual_score`.

Output written to `finetune_jobs.eval_scores` and mirrored to `model_registry.eval_scores`:

```json
{
  "chrf": {"san_hin": 48.2, "pra_hin": 41.7},
  "bleu": {"san_hin": 22.1, "pra_hin": 17.4},
  "manual_score": null,
  "macro_chrf": 44.95
}
```

Promotion bar (admin-overridable in spec 24): `macro_chrf >= 35` AND no per-direction chrF below 30.

### Serve

Same flow as spec 25:

- vLLM container (for Llama-8B variant): `--enable-lora --lora-modules sa-pr-ft-v1=...`.
- For the IndicTrans2 variant, spec 23 registry row uses `serve_target='vllm'` against a vLLM `seq2seq` container *(vLLM ≥ 0.6 supports encoder-decoder)*; if the vLLM build does not yet support it, fall back to `serve_target='ollama'` with a `gguf` quantisation, or `disabled` and call directly via an HF-text-generation-inference sidecar (`endpoint_url=http://hf-tgi-sa-pr:8080`).
- `unit_cost_usd_per_1k_*` is populated from spec 23 defaults for the chosen base.

### Pipeline integration (spec 09 — translation AI flow)

Spec 09 currently produces `hi_translation` for each Sa/Pr source by calling the main LLM. After this spec ships, spec 09 gains an additional step:

```
main_llm_translation     ─┐
                          ├─► reviewer UI shows both, can accept either or merge
sa_pr_ft_translation     ─┘
```

Implementation: `services/translation_pipeline/ai_flow.py` adds a second call:

```python
from jain_kb_common.llm.router import LLMRouter
router = LLMRouter()

async def supplementary_translate(src_text: str, src_lang: str) -> str | None:
    if not feature_flag("USE_SA_PR_FT_MODEL"):
        return None
    try:
        reply = await router.chat(
            model_id="sa-pr-ft-v1",
            messages=format_prompt(src_text, src_lang, 'hin'),
            max_tokens=512, temperature=0.0,
        )
        return reply.choices[0].message.content
    except Exception as e:
        logger.warning("sa_pr_ft_unavailable", exc_info=e)
        return None
```

The two translations are stored as `translation_candidates` rows (existing table in spec 09) with `source ∈ {main_llm, sa_pr_ft}`. The review UI (spec 09 Phase C) already supports multiple candidates.

### Consumer: Siri Bhoovalay (spec 27)

The Bhoovalay workspace calls `POST /v1/bhoovalay/score-path` which under the hood asks model-serving for an LM score in `san` or `pra`. That endpoint expects a `/v1/lm/score` route on model-serving (spec 23). For this spec, we additionally publish:

```
POST /v1/lm/score  (on model-serving-service)
  body:    { text, model_id }
  returns: { perplexity: float, tokens: int, model_id, served_by }
```

`model-serving-service` (spec 23) computes perplexity by calling the underlying model with `logprobs=true` and summing token negative log-likelihoods. The Sa/Pr finetune emits well-calibrated logprobs because it was trained with standard cross-entropy.

### Tests (TDD)

1. `test_eval_harness_invocation.py::test_chrf_computed_per_direction`.
2. `test_eval_harness_invocation.py::test_bleu_computed_per_direction`.
3. `test_eval_harness_invocation.py::test_macro_chrf_average`.
4. `test_promotion_rule.py::test_below_bar_stays_staging`.
5. `test_registry_registration.py::test_succeeded_job_creates_staging_row` — simulated `finetune_jobs.status='succeeded'` → `model_registry` row id matches `sa-pr-ft-v<n>`.
6. `test_pipeline_integration.py::test_flag_off_skips_supplementary` — feature flag unset → only main LLM candidate created.
7. `test_pipeline_integration.py::test_flag_on_creates_two_candidates`.
8. `test_pipeline_integration.py::test_model_unavailable_does_not_break_pipeline` — gateway 503 → main LLM candidate still saved.
9. `test_lm_score_route.py::test_perplexity_decreases_with_better_text`.

## Manual verification

```bash
# 1. Assemble corpus
celery -A workers.sa_pr_data_assembly.main call tasks.build_corpus \
  --args '["sa_pr_v1", 42]'

psql -c "SELECT src_lang, status, count(*) FROM parallel_corpus_pairs GROUP BY 1,2;"

# 2. Review a handful of rows in the admin UI, mark them 'published'
open http://localhost:3000/admin/parallel-corpus?src_lang=san

# 3. Export dataset
celery -A workers.sa_pr_data_assembly.main call tasks.export_dataset --args '["sa_pr_v1"]'

# 4. Train (spec 22)
DATASET_ID=$(psql -tAc "SELECT id FROM finetune_datasets WHERE name='sa_pr_v1_indictrans'")
curl -X POST http://localhost:8001/admin/finetune/jobs -b cookies.txt \
  -H 'content-type: application/json' \
  -d "{\"dataset_id\":\"$DATASET_ID\",\"base_model\":\"ai4bharat/indictrans2-indic-indic-1B\",\"recipe\":\"lora_sft\"}"

# 5. Promote on eval pass
curl -X POST http://localhost:8001/admin/models/sa-pr-ft-v1/status -b cookies.txt \
  -d '{"status":"active"}'

# 6. Call via gateway
curl -X POST http://localhost:8008/v1/chat/completions -H 'content-type: application/json' \
  -d '{"model":"sa-pr-ft-v1",
       "messages":[{"role":"system","content":"You translate Jain canonical verses. Output Hindi only."},
                   {"role":"user","content":"Translate Sanskrit to Hindi:\nजीवाजीवौ हि सिद्धान्तस्य मूलम्"}],
       "max_tokens":128}'

# 7. LM score (used by spec 27 Bhoovalay)
curl -X POST http://localhost:8008/v1/lm/score -H 'content-type: application/json' \
  -d '{"text":"जीवाजीवौ हि सिद्धान्तस्य मूलम्","model_id":"sa-pr-ft-v1"}'
```

## Definition of done

- [ ] Migration `0044_parallel_corpus.py` applies cleanly.
- [ ] Corpus assembly worker runs against the current shastra JSONs and produces ≥ 20k `extracted` rows across `san` and `pra`.
- [ ] Cross-edition dedupe collapses duplicates with reviewer notes pointing at the winner.
- [ ] Admin review endpoints + UI page work for `published` flip and bulk publish.
- [ ] Dataset export produces both IndicTrans2-format and chat-SFT-format JSONL with a `finetune_datasets` row each.
- [ ] LoRA training succeeds for at least the IndicTrans2 recipe within the cost cap.
- [ ] Eval harness writes chrF + BLEU + macro to `finetune_jobs.eval_scores`.
- [ ] Auto-registered `model_registry` row promotes to `active` only when bar met.
- [ ] Translation pipeline (spec 09) creates a second `translation_candidates` row from the finetune when the flag is on; reviewer UI shows both.
- [ ] `POST /v1/lm/score` returns perplexity such that spec 27 Bhoovalay's score panel renders.

## Implementation notes

_(to be filled in after merge)_
