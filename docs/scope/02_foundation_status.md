# 02 — Foundation Status & Gap Analysis

What exists today, what the SAAR vision adds, and which docs in `design/scope/` fill each gap.

## ✅ Already implemented

| Capability | Where | Notes |
|---|---|---|
| Postgres schema (authors, shastras, teekas, books, pravachans, keywords, aliases, gathas, topics, ingestion runs, review queue, topic candidates, query logs) | `design/02_data_model_postgres.md` + Alembic migrations | source of truth for IDs |
| Mongo collections (gatha texts, teeka mappings, keyword definitions, topic extracts, kalashas, raw HTML) | `design/03_data_model_mongo.md` | |
| Neo4j graph (Keyword, Topic, Alias, Gatha, Shastra nodes; IS_A, PART_OF, RELATED_TO, ALIAS_OF, HAS_TOPIC, MENTIONS_KEYWORD, MENTIONS_TOPIC, IN_SHASTRA edges) | `design/04_data_model_graph.md` | mirror of PG |
| `metadata-service` (port 8001) | `services/metadata_service/` | CRUD on shastras/authors/teekas/books/pravachans |
| `data-service` (port 8002) | `services/data_service/` | gathas, keywords, topics, kalashas, browse |
| `navigation-service` (port 8003) | `services/navigation_service/` | graph nav + alias writes |
| `query-service` (port 8004), Phase 1 `keyword_resolve_batch` | `design/query_engine/implementation_notes/initial_implementation_notes.md` | NFC normalize → exact → alias → suffix-strip → fuzzy |
| `query-service` Phase 2 `topics_match` + `graphrag` | same | GraphRAG endpoint for chat |
| Ingestion: jainkosh (incremental + review queue + edge creation) | `design/08_ingestion_jainkosh.md` + `design/jainkosh/` | |
| Ingestion: nikkyjain shastras (partial) | `design/09_ingestion_nikkyjain.md` | gatha + word-meaning + anvayartha |
| Chat enrichment puller (cron) | `design/archived/11_chat_enrichment_loop.md` | topic_candidates table |
| Public UI v1 (existing routes) | `design/14_public_ui.md`, `ui/` directory | Hindi-first, EN switch |
| Admin UI v1 | `design/admin_ui.md` | review queues, ingestion triggers |

## 🔜 Gaps SAAR fills

### Reading layer

| Gap | Spec |
|---|---|
| Per-shastra organised layout (samaysaar vs puraan vs karm-grantha differ structurally) | `design/scope/02_shastra_layout_configs_spec.md` |
| Hover/click keyword expansion in reader | `design/scope/04_keyword_hover_expansion_spec.md` |
| Drush-taant image generation per gatha | `design/scope/05_drushtaant_image_gen_spec.md` |
| Audio reader (ElevenLabs) | `design/scope/06_audio_reader_elevenlabs_spec.md` |
| PDF export | `design/scope/07_pdf_export_spec.md` |
| JainKosh-highlighted text overlay | `design/scope/12_jainkosh_highlight_overlay_spec.md` |

### Translation / enrichment layer

| Gap | Spec |
|---|---|
| Vitrag-elibrary Hindi-English dictionary ingest | `design/scope/14_vitrag_dictionary_ingest_spec.md` |
| 3-step enrichment pipeline (topic extract, keyword extract, hierarchy) | `design/scope/08_translation_pipeline_extraction_spec.md`, `09_translation_pipeline_ai_flow_spec.md`, `11_topic_hierarchy_ai_spec.md` |
| Counters (mentions of topics/keywords across corpus) | `design/scope/10_topic_keyword_counters_spec.md` |
| Multilingual keyword/topic translations (Kn/Gu/Sa/Pr/Ta) | `design/scope/15_multilingual_keyword_storage_spec.md`, `16_kn_gu_ocr_pipeline_spec.md` |
| Categorisation of keywords/gathas by research domain (Maths/Sciences/Philosophy/...) | `design/scope/13_categorisation_pipeline_spec.md` |
| Sanskrit / Prakrit translation models | `design/scope/26_sanskrit_prakrit_model_spec.md` |

### Retrieval / RAG layer

| Gap | Spec |
|---|---|
| Cataloguesearch vector search enhancements + graph observability | `design/scope/17_advanced_rag_enhancements_spec.md` |
| YouTube pravachan A/V RAG | `design/scope/18_av_rag_pipeline_spec.md` |
| Jinswara Q/A as graph entities (verified authors) | `design/scope/19_jinswara_qna_ingest_spec.md` |
| Flowchart / table / diagram scanner for shastra OCRs | `design/scope/20_flowchart_table_graph_scanner_spec.md` |

### Finetuning / serving layer

| Gap | Spec |
|---|---|
| Dataset export from graph + Mongo for training | `design/scope/21_finetune_dataset_export_spec.md` |
| Training infra (LoRA / full FT) | `design/scope/22_finetune_training_infra_spec.md` |
| Model serving registry + router | `design/scope/23_model_serving_registry_spec.md` |
| Eval harness | `design/scope/24_finetune_eval_harness_spec.md` |
| Graph-understanding finetune (relation + metadata + JainKosh keyword model) | `design/scope/25_graph_understanding_finetune_spec.md` |

### Platform layer

| Gap | Spec |
|---|---|
| User accounts + auth | `design/scope/01_user_accounts_spec.md` |
| ShastraExplorer UI | `design/scope/03_shastra_reader_ui_spec.md` |
| Siri Bhoovalay workspace | `design/scope/27_siri_bhoovalay_workspace_spec.md` |
| Research tools framework | `design/scope/28_research_tools_framework_spec.md` |
| Research models index | `design/scope/29_research_models_index_spec.md` |

## Touch-list for existing docs (additive patches)

- `00_overview.md` — append SAAR services, expand "Sources we ingest" with Jinswara + YouTube + Vitrag.
- `02_data_model_postgres.md` — add tables: `users`, `user_preferences`, `saved_views`, `saved_highlights`, `shastra_layouts`, `keyword_translations`, `topic_translations`, `topic_keyword_counters`, `flowcharts_tables`, `model_registry`, `finetune_jobs`, `finetune_datasets`, `youtube_pravachan_chunks`, `jinswara_qna`. Add enum `ingestion_source` values: `jinswara`, `youtube`, `vitrag_dict`, `vyakaran_v2`.
- `03_data_model_mongo.md` — add collections: `shastra_layouts`, `keyword_translations_extracts`, `drushtaant_images`, `audio_chapters`, `flowcharts_tables_blobs`, `youtube_transcripts`, `jinswara_qna_extracts`, `user_scratchpads`.
- `04_data_model_graph.md` — add node labels: `Translation`, `Flowchart`, `JinswaraQnA`, `PravachanChunk`, `ResearchCategory`. Add edges: `TRANSLATES_TO`, `HAS_FLOWCHART`, `ANSWERS`, `IN_PRAVACHAN`, `CATEGORISED_AS`, `DRUSHTAANT_OF`.
- `admin_ui.md` — append admin pages: model registry, finetune job runner, translation approvals, layout config editor, image/audio review.
- `deployment.md` — append: vLLM/Ollama serving, GPU node sizing, image-gen and ElevenLabs API key handling, S3-compatible store for blobs.
- `16_testing_and_fixtures.md` — append: counter computation tests, translation pipeline golden tests, model eval harness fixtures, layout config validator tests.

`14_public_ui.md` is left untouched (existing implementation). New page IA is captured in `01_pages_and_features.md` and per-page specs.
