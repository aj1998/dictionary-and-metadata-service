# Phase 6 — Testing, Env, and Rollout

## Rollout order

1. Phase 5 (hydration helpers) — zero behavioural change; just lets Phases
   1/2/4 land cleanly.
2. Phase 1 (keyword resolve batch).
3. Phase 2 (topics_match + graphrag).
4. Phase 3 (metadata fuzzy) — independent, can land in parallel with 1/2.
5. Phase 4 (sub-workflow endpoints).

Each phase ships behind its own URL so chat can adopt incrementally — no
feature flag needed in kb-service.

## Env additions (query-service)

```
QUERY_KEYWORD_RESOLVE_MAX_TOKENS=32
QUERY_KEYWORD_FUZZY_MIN_SIM=0.35
QUERY_KEYWORD_FUZZY_TOP_K=5

QUERY_TOPICS_MATCH_DEFAULT_LIMIT=5
QUERY_TOPICS_MATCH_MIN_SIM=0.30

QUERY_GRAPHRAG_DEFAULT_LIMIT=5
QUERY_GRAPHRAG_DEFAULT_MAX_HOPS=2

QUERY_TOPICS_IN_SHASTRA_LIMIT=25
QUERY_SHASTRAS_FOR_TOPIC_LIMIT=10
```

## Integration test plan

Single `tests/query_engine/test_e2e.py` against a testcontainer trio
(Postgres + Mongo + Neo4j) seeded from
`tests/fixtures/golden_query_responses.json` (already referenced by
`12_query_engine.md`). Add fixtures for:

- A jain keyword with alias + suffix variants.
- A topic where parent-aware trigram beats leaf-only.
- A shastra+gatha with multiple `MENTIONS_TOPIC` edges.
- A topic mentioned across ≥2 shastras.

Assertions per phase covered in each phase doc; this file owns the
**round-trip** assertion: `len(postgres_roundtrips) + len(mongo_roundtrips) +
len(neo4j_roundtrips) ≤ documented_budget` per endpoint.

## Manual testing snippets

Add under `docs/manual_testing/api/query/`:

- `keyword_resolve_batch.md`
- `topics_match.md`
- `graphrag.md`
- `topics_in_shastra.md`
- `shastras_for_topic.md`

Each file contains one `curl` block, expected response shape, and a
diagnostic Cypher / SQL query for verifying the row counts.
