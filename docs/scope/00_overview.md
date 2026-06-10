# Jinvani SAAR — Scope Overview

**SAAR = Search, Analysis and AI Research.**

A Jain-text discovery platform built on top of the existing dictionary-and-metadata-service (graph + APIs), `cataloguesearch` (vector/BM25), `cataloguesearch-chat` (LLM chat), and `nikkyjain.github.io` (shastra HTML corpus). SAAR is the *public surface* + the *enrichment layer* that turns these into a research workspace.

These docs are intentionally short. Detailed, implementable specs live in [`../design/scope/`](../design/scope/). Existing foundational docs (02–16) are patched only where new entities require it; the new architecture is *additive*.

## Eight named features

| # | Feature | Home page | Scope doc |
|---|---|---|---|
| 1 | Graph UI (with Shastra Reader side panel) | `#Graph` | [01_pages_and_features.md](./01_pages_and_features.md) |
| 2 | Advanced RAGs / AI page | `#AI` | [06_advanced_rag_and_finetuning.md](./06_advanced_rag_and_finetuning.md) |
| 3 | Shastra Reader | `#ShastraExplorer` | [03_shastra_reader.md](./archived/03_shastra_reader.md) |
| 4 | Translations / Multilingual | All pages | [05_multilingual_strategy.md](./05_multilingual_strategy.md) |
| 5 | Finetuned Models | `#AI` | [06_advanced_rag_and_finetuning.md](./06_advanced_rag_and_finetuning.md) |
| 6 | Siri Bhoovalay decoder | `#ResearchTools` | [07_siri_bhoovalay_and_research_models.md](./07_siri_bhoovalay_and_research_models.md) |
| 7 | Topic-wise Research Tools | `#ResearchTools` | [07_siri_bhoovalay_and_research_models.md](./07_siri_bhoovalay_and_research_models.md) |
| 8 | User login + customization | All pages | [08_user_accounts.md](./08_user_accounts.md) |

## Four enrichment workstreams (foundation)

| Workstream | Status | Scope doc |
|---|---|---|
| GraphRAG (keyword resolve, topic match, ranker) | ✅ phases 1–2 implemented; see `design/query_engine/implementation_notes/initial_implementation_notes.md` | [02_foundation_status.md](./02_foundation_status.md) |
| Hin↔Eng translation + topic/keyword extraction pipeline | 🔜 | [04_translation_enrichment_pipeline.md](./04_translation_enrichment_pipeline.md) |
| Kannada/Gujarati keyword + topic translation | 🔜 | [05_multilingual_strategy.md](./05_multilingual_strategy.md) |
| Finetuning + serving (graph-aware + main Jainism model + research-domain models) | 🔜 | [06_advanced_rag_and_finetuning.md](./06_advanced_rag_and_finetuning.md) |

## Design tenets

1. **Postgres is the source of truth.** Mongo + Neo4j mirror; new entities (users, layout configs, counters, multilingual translations, model registry) follow the same `natural_key` + UUID pattern.
2. **Hindi default, English co-equal.** Other languages (Kn/Gu/Sa/Pr/Ta) are *optional overlays* at keyword/topic granularity only — not full-text translations.
3. **Admin reviews everything** before public visibility — including AI-generated topics, keyword translations, and finetune candidates.
4. **AI pipelines are pluggable.** A single `llm_call` abstraction picks the model per task (Anthropic, OpenAI, hosted Ollama, or a finetuned in-house model from our registry).
5. **Counters as a USP.** Every extracted topic/keyword carries occurrence counts across the corpus — exposed in reader UI, used by ranker, used as training-set weighting.
6. **Research workspace > polished consumer app.** SAAR is a tool for serious Jain study; UX favors depth, citations, and provenance over discovery polish.

## What's out of scope (still)

- Mobile apps (web-responsive is enough).
- Owning OCR of the cataloguesearch corpus.
- Running a payment system.
- Real-time collaborative reading (saved highlights + private notes are in scope; co-editing is not).

## Reading order

1. [01_pages_and_features.md](./01_pages_and_features.md) — the eight features as a user sees them.
2. [02_foundation_status.md](./02_foundation_status.md) — what's already built; gaps the scope work fills.
3. [03_shastra_reader.md](./archived/03_shastra_reader.md) — the reading core.
4. [04_translation_enrichment_pipeline.md](./04_translation_enrichment_pipeline.md) — the 3-step pipeline (the engine behind everything multilingual).
5. [05_multilingual_strategy.md](./05_multilingual_strategy.md) — Kn/Gu/Sa/Pr scope.
6. [06_advanced_rag_and_finetuning.md](./06_advanced_rag_and_finetuning.md) — AI page, training infra, A/V RAG, Jinswara.
7. [07_siri_bhoovalay_and_research_models.md](./07_siri_bhoovalay_and_research_models.md) — research workstreams.
8. [08_user_accounts.md](./08_user_accounts.md) — login + preferences.
9. [09_open_questions.md](./09_open_questions.md) — clarifications still needed from product owner.
10. [10_suggested_improvements.md](./10_suggested_improvements.md) — proposed additions to the vision.
11. [11_suggested_research_tools.md](./11_suggested_research_tools.md) — tools that fall out of the data we'll have.
