# 07 — Topic Neighbors API (anchored related-topic expansion)

Adds one endpoint: **`POST /v1/query/topic_neighbors`**. It takes an explicit
set of `topic_natural_key`s (the *anchors*) and returns their graph neighbors
(related topics / related keywords / mentioned-in gathas), optionally hydrated.

## Why this exists

Today the only way to get "related topics" is [`/v1/query/graphrag`](02_topic_match_api.md),
whose neighbor expansion is anchored on **keyword-seed traversal** (Stage 3–5 of
[`12_query_engine.md`](../archived/initial/12_query_engine.md)), not on a topic
the caller already identified. Chat now identifies the anchor topic via the
precise trigram matcher [`/v1/query/topics_match`](02_topic_match_api.md) and
needs to expand neighbors of **exactly those** topics. See the chat-side
rationale in
[`03a_sequential_topic_anchor_expand.md`](../../../../cataloguesearch-chat/service/docs/jain_kb_service/03a_sequential_topic_anchor_expand.md).

This endpoint is the **expand** stage of an anchor→expand pipeline:

```
topics_match (anchor topics)  →  topic_neighbors (related topics, per anchor)
```

## Scope / non-goals

- **No keyword resolution, no token traversal.** Input is topics, not tokens.
- Reuses the exact neighbor Cypher already specified for
  `graphrag` `include_neighbors=true` (see
  [`02_topic_match_api.md`](02_topic_match_api.md) §2B "Implementation").
- No ranking math change; neighbors are returned grouped per anchor.
- No embeddings (graph-only, v1 — consistent with
  [`12_query_engine.md`](../archived/initial/12_query_engine.md)).

---

## Request

```json
{
  "topic_natural_keys": ["द्रव्य/स्वतंत्रता/लक्षण", "द्रव्य/गुण"],
  "max_neighbors_per_topic": 25,
  "include_extracts": false,
  "include_references": false,
  "edge_types": null
}
```

| Field | Required | Default | Notes |
|---|---|---|---|
| `topic_natural_keys` | yes | — | 1..N anchor topics; NFC-normalized on entry (Stage 1 of [`12_query_engine.md`](../archived/initial/12_query_engine.md)) |
| `max_neighbors_per_topic` | no | 25 | cap per anchor, applied per relation bucket after grouping |
| `include_extracts` | no | false | when true, hydrate Hindi extract blocks for each **neighbor topic** (same hydrator as §2B) |
| `include_references` | no | false | when true, include `{shastra, gatha, teeka, page}` refs for neighbor topics |
| `edge_types` | no | null | optional whitelist; structural edges always excluded |

Notes:
- Anchors not present in the graph are silently dropped and reported in
  `unresolved_topic_keys` (never an error).
- Empty `topic_natural_keys` → `400` (caller must not call with no anchors).

## Cypher

Identical traversal to `graphrag include_neighbors`, but keyed on
caller-supplied anchors instead of seed-traversed topics:

```cypher
UNWIND $topic_nks AS nk
MATCH (t:Topic {natural_key: nk})-[r:RELATED_TO|MENTIONS_TOPIC|HAS_TOPIC]-(n)
WHERE NOT type(r) IN ['IN_SHASTRA','IN_TEEKA','IN_PUBLICATION']
RETURN nk AS anchor_nk, type(r) AS rel, n
LIMIT $hard_cap
```

`$hard_cap = len(topic_nks) * max_neighbors_per_topic * 3` (a defensive upper
bound across the three buckets; the per-bucket cap is enforced in Python after
grouping). Bucket rows by `type(r)`:

- `RELATED_TO` (Topic↔Topic) → `related_topics`
- `MENTIONS_TOPIC` (Topic↔Gatha/Subsection) → `mentioned_in_gathas`
- `HAS_TOPIC` / Keyword↔Topic → `related_keywords`

(Same bucketing rule as §2B; if the implementation already has a
`bucket_neighbors()` helper for graphrag, reuse it — **do not duplicate**.)

## Response

```json
{
  "neighbors_by_anchor": [
    {
      "anchor_topic_natural_key": "द्रव्य/स्वतंत्रता/लक्षण",
      "related_topics": [
        {
          "topic_natural_key": "द्रव्य/स्वतंत्रता",
          "display_text_hi": "स्वतंत्रता",
          "ancestors_hi": ["द्रव्य"],
          "is_leaf": false,
          "source": "jainkosh",
          "extracts_hi": [],
          "references": []
        }
      ],
      "related_keywords": [
        { "keyword_natural_key": "स्वभाव" }
      ],
      "mentioned_in_gathas": [
        { "shastra_natural_key": "samaysaar", "gatha_number": 6 }
      ]
    }
  ],
  "unresolved_topic_keys": [],
  "tool_trace_id": "uuid-…"
}
```

- `related_topics[*]` is shaped as a **subset** of `topics_match` match items
  (so chat can attach them to the merged topic list without remapping).
- `extracts_hi` / `references` are populated only when the corresponding
  `include_*` flag is true; otherwise empty arrays.
- Hydration (when enabled) reuses the §2B Hydration path
  (`block_index`-aware, Hindi-only, 1500-char truncation) from
  [`12_query_engine.md`](../archived/initial/12_query_engine.md) Stage 6.

## Implementation

- New pipeline module `services/query_service/pipeline/topic_neighbors.py`
  exposing a pure `bucket_neighbors(rows) -> dict` (reuse graphrag's if present)
  and an `expand_neighbors(neo4j, anchors, ...)` coroutine.
- Wire into the FastAPI router next to `graphrag` / `topics_match`.
- One Cypher round-trip; one optional Mongo batch (extracts) + one optional
  Postgres batch (references) — same call-count discipline as
  [`12_query_engine.md`](../archived/initial/12_query_engine.md) DoD.
- Log: anchor count, total neighbor rows, per-bucket counts, `tool_trace_id`.

## Tests

- `test_topic_neighbors_e2e.py` — seeded testcontainer graph; anchors return
  expected `related_topics` / `mentioned_in_gathas`; structural edges excluded.
- `test_topic_neighbors_unknown_anchor.py` — unknown anchor lands in
  `unresolved_topic_keys`, others still expand, no crash.
- `test_topic_neighbors_cap.py` — `max_neighbors_per_topic` enforced per bucket.
- `test_topic_neighbors_hydration.py` — `include_extracts`/`include_references`
  populate only when flagged; Hindi-only blocks.
- `test_neighbors_helper_shared.py` — assert `topic_neighbors` and `graphrag`
  produce identical bucketing for the same rows (proves no logic fork).

## DoD

- [x] `POST /v1/query/topic_neighbors` live; OpenAPI generated.
- [x] Neighbor bucketing shared with graphrag (single source of truth).
- [x] One Cypher hop; hydration reuses §2B path.
- [x] Empty anchors → 400; unknown anchors → `unresolved_topic_keys`.
- [x] Manual test snippet under `docs/manual_testing/api/query/`.

## Implementation Notes

- **`bucket_neighbors` shared**: `traverse.py` is the single source of truth. `NeighborRow`
  extended with optional `is_leaf: bool | None` and `source: str | None`; `bucket_neighbors`
  includes them in `related_topics` dict entries when present (not None). Graphrag callers
  are unaffected because they don't pass these fields.

- **New pipeline module**: `services/query_service/pipeline/topic_neighbors.py` exposes
  `expand_neighbors(neo4j_driver, anchors, max_neighbors_per_topic, edge_types, mongo_db,
  database, include_extracts, include_references)`. The Cypher adds `anchor_nk` to the
  RETURN clause; rows are mapped to `NeighborRow` with `topic_nk = anchor_nk` so
  `bucket_neighbors` groups correctly by anchor.

- **ancestors_hi**: computed locally via `ancestors_from_natural_key(topic_natural_key)`
  after bucketing (no extra graph hop needed).

- **Hydration**: reuses `hydrate_topic_extracts_hi` from `jain_kb_common`; identical to
  the §2B graphrag hydration path.

- **New schemas** in `schemas/topic_match.py`: `TopicNeighborsRequest`,
  `ExpandedNeighborTopic`, `AnchorTopicNeighbors`, `TopicNeighborsResponse`.

- **Tests**: 5 test files covering e2e, unknown anchors, cap enforcement, hydration flags,
  and shared bucketing helper. All 84 tests in the query service test suite pass.
</content>
</invoke>
