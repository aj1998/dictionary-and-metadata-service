# Vectorless GraphRAG Query Engine — Overview & Scope

This folder specifies the kb-service (Jain KB) side of the GraphRAG enhancement
for `cataloguesearch-chat`. The chat-side spec lives in
`cataloguesearch-chat/service/docs/jain_kb_service/`. Each repo can implement
its phases independently; the contracts in this folder are the seam.

The Phase docs (`01_*` … `06_*`) are sized so a single agent can complete each
phase in one context window without delegating.

---

## Motivation

`cataloguesearch-chat` currently runs a vector/BM25 RAG (Step1 → external_search
→ Step2). It misses Jain-specific terminology, has no notion of canonical
topics, cannot guide its searches with structural context (shastra / gatha /
page), and cannot answer direct structural queries (e.g. *"समयसार की 6th गाथा
और उसका भावार्थ"*). This GraphRAG path complements (does **not** replace) the
vector RAG.

Two principles:

1. **Vectorless v1.** Reuse the dictionary, suffix-strip + alias resolution, and
   `pg_trgm` fuzzy that already power `query-service` per `12_query_engine.md`.
   No embeddings in this phase.
2. **Chat owns orchestration.** kb-service is a stateless library of HTTP
   endpoints. The chat service decides which to call and how to merge results.

---

## Endpoint inventory (reuse + new)

| Capability | Status | Endpoint |
|---|---|---|
| Keyword resolve (alias / suffix / fuzzy) for one token | Reuse (navigation-service) | `GET /v1/keywords/{token}/resolve` |
| Batched jain-keyword resolve + nearest-neighbour suggestions | **NEW** | `POST /v1/query/keyword_resolve_batch` (query-service) — Phase 1 |
| Keyword definitions (Hindi text only, by natural_key) | Reuse (data-service) | `GET /v1/keywords/{ident}` (extract Hindi blocks) |
| Closest-topic match by string (pg_trgm over `natural_key`, parent-aware) | **NEW** | `POST /v1/query/topics_match` (query-service) — Phase 2 |
| Closest-topic match via GraphRAG (normalize → resolve → traverse → rank → hydrate) | **NEW** | `POST /v1/query/graphrag` (query-service) — Phase 2 |
| Topic extract hydration (Hindi blocks + references) | Reuse + extend | `GET /v1/topics/{ident}` — Phase 5 helper |
| Metadata fuzzy match for shastras / authors | **NEW** (extend) | `GET /v1/shastras?q=&fuzzy=true`, `GET /v1/authors?q=&fuzzy=true` — Phase 3 |
| Gatha direct retrieval (`shastra` + number → Prakrit/Sanskrit/Hindi/bhavarth) | Reuse (data-service) | `GET /v1/gathas?shastra=&number=` already present; verify response shape — Phase 4 |
| Topics in a shastra | **NEW** | `POST /v1/query/topics_in_shastra` (query-service) — Phase 4 |
| Shastras (and gathas) mentioning a topic | **NEW** | `POST /v1/query/shastras_for_topic` (query-service) — Phase 4 |

All NEW endpoints live in `query-service` (port 8004) unless noted. Each is
designed to be pure-function on (Postgres + Mongo + Neo4j); no session state.

---

## Phase docs

1. `01_keyword_resolve_api.md` — batched resolve + nearest-neighbours
2. `02_topic_match_api.md` — `topics_match` (trigram, parent-aware) + `graphrag` reuse-of-pipeline
3. `03_metadata_fuzzy_match.md` — pg_trgm on shastras / authors / teekas
4. `04_subworkflow_endpoints.md` — gatha direct, topics-in-shastra, shastras-for-topic
5. `05_definitions_and_extracts_hydration.md` — shared Hindi-only projection helpers
6. `06_testing_and_rollout.md` — golden fixtures, integration tests, env, rollout order

---

## Cross-cutting conventions

- **Language**: All text fields the chat consumes are Hindi (Devanagari). Mongo
  blocks tagged `lang != "hi"` are filtered out before response.
- **Caps**: All endpoints accept `limit` (default values per endpoint;
  documented per phase). Chat overrides via env.
- **Natural keys**: kb-service responses always include `natural_key` so chat
  can re-query without round-tripping through opaque IDs.
- **References shape** (used by guided filters on chat side):

  ```json
  {
    "shastra_natural_key": "samaysaar",
    "gatha_number": 6,
    "teeka_natural_key": "amritchandra_atmakhyati",
    "page_number": 42
  }
  ```

  Any field may be null; chat treats each non-null field as a filter axis.
- **Errors**: 4xx for client errors, 5xx for backend failures; never leak DB
  internals. All endpoints log `tool_trace_id` for correlation with chat.

---
