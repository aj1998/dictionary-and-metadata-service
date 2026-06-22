# Phase 2 — Topic Match APIs

> **`topics_match` gains a `content_only` flag** in
> [`08_content_gated_topic_neighbors.md`](08_content_gated_topic_neighbors.md)
> (Part A) — default true, drops topics with no displayable extracts.

Two endpoints. Chat calls **both** in parallel and merges. Rationale (per
user): trigram catches keyword phrases that appear in a parent topic but not
the current node; GraphRAG catches sub-topics / related topics / cross-shastra
mentions that pure string match misses.

---

## 2A. `POST /v1/query/topics_match`

String-similarity match over topic natural_keys, **parent-aware**.

> **Implementation note (2026-06):** `display_text_hi` in each match item is
> extracted from the `topics.display_text` JSONB by
> `get_display_text_hi()` in `services/query_service/pipeline/topics_match.py`.
> The lang code stored on extracts is `"hin"` (Bharati/ISO 639-3), not `"hi"`;
> the helper accepts both (`item.get("lang") in ("hin", "hi")`). Earlier
> versions only matched `"hi"` and returned an empty string, leaving the topic
> name blank on the public UI topics search cards.


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
  "leaf_only": false,
  "min_token_coverage": 0.5
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
| `min_token_coverage` | no | 0.5 | min fraction of meaningful query tokens a topic must contain (see token-coverage guard); 1.0 requires every word, 0.0 disables |

### Scoring

```
search_str   = phrase OR " ".join(keywords)
candidate    = REPLACE(topic.natural_key, '/', ' ')
raw_sim      = GREATEST(similarity(candidate, search_str), leaf_substring_hit)
tokens       = normalize(meaningful query tokens)         # stopwords/short dropped
coverage     = |{ t in tokens : some path-segment starts with t }| / |tokens|
similarity   = raw_sim * coverage                         # ← coverage-weighted; the UI ranks/shows this
score        = similarity * (1.0 if topic.is_leaf else 0.6)
```

> **Why coverage is folded into `similarity` (not only `score`):** the topics
> search UI sorts by and renders `similarity` directly as the "% मिलान" badge
> (`ui/.../topics/page.tsx`). Folding coverage there (backend-only, no UI change)
> is what lifts full-coverage child/sub-topics above topics that share only an
> incidental token. `score` additionally applies the leaf/container weighting and
> is what the chat merge with graphrag ranks on. The unweighted trigram value is
> retained internally as `raw_similarity`.

Same leaf penalty pattern as `12_query_engine.md` Stage 5 (0.5 → 0.6 here
because we have *less* context to reject containers).

#### Token-coverage guard *(2026-06)*

Pure trigram/substring similarity over the full `natural_key` path let topics
that merely shared an incidental token outrank topics containing the
distinctive one — e.g. for `सत् द्रव्य भेद`, `…:स्व-व-पर-द्रव्य-के-लक्षण`
(shares `द्रव्य`+`भेद` via its ancestor path but has **no** `सत्`) scored above
`…:सत्-व-द्रव्य-में-…-भेदाभेद`.

Fix: count how many of the query's *meaningful* tokens appear in each candidate.
`coverage` both **multiplies the score** (so higher-coverage topics always rank
above lower-coverage ones) and **gates** the result via `min_token_coverage`
(request field). Candidates below the threshold are dropped.

- **Word-boundary matching:** the `natural_key` is split into its individual
  Hindi words (segments — on `: / -`, dandas, whitespace) and a token counts
  only when it is a **prefix of some segment**. This keeps compound matches
  (`भेद` → `भेदाभेद`) while rejecting mid-word false positives — e.g. `सत` must
  *not* match the middle of `पंचास्तिकाय` (पंचा-**स्ति**-काय), which otherwise
  gave it a spurious full coverage and floated it above topics that genuinely
  contain `सत्` as a word.
- **Normalization:** query tokens (`normalize_topic_token`) are lowercased and
  stripped of halants/virama, ZWNJ/ZWJ, separators, hyphens, dandas, whitespace;
  path segments are normalized in-word the same way (halant/joiners stripped)
  but keep their boundaries. This makes `सत्` match `सत` and folds conjuncts.
- **Token selection** (`build_coverage_tokens`): prefers the `keywords` list,
  else whitespace-splits `phrase`; drops Hindi connectives/postpositions
  (`व`, `के`, `में`, …) and tokens shorter than 2 chars so they don't dilute
  coverage.
- **`min_token_coverage`** (default **0.5**) — a topic must cover at least half
  of the meaningful query words. This keeps relevant child/sub-topics (which
  usually cover most tokens via their ancestor path) while dropping topics that
  share only one common word. Raise to `1.0` to require every word; `0.0`
  disables the guard (legacy behaviour). Coverage also multiplies the score, so
  even among survivors a full-coverage topic outranks a partial one.

Implemented in `services/query_service/pipeline/topics_match.py`
(`search_topics_trigram`).

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
      "source_url": "https://www.jainkosh.org/wiki/द्रव्य#3.1",
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

`source_url` (added) — the canonical jainkosh URL for the topic extract: the
keyword wiki page plus the topic's numbered section-path anchor (e.g.
`/wiki/द्रव्य#3.1`). Read **verbatim** from the top-level `source_url` of the
`topic_extracts` doc — the API never derives or reconstructs the anchor. Present for every match (independent of
`include_extracts`); `null` when the doc has no `source_url`. Consumers use it
to cite/link the topic extract in the final answer.

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
