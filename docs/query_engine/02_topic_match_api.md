# Phase 2 — Topic Match APIs

Two endpoints. Chat calls **both** in parallel and merges. Rationale (per
user): trigram catches keyword phrases that appear in a parent topic but not
the current node; GraphRAG catches sub-topics / related topics / cross-shastra
mentions that pure string match misses.

---

## 2A. `POST /v1/query/topics_match`

String-similarity match over topic natural_keys, **parent-aware**.

### Why parent-aware

Topic natural_keys today encode hierarchy (e.g.
`द्रव्य/स्वतंत्रता/लक्षण`). A user query like *"द्रव्य स्वतंत्रता"* should
match `द्रव्य/स्वतंत्रता/लक्षण` even though the leaf heading is just
*"लक्षण"*. We similarity-score against the **full natural_key path** (slashes
replaced with spaces for trigram), not just `display_text_hi`.

### Request

```json
{
  "keywords": ["द्रव्य", "स्वतंत्रता"],
  "phrase": "द्रव्य स्वतंत्रता",
  "limit": 5,
  "min_similarity": 0.30,
  "include_extracts": true,
  "include_references": true,
  "leaf_only": false
}
```

| Field | Required | Default | Notes |
|---|---|---|---|
| `keywords` | one of `keywords` or `phrase` | — | tokens to AND-soft-match |
| `phrase` | one of `keywords` or `phrase` | — | free-form string, used directly for similarity |
| `limit` | no | 5 | top-N, closest first |
| `min_similarity` | no | 0.30 | trigram cutoff |
| `include_extracts` | no | true | hydrate Mongo `topic_extracts` (Hindi blocks only) |
| `include_references` | no | true | include `{shastra, gatha, teeka, page}` refs from extract blocks |
| `leaf_only` | no | false | when true, filter `is_leaf = true` |

### Scoring

```
search_str  = phrase OR " ".join(keywords)
candidate   = REPLACE(topic.natural_key, '/', ' ')
sim         = similarity(candidate, search_str)
score       = sim * (1.0 if topic.is_leaf else 0.6)
```

Same leaf penalty pattern as `12_query_engine.md` Stage 5 (0.5 → 0.6 here
because we have *less* context to reject containers).

### Response

```json
{
  "matches": [
    {
      "topic_natural_key": "द्रव्य/स्वतंत्रता/लक्षण",
      "topic_pg_id": "uuid-…",
      "display_text_hi": "लक्षण",
      "ancestors_hi": ["द्रव्य", "स्वतंत्रता"],
      "is_leaf": true,
      "source": "jainkosh",
      "similarity": 0.71,
      "score": 0.71,
      "extracts_hi": [
        { "block_index": 2, "text_hi": "…" }
      ],
      "references": [
        { "shastra_natural_key": "samaysaar", "gatha_number": 6, "teeka_natural_key": null, "page_number": 42 }
      ]
    }
  ],
  "tool_trace_id": "uuid-…"
}
```

### Indexes

```
CREATE INDEX topics_natural_key_trgm_idx ON topics
  USING gin (REPLACE(natural_key, '/', ' ') gin_trgm_ops);
```

---

## 2B. `POST /v1/query/graphrag`

This is the full pipeline from `12_query_engine.md` exposed as an HTTP call.
Chat uses it to get **graph-enriched** topic context (sub-topics, related
keywords, cross-shastra mentions).

### Request

```json
{
  "tokens": ["द्रव्य", "स्वतंत्रता"],
  "max_hops": 2,
  "limit": 5,
  "edge_types": null,
  "include_extracts": true,
  "include_neighbors": true,
  "include_references": true,
  "fuzzy": false
}
```

| Field | Default | Notes |
|---|---|---|
| `tokens` | required | passed through Stages 1–3 |
| `max_hops` | 2 | traversal depth |
| `limit` | 5 | top-N ranked topics |
| `edge_types` | null | optional whitelist; structural edges excluded by default |
| `include_neighbors` | true | adds 1-hop `RELATED_TO` / `MENTIONS_TOPIC` neighbors per topic |
| `fuzzy` | false | per Stage 3, opt-in trigram during resolve |

### Response

```json
{
  "ranked_topics": [
    {
      "topic_natural_key": "द्रव्य/स्वतंत्रता",
      "topic_pg_id": "uuid-…",
      "display_text_hi": "स्वतंत्रता",
      "ancestors_hi": ["द्रव्य"],
      "score": 23.5,
      "overlap_count": 2,
      "matched_seed_keywords": ["द्रव्य", "स्वतंत्रता"],
      "is_leaf": true,
      "source": "jainkosh",
      "extracts_hi": [ … ],
      "references": [ … ],
      "neighbors": {
        "related_topics": [
          { "topic_natural_key": "द्रव्य/लक्षण", "display_text_hi": "लक्षण" }
        ],
        "mentioned_in_gathas": [
          { "shastra_natural_key": "samaysaar", "gatha_number": 6 }
        ],
        "related_keywords": [
          { "keyword_natural_key": "स्वभाव" }
        ]
      }
    }
  ],
  "unresolved_tokens": ["…"],
  "tool_trace_id": "uuid-…"
}
```

The shape of `ranked_topics[*]` is a superset of `topics_match` matches so
chat can normalize-merge the two lists by `topic_natural_key` (graphrag wins
on tie, additive on extracts/neighbors).

### Implementation

- Wraps the existing six-stage pipeline; **do not duplicate logic**.
- `include_neighbors=true` adds a second Cypher round-trip after Stage 6:

  ```cypher
  UNWIND $topic_nks AS nk
  MATCH (t:Topic {natural_key: nk})-[r:RELATED_TO|MENTIONS_TOPIC|HAS_TOPIC]-(n)
  WHERE NOT type(r) IN ['IN_SHASTRA','IN_TEEKA','IN_PUBLICATION']
  RETURN nk, type(r) AS rel, n LIMIT 200
  ```

  Bucket the rows into `related_topics` / `related_keywords` /
  `mentioned_in_gathas` in Python.

---

## Tests (Phase 2)

- `test_topics_match_trigram.py` — `द्रव्य स्वतंत्रता` matches
  `द्रव्य/स्वतंत्रता/लक्षण` via parent-aware similarity; `leaf_only` filter
  works.
- `test_topics_match_extracts_hi_only.py` — non-Hindi blocks excluded.
- `test_graphrag_endpoint_e2e.py` — seeded testcontainer graph; returns
  ranked topics with neighbors.
- `test_graphrag_endpoint_unresolved.py` — unknown tokens land in
  `unresolved_tokens` and don't crash traversal.
- `test_merge_equivalence.py` — fixture proving overlap of `topics_match`
  and `graphrag` is non-empty for a real query; merge-by-natural_key works.

## DoD

- [ ] Both endpoints live; OpenAPI generated.
- [ ] Trigram index on `topics(natural_key)` (computed expression).
- [ ] GraphRAG endpoint adds only one Cypher hop beyond existing Stage 6.
- [ ] Manual test snippet under `docs/manual_testing/api/query/`.
