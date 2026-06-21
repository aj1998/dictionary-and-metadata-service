# 08 — Content-Gated Multi-Hop Topic Neighbors (+ content-only `topics_match`)

Extends [`07_topic_neighbors_api.md`](07_topic_neighbors_api.md) with **depth**
(`max_hops`) whose counter only advances through topics that have **readable
(hydrated) content**, and tightens [`02_topic_match_api.md`](02_topic_match_api.md)
§2A so anchors are likewise content-bearing only.

Chat-side consumer & rationale: [`03b_two_hop_related_extracts.md`](../../../../cataloguesearch-chat/service/docs/jain_kb_service/03b_two_hop_related_extracts.md).

---

## Why this exists

`07` returns **1-hop** neighbors of each anchor. Chat wants the *related topics
and their related topics* — but with two constraints the user set:

1. **Depth must be content-aware.** Many graph `Topic` nodes carry **no readable
   extracts** — they are container/parent topics (e.g. *"2 द्रव्य निर्देश व शंका
   समाधान"*), label/index-seed topics, or `अन्य विषय` cross-reference (`see_also`)
   rows. Walking *through* such a node to reach a real, content-bearing topic
   must **not** consume a hop. Only arriving at a **hydrated** topic increments
   the depth counter. "Related traversal" through content-less nodes is free.

2. **Anchors and neighbors must be content-bearing.** `topics_match` today can
   return container/index topics that have nothing to show. Those should be
   filtered out so chat never anchors on (or expands to) an empty topic.

## The architectural constraint (read first)

**"Has readable content" is not a graph property.** Whether a `Topic` has
displayable extracts lives in **Mongo** (`topic_extracts`), computed by
`count_displayable_extract_blocks()` in
[`packages/jain_kb_common/jain_kb_common/hydration/topic_extracts.py`](../../../packages/jain_kb_common/jain_kb_common/hydration/topic_extracts.py)
(a block counts when its `kind ∉ EXCLUDED_BLOCK_KINDS` **and** it carries
`text_devanagari` or `hindi_translation` — see
[`05_definitions_and_extracts_hydration.md`](05_definitions_and_extracts_hydration.md)).
The Neo4j `Topic` node only stores `is_stub`, `source`,
`parent_keyword_natural_key`, `topic_path`, … (see
[`data_model_graph.md`](../data_model/data_model_graph.md) "Node labels").

**Consequence:** a single variable-length Cypher (`-[*1..2]-`) cannot implement
content-gated depth — it counts every edge equally and has no view of Mongo. So
depth must be an **iterative BFS** in Python.

> **Strongly recommended — denormalize the content flag onto the node (Part D).**
> Rather than calling Mongo once per BFS round, **store the displayable extract
> count on the `Topic` node at ingestion/sync time** so the BFS reads it straight
> from the Cypher rows and makes **zero** Mongo calls during traversal. Part D
> below specifies this. The BFS algorithm is written to work either way: if the
> node prop is present, use it; otherwise fall back to the per-round Mongo
> check. **Build Part D first** — it removes the only unbounded-cost concern and
> also lets `topics_match` (Part A) and `count_topic_extract_blocks` read the
> count without a Mongo aggregation.

---

## Part A — `topics_match` returns content-bearing topics only

`POST /v1/query/topics_match` gains one optional flag.

### Request (additions to [`02`](02_topic_match_api.md) §2A)

| Field | Required | Default | Notes |
|---|---|---|---|
| `content_only` | no | `true` | When true, drop matches whose displayable extract count is 0. |

> Default flips to **`true`** because every current caller wants readable
> anchors. A future caller that needs raw structural topics can pass `false`.

### Behavior

The handler already computes `extract_counts` via
`count_topic_extract_blocks` (see
[`routers/query.py`](../../../services/query_service/routers/query.py) topics_match
handler). When `content_only` is true, **filter `hits` to
`extract_counts[nk] > 0`** *before* building `matches` (and before applying
`limit`, so the limit yields N content-bearing topics, not N raw rows of which
some are empty).

- `extract_count` stays on every returned item (unchanged).
- `leaf_only` and `content_only` are independent; both may be set.

### Example

For the `द्रव्य` page in the user's screenshot: `2.1 एकांत पक्ष में द्रव्य का
लक्षण संभव नहीं` (has the book/extract icon) is kept; `2 द्रव्य निर्देश व शंका
समाधान` (container) and the `अन्य विषय` cross-reference rows (`see_also`) are
dropped.

---

## Part B — content-gated `max_hops` in `topic_neighbors`

`POST /v1/query/topic_neighbors` gains `max_hops`.

### Request (additions to [`07`](07_topic_neighbors_api.md))

| Field | Required | Default | Notes |
|---|---|---|---|
| `max_hops` | no | `1` | Number of **content hops**. `1` = current behavior. Depth counts only arrivals at hydrated topics. |

`include_extracts` / `include_references` / `max_neighbors_per_topic` /
`edge_types` keep their `07` meaning. `max_neighbors_per_topic` is the per-bucket
cap applied **per anchor on the final flattened result** (see Response).

### Algorithm — content-gated BFS

Replaces the single-shot `expand_neighbors` with a bounded BFS, per the
constraint above. Pseudocode (one run covers all anchors at once; track origin
anchor through the walk):

```
visited       = set(anchors)            # never re-expand or re-collect these
collected     = {anchor: []}            # hydrated related topics, per origin anchor
kw_by_anchor  = {anchor: []}            # related keywords, per origin anchor
gatha_by_anchor = {anchor: []}          # mentioned-in gathas, per origin anchor
frontier      = {anchor: {anchor}}      # origin_anchor -> set(nodes to expand this round)
content_depth = 0

while content_depth < max_hops and any(frontier.values()):
    # 1. one Cypher hop from the union of all frontier nodes (carry origin anchor)
    rows = neighbors_of(frontier)                # RELATED_TO|MENTIONS_TOPIC|HAS_TOPIC, structural excluded
    bucket rows by origin anchor into: topic_neighbors, keyword_neighbors, gatha_neighbors

    # 2. one batched Mongo check for all *new* topic neighbors this round
    new_topic_nks = { unvisited topic nks across all anchors }
    counts = count_displayable_extract_blocks(mongo, new_topic_nks)

    next_frontier = {anchor: set()}
    for each (anchor, topic_neighbor) in topic_neighbors:
        if topic_neighbor in visited: continue
        visited.add(topic_neighbor)
        if counts[topic_neighbor] > 0:          # HYDRATED → collect + it advances depth
            collected[anchor].append(topic_neighbor)
            next_frontier[anchor].add(topic_neighbor)   # may expand further next hop
        else:                                   # content-less passthrough → free hop
            next_frontier[anchor].add(topic_neighbor)   # expand, but did NOT count

    # keywords/gathas are leaves: collect, never expand, never count toward depth
    kw_by_anchor   merge keyword_neighbors (dedup per anchor)
    gatha_by_anchor merge gatha_neighbors  (dedup per anchor)

    content_depth += 1          # one content hop consumed
    frontier = next_frontier
```

Notes & invariants:

- **Depth counts content hops only.** Passing through a content-less topic adds
  it to the next frontier *without* the hop "landing" — but `content_depth`
  still increments once per BFS round. To make passthrough truly free, only
  increment `content_depth` on rounds that produced **≥1 hydrated** topic; a
  round that produced only passthrough topics does not advance depth (it just
  extends the frontier). Implement via a `produced_hydrated` flag per round.
  *(This is the precise reading of "navigating to a content-less related
  keyword/topic should not be counted in depth.")*
- **Keywords and gathas never count toward depth and are never expanded** — they
  are terminal related items collected at whatever round they appear.
- **`visited` set** prevents cycles and re-collection; anchors are pre-seeded so
  an anchor never appears as its own neighbor.
- **Hard cap / safety:** bound total Cypher rounds at `max_hops + K` (K small,
  e.g. 3, to absorb passthrough chains) and the per-round `LIMIT` as in `07`
  (`len(frontier) * max_per * 3`). Log when the safety bound trips.
- **Call-count discipline:** ≤ `(max_hops + K)` Cypher round-trips + **one**
  final hydration batch (extracts) + **one** final references/definitions batch.
  With Part D the content check reads the node prop returned by each round's
  Cypher, so there are **no** per-round Mongo content calls (the fallback path —
  when the prop is absent — adds one batched Mongo check per round).

### Response (shape unchanged from [`07`](07_topic_neighbors_api.md); flat per anchor)

Per the chosen shape ("flat per-anchor, deduped"): all content-bearing topics
found within the gated depth collapse into each anchor's `related_topics[]`,
deduped by `topic_natural_key`. Each entry gains a `hops` field = the content
depth at which it was collected (1 or 2). Container/passthrough topics are
**not** emitted (they were only traversal waypoints).

```jsonc
{
  "neighbors_by_anchor": [
    {
      "anchor_topic_natural_key": "द्रव्य/...",
      "related_topics": [
        { "topic_natural_key": "...", "display_text_hi": "...", "ancestors_hi": [...],
          "is_leaf": true, "source": "jainkosh", "hops": 1,
          "extracts_hi": [ { "block_index": 2, "text_hi": "...", "main_reference": {...} } ],
          "references": [ ... ] },
        { "topic_natural_key": "...", "hops": 2, "extracts_hi": [...], "references": [...] }
      ],
      "related_keywords": [ { "keyword_natural_key": "..." } ],
      "mentioned_in_gathas": [ { "shastra_natural_key": "...", "gatha_number": 6 } ]
    }
  ],
  "unresolved_topic_keys": [],
  "tool_trace_id": "..."
}
```

- `hops` is **new** and additive; existing consumers ignore it.
- `max_neighbors_per_topic` caps each bucket per anchor *after* the BFL flatten +
  dedup, sorted by `hops ASC` then graph order (closest first).
- Hydration of the collected topics reuses `hydrate_topic_extracts_hi` exactly
  as `07` already does (extracts + per-extract `main_reference` + flattened
  `references`).

---

## Part C — UI: topic search page shows content-bearing intermediate topics

Independent UI fix in the same repo (`ui/`), consuming Part A's `content_only`.

### The bug

On the topic search page, the **"मध्यवर्ती विषय भी दिखाएँ"** checkbox maps to
`include_other`. In the **search branch** of
[`ui/src/app/[locale]/(content)/topics/page.tsx`](../../../ui/src/app/[locale]/(content)/topics/page.tsx)
(`q` present) the call is `topicsMatch({ ..., leafOnly: !includeOther })`. So when
the filter is **off**, `leaf_only=true` drops **every** non-leaf topic — including
intermediate topics that have their **own readable content and** further
expansions (e.g. *"आत्मा के बहिरात्मादि 3 भेद"* — 100% match, has extracts **and**
children). The user wants those kept when the filter is off; only **content-less**
intermediate topics should be hidden.

### Fix

1. **Filter by content, not by leaf.** In the search branch, replace
   `leafOnly: !includeOther` with `contentOnly: !includeOther` (Part A flag):
   - filter **on** (`include_other=1`) → `content_only=false` (show everything, as today).
   - filter **off** → `content_only=true` (show leaf **and** non-leaf topics that
     have `extract_count > 0`; hide content-less intermediates).
   - Drop `leaf_only` from this call (it conflated "intermediate" with
     "content-less"). Add `contentOnly` to the
     [`ui/src/lib/api/query.ts`](../../../ui/src/lib/api/query.ts) `topicsMatch`
     params → `content_only` in the request body.
   - `include_extracts` stays `false` here; the card relies on `extract_count`
     (already on `TopicMatchItem`) to decide the पढ़ें affordance, so ensure the
     response keeps returning `extract_count` (it does — unchanged by Part A).

2. **Show BOTH actions for content-bearing intermediate topics.** Today
   [`TopicNavAction`](../../../ui/src/components/TopicNavAction.tsx) renders
   पढ़ें **or** the external-link (expand) action via the single `isLeaf` branch
   (`showReadIcon = isLeaf !== false`). For a topic that **has extracts AND is
   non-leaf**, render **both**:
   - **पढ़ें** (BookOpen) → opens the `DefinitionModal` with the topic's own extracts.
   - **link** (ExternalLink) → navigates to the parent keyword page (the expansion),
     as the non-leaf branch does now.
   Implement by splitting the either/or: drive पढ़ें off `hasExtracts` and the
   expand-link off `isLeaf === false`, so all four combinations work
   (leaf+content → पढ़ें only; non-leaf+content → both; non-leaf+no-content →
   link only; leaf+no-content → none). Update
   [`TopicMatchActions`](../../../ui/src/components/TopicMatchActions.tsx)
   (which already fetches `hasExtracts` + `isLeaf`) to pass both signals, and the
   no-search listing card in `topics/page.tsx` (lines ~183-190) which currently
   gates `TopicNavAction` on `item.topic_path && item.is_leaf` — relax to also
   render for non-leaf topics with `extract_count > 0`.

### UI tests / verification

- Search `आत्मा के बहिरात्मादि 3 भेद` with the filter **off**: the 100% intermediate
  topic appears, with both पढ़ें and the expand link; a content-less intermediate
  (e.g. a pure container) does **not** appear.
- Filter **on**: result set unchanged from today.
- Follow `ui/AGENTS.md` (this Next.js has breaking changes — read the bundled
  docs before editing).

---

## Part D — (recommended, build first) denormalize content count onto the Topic node

Add a graph-node property so "has readable content" is answerable from Neo4j
alone — no Mongo round-trip during traversal, matching, or counting.

### Property

On `Topic` nodes, add:

| Prop | Type | Meaning |
|---|---|---|
| `displayable_extract_count` | int | Count of displayable extract blocks (`kind ∉ EXCLUDED_BLOCK_KINDS` **and** carrying `text_devanagari`/`hindi_translation`) — exactly what `count_displayable_extract_blocks` returns. `0` ⇒ content-less. |

Use the count (not just a bool) so the UI badge / `extract_count` can also read
it later; "has content" is `displayable_extract_count > 0`. Document it in
[`data_model_graph.md`](../data_model/data_model_graph.md) "Node labels" (Topic
row) and add an index:

```cypher
CREATE INDEX topic_displayable_extract_count IF NOT EXISTS
  FOR (n:Topic) ON (n.displayable_extract_count);
```

### Where it's set

The graph is a **mirror** of Postgres+Mongo and re-sync must be idempotent (see
[`data_model_graph.md`](../data_model/data_model_graph.md) "Sync from Postgres"),
so the count must be (re)computed wherever a topic's extracts are (re)written:

- **`sync_topic`** in
  [`packages/jain_kb_common/jain_kb_common/db/neo4j/upserts.py`](../../../packages/jain_kb_common/jain_kb_common/db/neo4j/upserts.py):
  add a `displayable_extract_count: int = 0` kwarg and
  `SET t.displayable_extract_count = $cnt` in the MERGE.
- **Caller (jainkosh ingestion / graph_sync)**: compute the count from the
  topic's `topic_extracts` payload being applied (the envelope already carries
  the blocks — see
  [`workers/ingestion/jainkosh/envelope.py`](../../../workers/ingestion/jainkosh/envelope.py)
  / `apply.py`), or via `count_displayable_extract_blocks` right after the Mongo
  write, and pass it into `sync_topic`. Reuse the **shared block-kind predicate**
  from `jain_kb_common/hydration/blocks.py` — do **not** duplicate the rule, so
  the node count and the hydrator can never disagree.
- **Stub nodes** default `displayable_extract_count = 0` (via `coalesce`, never
  overwriting a real value) — consistent with existing stub handling.
- **Full resync** (`POST /admin/graph/resync`) recomputes for all topics.

### Consumers that drop their Mongo call

- **Part B BFS**: `fetch_anchor_neighbors` Cypher already returns neighbor node
  props — add `n.displayable_extract_count AS extract_count` to the RETURN and
  gate depth on that field. No per-round Mongo check.
- **Part A `topics_match`**: filter `content_only` on the graph/Postgres-joined
  count instead of (or in addition to) the Mongo `count_topic_extract_blocks`
  aggregation. (If `topics_match` candidates come from Postgres trigram, either
  join the count from Neo4j by nk in the existing neighbor step, or keep the
  Mongo count for `topics_match` only — it's a single batched call there, not
  per-round. Decide based on least churn; the BFS is where the repeated cost was.)

### Migration / backfill

One-off backfill for existing topics: iterate topics, compute
`count_displayable_extract_blocks` in batches, `SET` the prop. Add as an admin
resync path or a small migration script. Until backfilled, the BFS fallback
(per-round Mongo check when the prop is absent/null) keeps correctness.

### Tests

- `sync_topic` sets `displayable_extract_count` from the predicate; stub upsert
  doesn't clobber it.
- A topic whose only blocks are `see_also`/`table` (or text-less) → count `0`;
  a topic with real Hindi blocks → correct count (parity with
  `count_displayable_extract_blocks` on the same fixture).
- BFS reads the node prop and issues **no** Mongo content call when present.
- Resync recomputes after an extract edit (count goes 0→N and N→0).

---

## Part E — one source of truth: query-engine carries content/leaf signals; UI stops per-card Mongo fetches

The `displayable_extract_count` from Part D (and `is_leaf`) must flow through
**every** topic-returning query-engine response, and the UI must decide
पढ़ें-vs-link **from the search result itself** — not via a per-card detail fetch.

### Current redundancy

- `topics_match` items already carry `extract_count` + `is_leaf`
  ([`schemas/topic_match.py`](../../../services/query_service/schemas/topic_match.py)).
- **Global search** (`ui/.../(content)/search/page.tsx`) already does this right —
  it reads `tp.extract_count` from the result, no per-card fetch.
- **`/topics` search cards** do **not**: `TopicMatchActions`
  ([`ui/src/components/TopicMatchActions.tsx`](../../../ui/src/components/TopicMatchActions.tsx))
  calls `getEntityDetail(topic, nk)` **per card** purely to learn `hasExtracts`
  and `isLeaf` — data the `topics_match` item already has. That's one redundant
  round-trip per result card (and it ultimately reads Mongo extracts).

### Fix

1. **Server: source `extract_count` from the Part D node prop.** Wherever the
   query-engine populates `extract_count` (topics_match) or content signals
   (topic_neighbors `related_topics[*]`), read `Topic.displayable_extract_count`
   instead of a Mongo aggregation. Single source of truth = the node prop;
   `count_topic_extract_blocks` becomes a thin reader of it (or is dropped from
   the hot path). Ensure `extract_count` + `is_leaf` are present on:
   - `topics_match` items (already present — just re-source the value),
   - `topic_neighbors` `related_topics[*]` (add `extract_count`; `is_leaf` already
     in the `07` shape) so chat/UI consumers needn't re-fetch,
   - the global-search topics section (already uses `extract_count`).
2. **UI: decide actions from the result, drop the per-card fetch.** Refactor
   `TopicMatchActions` to take `extractCount` + `isLeaf` as **props** from the
   `topics_match` card (`TopicMatchCard` in
   [`topics/page.tsx`](../../../ui/src/app/[locale]/(content)/topics/page.tsx)
   already has `item.extract_count` / `item.is_leaf`) and **remove the
   `getEntityDetail` effect**. Render:
   - पढ़ें when `extractCount > 0` (opens modal),
   - expand link when `isLeaf === false`,
   - both when both (the Part C dual-action rule — keep this behaviour identical
     across global search and `/topics`).
   The detail/extracts fetch stays **lazy on click** (the modal still loads the
   blocks when पढ़ें is pressed) — that's the only remaining, on-demand Mongo read.

### Result

No topic search card issues a Mongo/detail call just to render its buttons;
button/link behaviour everywhere (global search, `/topics` search + listing) is
driven by the denormalized node signals from Part D. Detail is fetched only when
a user actually opens a topic's extracts.

### Tests / verification

- `/topics?q=…` renders correct पढ़ें/link/both without any `getEntityDetail`
  call before interaction (assert no detail request fires on list render).
- Global search and `/topics` agree on the affordance for the same topic.
- `topic_neighbors related_topics[*]` include `extract_count` sourced from the
  node prop.

---

## Implementation

### Files (dictionary-and-metadata-service)

- [`services/query_service/pipeline/topic_neighbors.py`](../../../services/query_service/pipeline/topic_neighbors.py)
  - Add `max_hops` param to `expand_neighbors`; implement the BFS loop above.
  - Reuse `fetch_anchor_neighbors` for each round (it already returns
    `NeighborRow` keyed by the frontier node); extend it to carry the **origin
    anchor** distinct from the immediate frontier node (add an `origin_nk`
    passthrough, or run per-anchor frontiers — prefer carrying `origin_nk` in
    the UNWIND payload `[{origin, node}]` so it stays one Cypher per round).
  - Reuse `bucket_neighbors` (single source of truth — do **not** fork).
  - Add `count_displayable_extract_blocks` content-check per round (import from
    `jain_kb_common.hydration.topic_extracts`).
  - Final hydration batch unchanged.
- [`services/query_service/pipeline/topics_match.py`](../../../services/query_service/pipeline/topics_match.py)
  + [`routers/query.py`](../../../services/query_service/routers/query.py):
  apply the `content_only` filter on `hits` using the already-computed
  `extract_counts`.
- [`services/query_service/schemas/topic_match.py`](../../../services/query_service/schemas/topic_match.py):
  - `TopicNeighborsRequest`: add `max_hops: int = 1`.
  - `TopicsMatchRequest`: add `content_only: bool = True`.
  - `ExpandedNeighborTopic`: add `hops: int = 1`.
- Regenerate OpenAPI.

### Logging

- `topic_neighbors`: per round log `round`, `frontier_size`, `hydrated_count`,
  `passthrough_count`, `content_depth`; final log totals + `tool_trace_id`
  (extends the existing `07` log line).
- `topics_match`: log `hits_before_content_filter`, `hits_after`.

---

## Tests

dictionary-and-metadata-service (`tests/` testcontainer graph + Mongo fixtures):

- `test_topic_neighbors_max_hops_content_gated.py` — anchor → content-less
  container → hydrated topic returns the hydrated topic at `hops=1` (passthrough
  did not consume the hop); a genuinely 2-content-hop topic returns at `hops=2`;
  `max_hops=1` excludes the hop-2 topic.
- `test_topic_neighbors_passthrough_free.py` — chain of N content-less topics
  before a hydrated one still reaches it within `max_hops=1` (passthrough free),
  bounded by the safety cap.
- `test_topic_neighbors_visited_cycle.py` — cyclic `RELATED_TO` does not loop;
  anchor never collected as its own neighbor.
- `test_topic_neighbors_keywords_gathas_no_depth.py` — related keywords/gathas
  collected but never expanded and never advance depth.
- `test_topic_neighbors_cap_after_flatten.py` — `max_neighbors_per_topic`
  enforced per bucket after flatten+dedup; `hops ASC` ordering.
- `test_topics_match_content_only.py` — container/index topics
  (`extract_count == 0`) dropped when `content_only=true`, kept when false;
  `limit` yields N content-bearing.
- Backward-compat: `max_hops` default `1` reproduces `07` results
  (reuse/extend existing `07` tests).

Run the full query-service suite (per repo AGENTS.md) — no regressions.

---

## Manual verification

Add snippets under `docs/manual_testing/api/query/`:

```bash
# content-only anchors
curl -s localhost:8004/v1/query/topics_match -H 'content-type: application/json' \
  -d '{"keywords":["द्रव्य"],"content_only":true,"include_extracts":false}' | jq '.matches[].topic_natural_key'

# 2 content-hop related topics with extracts
curl -s localhost:8004/v1/query/topic_neighbors -H 'content-type: application/json' \
  -d '{"topic_natural_keys":["<anchor nk>"],"max_hops":2,"include_extracts":true,"include_references":true}' \
  | jq '.neighbors_by_anchor[0].related_topics[] | {topic_natural_key, hops, n_extracts:(.extracts_hi|length)}'
```

---

## DoD

- [ ] **Part D (build first):** `Topic.displayable_extract_count` set by
      `sync_topic` (shared block predicate), indexed, documented in
      `data_model_graph.md`, backfilled; stubs default 0; resync recomputes.
- [ ] BFS reads the node prop and makes no per-round Mongo content call when present.
- [ ] `topics_match` `content_only` (default true) drops `extract_count==0`
      topics before `limit`; flag documented in [`02`](02_topic_match_api.md).
- [ ] `topic_neighbors` `max_hops` (default 1) implemented as content-gated BFS;
      passthrough through content-less topics does **not** consume depth;
      keywords/gathas never advance depth.
- [ ] Response `related_topics[*].hops` added; flat per-anchor, deduped, capped
      after flatten.
- [ ] Bucketing still shared with graphrag (no fork); hydration reuses §2B path.
- [ ] Bounded round-trips (no per-topic fan-out); per-round + summary logs.
- [ ] Tests above pass; full query-service suite green; manual snippets added.
- [ ] `07` and `02` specs cross-link to this doc; OpenAPI regenerated.
- [ ] **Part C (UI):** topic search with filter off uses `content_only` (not
      `leaf_only`) so content-bearing intermediate topics show; cards render both
      पढ़ें and the expand link for non-leaf topics with extracts.
- [ ] **Part E:** `extract_count`/`is_leaf` flow through all topic query-engine
      responses (sourced from Part D node prop); `TopicMatchActions` drops its
      per-card `getEntityDetail` and decides actions from the result; affordance
      consistent across global search and `/topics`; detail fetched only on click.

## Open questions for the implementing agent

- Confirm the precise depth rule with the team if ambiguous: this spec treats a
  round that produces **only** passthrough topics as **not** advancing
  `content_depth` (truly free passthrough). If instead every Cypher round should
  cost one hop regardless, simplify by incrementing unconditionally.

---

## Implementation Notes (2026-06-22)

Implemented in build order **D → A → B → C/E**. All backend + UI parts landed.

### Part D — `Topic.displayable_extract_count`
- Shared predicate centralized in
  [`jain_kb_common/hydration/blocks.py`](../../../packages/jain_kb_common/jain_kb_common/hydration/blocks.py):
  `is_displayable_block` / `count_displayable_blocks` — single source of truth so
  the node count and the hydrator can never disagree.
- `sync_topic` ([`upserts.py`](../../../packages/jain_kb_common/jain_kb_common/db/neo4j/upserts.py))
  gained `displayable_extract_count: int = 0` and `SET t.displayable_extract_count`.
- Index `topic_displayable_extract_count` added in
  [`constraints.py`](../../../packages/jain_kb_common/jain_kb_common/db/neo4j/constraints.py).
- Set at ingestion ([`workers/ingestion/jainkosh/apply.py`](../../../workers/ingestion/jainkosh/apply.py)
  computes per-topic counts from the extract blocks being applied) and recomputed
  on full resync ([`resync.py`](../../../services/core_service/domains/navigation/services/resync.py)
  batches `count_displayable_extract_blocks` and threads `mongo_db` from the admin route).
- **Backfill** is `POST /admin/graph/resync` — it now recomputes the prop for all
  topics, so no separate migration script was needed. Until backfilled, the BFS
  falls back to a per-round Mongo content check when the prop is null.
- Tests: `tests/db/neo4j/test_neo4j_graph.py::test_sync_topic_sets_displayable_extract_count`
  (set + recompute N→0) and `::test_sync_topic_displayable_extract_count_defaults_zero`.

### Part A — `topics_match content_only`
- `TopicsMatchRequest.content_only: bool = True`. Handler over-fetches
  (`limit * 5`) then drops `extract_count == 0` hits before applying `limit`;
  logs `hits_before`/`hits_after`. Tests: `test_topics_match_content_only.py`.

### Part B — content-gated multi-hop BFS
- `TopicNeighborsRequest.max_hops: int = 1`; `ExpandedNeighborTopic` gained
  `hops` + `extract_count`. BFS in
  [`topic_neighbors.py`](../../../services/query_service/pipeline/topic_neighbors.py)
  is **forward-only** (global `visited` set, anchors pre-seeded; back-edges to
  visited nodes skipped — each node expanded at most once). Content-less topics
  are free passthroughs (don't advance `content_depth`); keywords/gathas are
  terminal (collected, never expanded/counted). Capped after flatten, sorted
  `hops ASC`. Open question resolved in favour of **free passthrough** (a
  passthrough-only round does not cost a hop). Tests:
  `test_topic_neighbors_max_hops.py`.

### Parts C + E — UI
- [`query.ts`](../../../ui/src/lib/api/query.ts) `topicsMatch` gained
  `contentOnly` → `content_only` (defaults `false` for legacy callers; `/topics`
  sets it from the filter).
- [`topics/page.tsx`](../../../ui/src/app/[locale]/(content)/topics/page.tsx)
  search branch uses `contentOnly: !includeOther` (dropped `leafOnly`); listing
  card gating relaxed to non-leaf topics with `extract_count > 0`.
- [`TopicNavAction.tsx`](../../../ui/src/components/TopicNavAction.tsx) split into
  पढ़ें (driven by `hasExtracts`) + expand link (driven by `isLeaf === false`),
  so all four combinations render correctly; legacy fallback when `hasExtracts`
  omitted.
- [`TopicMatchActions.tsx`](../../../ui/src/components/TopicMatchActions.tsx) now
  takes `extractCount` + `isLeaf` props and **dropped the per-card
  `getEntityDetail` effect**; detail fetched lazily on पढ़ें click only.
- Global search ([`search/page.tsx`](../../../ui/src/app/[locale]/(content)/search/page.tsx))
  passes `isLeaf` + `hasExtracts` so the dual-action affordance matches `/topics`.
