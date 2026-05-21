# 06 — Advanced RAG & Finetuning

The AI layer behind the #AI page and ResearchTools. Combines retrieval enhancements, A/V ingestion, Jinswara Q/A, and a full finetune + serving pipeline.

## Retrieval enhancements (Advanced RAG)

### Existing baseline

- `cataloguesearch` — vector + BM25 over OCRed shastra chunks.
- `cataloguesearch-chat` — LLM chat that consumes cataloguesearch hits.
- `query-service /graphrag` — keyword resolve → topic graph expansion → re-rank → return as enrichment for chat.

### Enhancements

1. **GraphRAG-first re-rank** in cataloguesearch — use the topic graph to up-weight chunks whose tags overlap with the query's resolved keyword set. Spec: `design/scope/17_advanced_rag_enhancements_spec.md`.
2. **Jinswara Q/A ingestion** — Jinswara is a Jain Q/A site; verified-author Q/As become a new node type in the graph (`JinswaraQnA`) with edges to `Topic`, `Keyword`, and `Author`. Vectorless retrieval: when a user query semantically matches a Q&A's question, the answer is returned as a citation tile. Spec: `design/scope/19_jinswara_qna_ingest_spec.md`.
3. **A/V RAG** — YouTube pravachans of verified authors are speech-to-text transcribed, chunked, tagged with topics/keywords via the enrichment pipeline, and indexed alongside text chunks in cataloguesearch. Spec: `design/scope/18_av_rag_pipeline_spec.md`.
4. **Flowchart / table / diagram retrieval** — OCRed shastras often contain pre-existing flowcharts, tables, and diagrams. A separate scanner identifies and crops them; they become `Flowchart` nodes linked to the gathas/topics they appear with. The AI page renders them inline when retrieved. Spec: `design/scope/20_flowchart_table_graph_scanner_spec.md`.

### Observability

The graph doubles as the *evaluation lens* for retrieval quality. We can answer: "which queries hit no graph nodes?", "which chunks have low graph connectivity?", "which topics have no chunk citations?". These become admin dashboards in the existing admin UI. Spec: `design/scope/17_advanced_rag_enhancements_spec.md` (observability section).

## Finetuning

Four model families. All trained, registered, and served in-house (per product decision).

| Model family | Purpose | Architecture | Training data |
|---|---|---|---|
| **Graph-understanding model** | Take a natural-language question, emit a graph query (Cypher or our internal traversal spec). Replaces the hand-tuned ranker over time. | LoRA over an open base (Llama-3.1-8B-Instruct or Qwen-2.5-7B). | Graph schema + relation extraction + JainKosh keyword definitions; synthetic (Cypher, question) pairs. |
| **Jainism main model** | Q/A and reasoning over the full Hindi+English corpus (graph + Mongo extracts). | LoRA + DPO over a 13–34B open base. | All approved gathas, bhaavarths, JainKosh keyword definitions, topics, Jinswara Q/As, pravachans. |
| **Research-domain models** | One per domain (Maths, Sciences, Philosophy, Astronomy, Ethics). Each blends Jain canonical content with corresponding modern domain context. | LoRA from the Jainism main checkpoint. | Filtered Jainism data + curated modern-domain pairs (text-book Q/A, papers). |
| **Language models (Sa, Pr, Kn, Gu, Ta)** | Keyword / short-phrase translation between Hin/En and the target. | LoRA over multilingual base (Llama-3 multilingual or IndicTrans2). | Vitrag-elibrary, ocr-dict, manually curated phrase pairs from the graph. |

### Pipeline

```
graph + mongo  ──► dataset_export (spec 21) ──► dataset versioned in S3
                                                   │
                                                   ▼
                                             training (spec 22)
                                                   │
                                                   ▼
                                         checkpoint → eval (spec 24)
                                                   │
                                              pass eval?
                                              /         \
                                           yes           no
                                            │             │
                                            ▼             ▼
                              model_registry (spec 23)   loop
                                            │
                                            ▼
                                     vLLM/Ollama serve
                                            │
                                            ▼
                                AI page model picker / query-service
```

### Infra footprint

- Training: 1× A100 80GB or 2× L40S (rented) per family. LoRA only at first.
- Serving: 1× L4 or A10G can hold a 7-8B LoRA-merged model with vLLM. The Jainism main 34B needs A100 with quantisation.
- Storage: S3-compatible bucket for datasets + checkpoints. Versioned by date.

Spec set: `21_finetune_dataset_export_spec.md`, `22_finetune_training_infra_spec.md`, `23_model_serving_registry_spec.md`, `24_finetune_eval_harness_spec.md`, `25_graph_understanding_finetune_spec.md`, `26_sanskrit_prakrit_model_spec.md`.

## Eval (cross-cutting)

Three eval suites:

1. **Topic/keyword extraction** — vs. human-extracted goldens. Used both for the enrichment pipeline and to test whether a finetuned model can replace the LLM call.
2. **Relation extraction** — propose `IS_A` / `PART_OF` / `RELATED_TO` edges; compare to admin-approved edges.
3. **Domain Q/A** — small expert-graded set per research domain.

Every model version gets a row in `model_registry` with eval scores; the admin UI surfaces these for rollout decisions.

## Definition of done

- [ ] At least one finetune (graph-understanding) trained and served via the registry.
- [ ] AI page model picker switches between base + ≥ 1 finetuned model.
- [ ] Jinswara Q/A ingestion live for ≥ 2 verified authors.
- [ ] A/V RAG transcribes + indexes ≥ 10 pravachans.
- [ ] Flowchart scanner extracts ≥ 100 figures from one OCRed shastra.
- [ ] Eval harness runs all three suites on every checkpoint and writes scores to `model_registry`.
