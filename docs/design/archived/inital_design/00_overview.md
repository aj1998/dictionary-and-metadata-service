# 00 — Dictionary & Metadata Service: Overview

## Mission

Build a structured, knowledge-graph-backed retrieval service for Jain texts that complements the existing vector/BM25 retriever (`cataloguesearch`) and the LLM chat layer (`cataloguesearch-chat`). It owns:

- **Master Metadata** — authors, shastras, teekas, publications, books, pravachans, anuyogas (in Postgres).
- **Dictionary content** — gathas (Prakrit/Sanskrit/Hindi), kalashas, word-to-meaning maps, keyword definitions, topic extracts (in MongoDB).
- **Topic Knowledge Graph** — keyword↔topic↔topic relations, alias edges, structural containment edges (in Neo4j).

It exposes:

1. A **public read API** for the UI (browse shastras, look up keywords, read gathas, explore topics).
2. A **graph navigation API** for graph-based UI navigation and as the resolution layer for the query service.
3. A **GraphRAG query API** consumed by `cataloguesearch-chat` to enrich vector hits with structured topic context.
4. An **admin API + UI** for triggering ingestion, reviewing parsed extracts, curating synonyms, and approving AI-generated topic candidates.

## SAAR additions

The Jinvani SAAR vision extends the original 4-service platform. The scope and per-feature design specs live in [`scope/`](../../scope) and [`design/scope/`](../../scope). New services and sources added by SAAR are summarised below; see [`scope/02_foundation_status.md`](../../../scope/02_foundation_status.md) for the foundation gap analysis.

### Additional services

| Service | Port | Purpose |
|---|---|---|
| `auth-service` | 8005 | JWT auth (magic-link + Google OAuth), user preferences, saved views/highlights (spec 01) |
| `pdf-export-service` | 8006 | WeasyPrint-based PDF export of shastra chapters (spec 07) |
| `rag-enhancer-service` | 8007 | Graph-aware re-ranking on top of `query-service /graphrag` (spec 17), A/V RAG (spec 18) |
| `model-serving-service` | 8008 | vLLM-served LoRA finetunes + registry router (specs 22, 23) |
| `bhoovalay-service` | 8009 | Siri Bhoovalay chakra workspace + decoding helpers (spec 27) |

### Additional sources

| Source | Format | Output |
|---|---|---|
| `vitrag-elibrary` (Hi↔En dictionary) | Live HTML | Constrained translation vocabulary (spec 14) |
| Jinswara Q/A archive | HTML | Q/A pairs linked to graph topics (spec 19) |
| YouTube pravachan transcripts | YouTube API + STT fallback | Time-coded chunks indexed for A/V RAG (spec 18) |
| Scanned Kn/Gu shastra PDFs | PDF | OCR + multilingual keyword aliases (spec 16) |

## Out of Scope

- Mobile apps
- Owning OCR of the cataloguesearch corpus (we only OCR `vyakaran_vishleshan` and the Kn/Gu sources from spec 16 here)
