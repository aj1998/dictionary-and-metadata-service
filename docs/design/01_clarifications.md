# 01 — Clarifications (verbatim Q&A)

This file captures decisions made during the design phase. When in doubt during implementation, this is the tiebreaker.

## A. Tech stack & infra

**Q1.** Language/framework for the 3 backend services.
**A.** "Whichever works best and scalable" given a future graph of ~2000–2500 shastras × ~1000 pages each.
**Decision:** Python 3.12 + FastAPI for backend (matches OCR/LLM/scraping ecosystem), Celery + Redis for jobs, Next.js 14 for UI.

**Q2.** SQL engine.
**A.** PostgreSQL.
**Decision:** PostgreSQL 16 with `pg_trgm` (fuzzy match) and ICU collation for Devanagari.

**Q3.** Graph DB (must be free).
**A.** "Whichever you think is best." Subsequent answer: "lets use neo4j".
**Decision:** Neo4j 5 Community Edition.

**Q4.** Mongo or Postgres-JSONB for text extracts.
**A.** "Postgres JSONB is fine if good for Devanagari KB. Future Gujarati texts will be translated to Hindi; KB stays in Hindi."
**Decision:** Use **MongoDB** for text extracts. Justification: long-form, schema-flexible Devanagari/Sanskrit/Prakrit text with frequent re-parsing benefits from a document store; Postgres JSONB is fine for Devanagari but we want clean separation between structured metadata and bulk text. Hindi will always be the canonical KB language; Gujarati/Tamil etc. enter via translation pre-ingestion.

**Q5.** Deployment.
**A.** "Docker Compose single host for now, but service design should be extensible. Vertical scaling. Max ~10 req/sec from cataloguesearch-chat."
**Decision:** Docker Compose, single VM, vertical scale. Services are independent processes so they can later be split across hosts.

**Q6.** Auth.
**A.** "Public read for UI, no auth and user accounts for now."
**Decision:** Public UI is unauthenticated. Admin UI is gated by HTTP basic auth + IP allowlist behind nginx for v1.

## B. Data model

**Q7.** "Anuyoga tables (4*2)" — what does 4*2 mean?
**A.** "4 separate tables each that link Shastra↔Anuyoga and Book↔Anuyoga."
**Decision:** One `anuyogas` lookup table seeded with the four anuyogas (Prathmānuyoga, Karaṇānuyoga, Charaṇānuyoga, Dravyānuyoga) plus two link tables: `shastra_anuyogas` and `book_anuyogas`. (Total: 1 lookup + 2 links = 3 tables; the "4 separate" was clarified as semantic count of relationship targets.)

**Q8.** What is "Swalakshya Teeka Name/Id"?
**A.** "This is name of the OCRed shastra in cataloguesearch — a mapping field, rename it."
**Decision:** Renamed to `cataloguesearch_shastra_id` (foreign reference, no FK constraint).

**Q9.** ID strategy.
**A.** "Keep UUIDs."
**Decision:** UUIDv4 primary keys everywhere. Every ingested row also has a `natural_key` UNIQUE column for idempotent re-scrape (see Q26 below).

**Q10.** Mongo collection layout.
**A.** "Different collections per type."
**Decision:** Per-type collections (see `03_data_model_mongo.md`).

**Q11.** Versioning of re-scraped content.
**A.** "Overwrite."
**Decision:** Overwrite by `natural_key`. Only the latest parsed version is kept. Raw HTML snapshots are versioned on disk by ingestion-run timestamp for forensic re-parse without re-scrape.

**Q12.** Multilingual extensibility (Tamil harigeets).
**A.** "[{lang, text}] arrays from day one."
**Decision:** Every translation/harigeet/chhand field is an array of `{lang: ISO-639-3, script: ISO-15924, text: str}`.

## C. Parsing & ingestion

**Q13.** Parser config location.
**A.** "YAML/JSON in the repo."
**Decision:** YAML files under `parser_configs/`, version-controlled.

**Q14.** Persist raw HTML?
**A.** "Persist downloaded HTML in local files."
**Decision:** Raw HTML goes to `data/raw/<source>/<run_ts>/<slug>.html`. Path is recorded in `ingestion_runs` table.

**Q15.** Scraping etiquette.
**A.** "Yes, rate limits, all parses verified manually initially. Goes slow."
**Decision:** Default 1 req/sec to jainkosh.org (configurable), all ingest runs land in admin review queue before promotion.

**Q16.** OCR scope.
**A.** "OCR is in scope but rules to be specified later. Focus first on jainkosh and nikkyjain."
**Decision:** OCR module is a pluggable interface (`workers/ingestion/vyakaran_ocr.py`); v1 implementation is a stub that documents the I/O contract. Real OCR work begins after jainkosh + nikkyjain are in production.

**Q17.** nikkyjain repo location.
**A.** "We already have a clone locally."
**Decision:** Path configured via env `NIKKYJAIN_LOCAL_PATH`. Parser reads from disk; no scraping.

## D. Topic & keyword semantics

**Q18.** Topic identification.
**A.** "Section headings for now. AI-generated topics in cataloguesearch-chat will be persisted in its own DB; we pull on a daily cron and route through admin review queue."
**Decision:** v1 = section headings only. v2 = nightly puller from chat DB → `topic_candidates` table → admin UI review → merge into graph.

**Q19.** Devanagari Unicode normalization.
**A.** "Yes."
**Decision:** All Devanagari text passes through Unicode NFC + a Devanagari-specific cleanup (strip ZWJ/ZWNJ where not semantic, normalize anusvāra-vs-conjunct nasal where unambiguous). See `12_query_engine.md` for the exact normalizer.

**Q20.** Edge types in the graph.
**A.** "is_a / part_of / related_to. Extensible."
**Decision:** Initial edge types: `IS_A`, `PART_OF`, `RELATED_TO`, plus `ALIAS_OF` (for synonym links) and `MENTIONS` (for keyword↔gatha and topic↔chunk). New types can be added without schema migration (Neo4j is schema-flexible); a registry table in Postgres tracks the canonical list.

**Q21.** Semantic embeddings or graph-only?
**A.** "Graph-only + synonym dictionary for v1. Embeddings deferred to v2."
**Decisions:**
- v1 query path: tokenize → NFC normalize → Hindi-suffix-strip → lookup `keyword_alias` → seed graph traversal → weighted-overlap rank.
- Aliases come from (a) JainKosh redirect/aliases mined during scrape, (b) admin-curated synonyms in admin UI.
- Zero-match queries return `200 OK` with empty `topics: []`; no fuzzy fallback in v1.
- Ranking = weighted-overlap (count of seed keywords reaching topic, weighted by edge strength). Function isolated in `query_service/ranking.py` so PageRank/embeddings can swap in for v2.

## E. Service boundaries & API

**Q22.** Three deployable services?
**A.** Yes.
**Decision:** `metadata-service`, `dictionary-service`, `query-service`.

**Q23.** Sync vs async ingestion.
**A.** "Manually triggered. Iterators stored. Queue (Celery/Redis) for the chat-candidate cron."
**Decision:** Ingestion = Celery tasks triggered from admin UI (or CLI). Iterator state (e.g., last scraped letter, last shastra) stored in `ingestion_runs` table.

**Q24.** Direction with cataloguesearch-chat.
**A.** "Both. Chat calls us via direct API for GraphRAG. We pull chat's candidate topics via cron — no push."
**Decision:** `query-service` exposes `POST /v1/graphrag/topics`. `workers/enrichment/chat_candidate_puller.py` runs on a cron, reads chat's exposed DB read-replica.

**Q25.** API style.
**A.** "Whatever works best."
**Decision:** REST + OpenAPI 3.1, FastAPI auto-generates the spec at `/openapi.json`.

## F. UI

**Q26.** UI scope.
**A.** "Same web app with separate sections (shastra/gatha browse, keyword dictionary, topic explorer, plus user-query-topic-retrieval section). Hindi-first."
**Decision:** Single Next.js app with four top-level routes: `/shastras`, `/dictionary`, `/topics`, `/search`. Admin is a sub-route `/admin/*` behind basic auth.

**Q27.** UI stack.
**A.** "Choose best."
**Decision:** Next.js 14 (App Router) + Tailwind + `next-intl` (Hindi default, EN added later). Server-rendered for SEO/share-ability of dictionary and topic pages.

**Q28.** Admin UI.
**A.** "Yes, separate."
**Decision:** Same Next.js app, gated route prefix `/admin/*`.

## G. Out-of-scope

**Q29.** Training, chat orchestration, mobile apps, cataloguesearch OCR.
**A.** Confirmed out of scope.

## Follow-up clarifications (from second round)

**FQ1.** Synonym dictionary in v1, embeddings deferred to v2 — confirmed.
**FQ2.** Zero-match queries return empty array — confirmed.
**FQ3.** Weighted-overlap ranking — confirmed.
**FQ4.** Chat candidates pulled from chat's DB on cron, admin-review queue before merge — confirmed.
**FQ5.** Cataloguesearch chunk references stored as foreign IDs (no duplication of chunk text) — confirmed.
**FQ6.** Stack: Python+FastAPI, Celery+Redis, Neo4j, REST+OpenAPI, Next.js — confirmed.
**FQ7.** UUIDs + `natural_key` unique column on every ingested entity — confirmed. Naming convention:
- Keyword: `{NFC normalized keyword text}` (e.g. `आत्मा`)
- Shastra: human slug (e.g. `pravachansaar`)
- Gatha: `{shastra_slug}:{zero-padded gatha number or range}` (e.g. `pravachansaar:039`, `pravachansaar:004-005`)
- Teeka: `{shastra_slug}:{teeka_slug}` (e.g. `pravachansaar:amritchandra`)
- Topic: `{source}:{parent_keyword|context}:{normalized_heading}` (e.g. `jainkosh:आत्मा:बहिरात्मादि-3-भेद`)
- Author: human slug (e.g. `kundkundacharya`)
**FQ8.** Neo4j Community — confirmed.

## Constraints captured for implementers

- **Hindi morphology is NOT our problem at the API boundary**: queries arrive pre-tokenized as keyword phrases (e.g. `पर्याय गुण भेद`) from `cataloguesearch-chat`, which already extracted them via LLM. We do light NFC + suffix-strip but do not run a full lemmatizer.
- **Synonyms are the main lever for v1 recall**. Invest in seeding the synonym dictionary from JainKosh redirects + manual curation.
- **All schema fields that may go multilingual are arrays from day one** — even when only Hindi is populated.
- **Overwrite, don't version** — re-scrapes replace previous parsed rows, identified by `natural_key`. Raw HTML snapshots are kept on disk for re-parse if a parser bug is found.
