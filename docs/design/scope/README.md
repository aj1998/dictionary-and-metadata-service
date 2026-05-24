# Design Scope Specs — Jinvani SAAR

Code-level, phase-wise implementation specs for the SAAR vision. Each spec is sized for a single implementing-agent context window per [AGENTS.md](../../../AGENTS.md). High-level scope lives in [`../../scope/`](../../scope/).

## Reading order

1. Read scope docs first: [`scope/00_overview.md`](../../scope/00_overview.md) → [`02_foundation_status.md`](../../scope/02_foundation_status.md).
2. Read foundational design docs: [`02_data_model_postgres.md`](../data_model/02_data_model_postgres.md), [`03_data_model_mongo.md`](../data_model/03_data_model_mongo.md), [`04_data_model_graph.md`](../data_model/04_data_model_graph.md).
3. Pick a spec and ship it; the "definition of done" at the bottom is the merge bar.

## Spec index

### Platform

| # | Spec | Phase split | Depends on |
|---|---|---|---|
| 01 | [User accounts & preferences](./01_user_accounts_spec.md) | A: auth-service + JWT, B: prefs/saved-views/highlights | 02_data_model_postgres |

### Reading layer

| # | Spec | Phase split | Depends on |
|---|---|---|---|
| 02 | [Shastra layout configs](./02_shastra_layout_configs_spec.md) | A: schema + loader, B: admin editor | 03_data_model_mongo |
| 03 | [Shastra Reader UI](./03_shastra_reader_ui_spec.md) | A: page shell + panels, B: panels integration | 02, 04, 12 |
| 04 | [Keyword hover/click expansion](./04_keyword_hover_expansion_spec.md) | single phase | data-service /keywords |
| 05 | [Drush-taant image generation](./05_drushtaant_image_gen_spec.md) | A: gen worker, B: review UI, C: render in reader | 03 |
| 06 | [Audio reader (ElevenLabs)](./06_audio_reader_elevenlabs_spec.md) | A: generation, B: streaming + UI | 03 |
| 07 | [PDF export](./07_pdf_export_spec.md) | single phase | 03 |
| 12 | [JainKosh highlight overlay](./12_jainkosh_highlight_overlay_spec.md) | single phase | 08, 09 (spans from pipeline) |

### Translation / enrichment

| # | Spec | Phase split | Depends on |
|---|---|---|---|
| 08 | [Translation pipeline — extraction](./08_translation_pipeline_extraction_spec.md) | A: spans table, B: Stage A + B workers, C: review queue | 04_data_model_graph |
| 09 | [Translation pipeline — AI flow](./09_translation_pipeline_ai_flow_spec.md) | single phase (prompts + JSON contracts) | 08 |
| 10 | [Topic / keyword counters](./10_topic_keyword_counters_spec.md) | A: schema, B: recompute jobs, C: API | 02 |
| 11 | [Topic hierarchy AI](./11_topic_hierarchy_ai_spec.md) | A: candidate gen, B: review UI, C: graph apply | 08, 09 |
| 13 | [Categorisation pipeline](./13_categorisation_pipeline_spec.md) | single phase | 08 |
| 14 | [Vitrag-elibrary dictionary ingest](./14_vitrag_dictionary_ingest_spec.md) | A: scrape + parse, B: review, C: publish | 02 |
| 15 | [Multilingual keyword/topic storage](./15_multilingual_keyword_storage_spec.md) | single phase | 02 |
| 16 | [Kn/Gu OCR pipeline](./16_kn_gu_ocr_pipeline_spec.md) | A: OCR scaffold, B: mapping, C: ingest | 15 |

### Retrieval / A-V

| # | Spec | Phase split | Depends on |
|---|---|---|---|
| 17 | [Advanced RAG enhancements](./17_advanced_rag_enhancements_spec.md) | A: graph-aware re-rank, B: observability | query-service /graphrag |
| 18 | [A/V RAG pipeline](./18_av_rag_pipeline_spec.md) | A: STT, B: chunk + tag, C: index | 17 |
| 19 | [Jinswara Q/A ingest](./19_jinswara_qna_ingest_spec.md) | A: parse + table, B: graph link, C: AI page tile | 04_data_model_graph |
| 20 | [Flowchart / table / graph scanner](./20_flowchart_table_graph_scanner_spec.md) | A: detector, B: storage, C: AI page render | 03_data_model_mongo |

### Finetuning

| # | Spec | Phase split | Depends on |
|---|---|---|---|
| 21 | [Finetune dataset export](./21_finetune_dataset_export_spec.md) | A: corpus snapshot, B: per-task formatters | 02, 03, 04 |
| 22 | [Finetune training infra](./22_finetune_training_infra_spec.md) | A: Modal/RunPod runner, B: LoRA recipe, C: registry hook | 21, 23 |
| 23 | [Model serving registry](./23_model_serving_registry_spec.md) | A: registry table, B: vLLM serve, C: router | 22 |
| 24 | [Finetune eval harness](./24_finetune_eval_harness_spec.md) | A: extraction eval, B: relation eval, C: Q/A eval | 21 |
| 25 | [Graph-understanding finetune](./25_graph_understanding_finetune_spec.md) | A: synthetic data, B: train, C: serve | 21, 22, 23 |
| 26 | [Sanskrit / Prakrit translation models](./26_sanskrit_prakrit_model_spec.md) | A: data assembly, B: LoRA, C: serve | 21, 22, 23 |

### Research workspaces

| # | Spec | Phase split | Depends on |
|---|---|---|---|
| 27 | [Siri Bhoovalay workspace](./27_siri_bhoovalay_workspace_spec.md) | A: chakra viewer + path engine, B: decoding panel + LLM helper | 26 |
| 28 | [Research tools framework](./28_research_tools_framework_spec.md) | single phase (plugin contract) | 23 |
| 29 | [Research models index](./29_research_models_index_spec.md) | single phase | 22, 23 |

## Dependency graph (high-level)

```
02_data_model_postgres ─┐
03_data_model_mongo     ├─► 01_user_accounts ─► UI (03_shastra_reader_ui)
04_data_model_graph     ┘
                          │
                          ├─► 02_shastra_layouts ─► 03_shastra_reader_ui
                          │                        │
                          │                        ├─► 04_hover_expansion
                          │                        ├─► 05_drushtaant
                          │                        ├─► 06_audio
                          │                        ├─► 07_pdf
                          │                        └─► 12_jainkosh_highlights
                          │
                          ├─► 14_vitrag_ingest ─► 08_extraction ─► 09_ai_flow
                          │                                        │
                          │                                        ├─► 10_counters
                          │                                        ├─► 11_hierarchy
                          │                                        ├─► 13_categorisation
                          │                                        └─► 15_multilingual ─► 16_kn_gu_ocr
                          │
                          ├─► 17_advanced_rag ─► 18_av_rag
                          │                     19_jinswara
                          │                     20_flowchart
                          │
                          └─► 21_dataset_export ─► 22_training ─► 23_serving
                                                                  │
                                                                  ├─► 24_eval
                                                                  ├─► 25_graph_ft
                                                                  ├─► 26_sa_pr_model ─► 27_siri_bhoovalay
                                                                  ├─► 28_tools_framework
                                                                  └─► 29_research_models
```

## Conventions for every spec

- **Module path** under `services/`, `workers/`, `packages/jain_kb_common/`, or `ui/` is given explicitly.
- **Database changes** ship as a numbered Alembic migration with the table DDL pasted into the spec.
- **API contracts** use OpenAPI-fragment-style Pydantic models.
- **Tests** are TDD: one failing test per phase, listed up front.
- **Manual verification** steps at the bottom of each spec for the user.
- **Implementation notes** section left empty; the implementing agent fills it after merging.

## Phasing for product owner

Phasing is intentionally not pinned here; the product owner will decide rollout in a separate `phasing.md` once specs are reviewed. Every spec is **independently mergeable** once its dependencies are met.
