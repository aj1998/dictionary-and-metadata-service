# 07 — Query Service API (GraphRAG)

This is the contract consumed by `cataloguesearch-chat` to enrich its vector hits with structured topic context. It is **the most performance-sensitive surface** — chat can call up to ~10 req/sec.

## Service identity

- **Module path**: `services/query_service/`
- **Default port**: `8003`
- **Base path**: `/v1`
- **Auth**: simple API-key (`x-api-key` header) shared with `cataloguesearch-chat`. Public UI may also call read-only endpoints unauthenticated.
- **Performance target**: p95 ≤ 250ms for `/v1/graphrag/topics` at 10 req/sec.

## The core endpoint

### `POST /v1/graphrag/topics`

Take a list of keyword tokens (already extracted by an LLM in `cataloguesearch-chat`), traverse the graph, return ranked topics + minimal context.

**Request:**
```json
{
  "query_id": "optional-uuid-from-caller",
  "tokens": ["पर्याय", "गुण", "भेद"],
  "top_k": 10,
  "max_hops": 2,
  "include_extracts": true,
  "include_chunk_ids": true,
  "edge_types": ["IS_A", "PART_OF", "RELATED_TO", "HAS_TOPIC", "MENTIONS_KEYWORD"],
  "caller": "cataloguesearch-chat"
}
```

| Field | Required | Default | Meaning |
|---|---|---|---|
| `query_id` | no | server-gen | for log correlation |
| `tokens` | yes | — | NFC-normalized Devanagari keyword tokens; service applies suffix-strip + alias resolution |
| `top_k` | no | 10 (max 50) | number of topics to return |
| `max_hops` | no | 2 (max 4) | graph traversal depth from seed keywords |
| `include_extracts` | no | true | embed `topic_extracts` Mongo content |
| `include_chunk_ids` | no | true | include `cataloguesearch_chunk_id` mentions |
| `edge_types` | no | all | restrict traversal to listed edge types |
| `caller` | no | "unknown" | logged for analytics |

**Response (200):**
```json
{
  "query_id": "uuid",
  "tokens_resolved": [
    {"input": "पर्याय",  "matched_keyword_natural_key": "पर्याय",        "match_kind": "exact"},
    {"input": "गुण",     "matched_keyword_natural_key": "गुण",          "match_kind": "exact"},
    {"input": "भेद",     "matched_keyword_natural_key": null,           "match_kind": "none"}
  ],
  "topics": [
    {
      "rank": 1,
      "score": 4.5,
      "topic": {
        "id": "uuid",
        "natural_key": "jainkosh:द्रव्य:द्रव्य-गुण-पर्याय-भेद",
        "display_text_hi": "द्रव्य गुण पर्याय भेद",
        "source": "jainkosh"
      },
      "rationale": {
        "matched_seed_keywords": ["पर्याय", "गुण"],
        "edge_path_summary": [
          {"from": "पर्याय", "edges": ["MENTIONS_KEYWORD"], "to": "जैनकोष:द्रव्य:द्रव्य-गुण-पर्याय-भेद"},
          {"from": "गुण",   "edges": ["MENTIONS_KEYWORD"], "to": "जैनकोष:द्रव्य:द्रव्य-गुण-पर्याय-भेद"}
        ],
        "overlap_count": 2,
        "weight_sum": 2.5
      },
      "extracts": [
        {
          "natural_key": "jainkosh:द्रव्य:द्रव्य-गुण-पर्याय-भेद",
          "heading_hi": "द्रव्य गुण पर्याय भेद",
          "blocks": [
            {"kind": "hindi", "text": "द्रव्य के गुण और पर्याय में भेद ..."}
          ]
        }
      ],
      "mentions": [
        {"kind": "gatha", "gatha_natural_key": "pravachansaar:093"},
        {"kind": "cataloguesearch_chunk", "cataloguesearch_chunk_id": "cs-chunk-44231"}
      ]
    }
  ],
  "stats": {
    "tokens_total": 3,
    "tokens_matched": 2,
    "topics_returned": 1,
    "latency_ms": 78,
    "graph_hops": 1
  }
}
```

**Empty case (zero seed keywords matched):**

Per clarification FQ2, return `200 OK`:
```json
{
  "query_id": "uuid",
  "tokens_resolved": [{"input": "...", "matched_keyword_natural_key": null, "match_kind": "none"}],
  "topics": [],
  "stats": {"tokens_total": 1, "tokens_matched": 0, "topics_returned": 0, "latency_ms": 12, "graph_hops": 0}
}
```

The caller (cataloguesearch-chat) decides what to do with an empty list.

### `POST /v1/graphrag/explain`

Returns the same response as `/topics` but with full Cypher path traces for each ranked topic. Used by admin UI debugger and offline quality eval. Not for production traffic.

### `GET /v1/graphrag/health`

```json
{"postgres": "ok", "mongo": "ok", "neo4j": "ok", "graph_node_count": 12345}
```

## Query path (high-level — full detail in `12_query_engine.md`)

```
tokens
  ↓ NFC normalize
  ↓ light Hindi-suffix strip (configurable)
  ↓ alias lookup (Postgres keyword_aliases + Neo4j Alias→Keyword)
  ↓ seed keyword set
  ↓ Cypher traversal (depth ≤ max_hops, restricted edge types)
  ↓ candidate topics
  ↓ weighted-overlap rank (Python, swappable)
  ↓ top_k
  ↓ hydrate (Mongo extracts + Postgres mentions)
  ↓ response
```

## Module layout

```
services/query_service/
├── main.py
├── config.py
├── routers/
│   ├── graphrag.py          # /topics, /explain
│   └── health.py
├── pipeline/
│   ├── normalize.py         # NFC + suffix strip
│   ├── resolve.py           # token -> keyword_natural_key (alias-aware)
│   ├── traverse.py          # Cypher invocation
│   ├── ranking.py           # weighted-overlap scoring (v1)
│   └── hydrate.py           # batch fetch extracts + mentions
├── schemas/
│   ├── request.py
│   └── response.py
└── tests/
    ├── test_zero_match.py
    ├── test_partial_match.py
    ├── test_full_match.py
    └── fixtures/
```

## Performance & caching

- LRU cache on `(sorted(tokens), top_k, max_hops)` → response, with TTL 60s and capacity 10k. Bypass via `?nocache=1` on the endpoint.
- A request body of identical tokens (in any order) hits the cache.
- Token resolution (`token → keyword_natural_key`) is cached separately per token, capacity 50k, TTL 600s.
- Neo4j connection pool size = 32 (tune per load).
- Each request runs **one** Cypher round-trip (UNWIND seed list), **one** batched Mongo `find({_id: {$in: ...}})`, **one** batched Postgres `IN` query for mentions. No N+1.

## Logging

Every successful call writes one row to `query_logs` (Postgres). Async fire-and-forget so it doesn't add latency.

## Rate limiting

Token bucket per `caller`:
- `cataloguesearch-chat`: 20 rps burst, 10 rps sustained.
- Public UI: 5 rps per IP.

Implemented via `slowapi` or custom Redis-backed limiter.

## Definition of Done

- [ ] `POST /v1/graphrag/topics` returns valid responses for: zero-match, partial-match, full-match, very-broad (1 token).
- [ ] p95 ≤ 250ms at 10 rps demonstrated by a `pytest`+`locust` test on a realistic seed graph (≥ 500 keyword nodes, ≥ 200 topic nodes).
- [ ] All paths log to `query_logs`.
- [ ] LRU cache hit observed in test (second identical request is faster).
- [ ] OpenAPI examples include the four scenarios above.
- [ ] Service starts with `uvicorn services.query_service.main:app --port 8003`.
