# Query Engine & Ingestion Framework Improvements

> Suggested enhancements to `docs/design/12_query_engine.md` and the
> `docs/design/ingestion/` pipeline that arise naturally from the new
> entity types and the richer reference resolution now available.
>
> These are design suggestions — none are blockers for v1, but several
> (especially §1 and §2) have a large quality-of-life impact on hydration
> and should be incorporated before the first production ingest run.
>
> Each item is standalone. Adopt in any order.

---

## 1. `block_index` and `mention_path` on reference edges (HIGH PRIORITY)

### The problem

When the query engine hydrates a `MENTIONS_TOPIC` or `CONTAINS_DEFINITION`
edge in Stage 6, it currently fetches the entire `topic_extracts` or
`keyword_definitions` Mongo document. The caller only knows *which topic* was
mentioned — not *which block inside that topic* contained the reference. This
forces the UI to scan the entire block list to locate the relevant passage.

### The fix — `block_index` edge property

Add a `block_index: int` property to every `MENTIONS_TOPIC` and
`CONTAINS_DEFINITION` edge. The value is the 0-based index of the block (within
`Definition.blocks[]` or `Subsection.blocks[]`) that contained the reference
that produced the edge.

**Changes required:**

**`reference_edges.py`** — pass `block_index` into `_make_edge`:

```python
def build_reference_edges(
    block: Block,
    *,
    block_index: int,          # NEW: caller passes the loop index
    target: dict,
    edge_type: str,
    config: JainkoshConfig,
) -> list[dict]:
    ...
    # In _make_edge call, include block_index in props:
    props["block_index"] = block_index
```

**`envelope.py`** — thread `block_index` through the block loops:

```python
for i, b in enumerate(sub.blocks):
    edges.extend(build_reference_edges(
        b, block_index=i, target=target,
        edge_type="MENTIONS_TOPIC", config=config,
    ))

for i, b in enumerate(d.blocks):
    edges.extend(build_reference_edges(
        b, block_index=i, target=target,
        edge_type="CONTAINS_DEFINITION", config=config,
    ))
```

**`edge_types.yaml`** — `MENTIONS_TOPIC` and `CONTAINS_DEFINITION` gain
optional prop `block_index: int`.

**`upserts.py` (Neo4j)** — when merging edges, always `SET r.block_index = $bi`
so it's updated on re-ingest.

### Extended: `mention_path` for precise Mongo resolution

For definition-context edges (CONTAINS_DEFINITION), the block lives inside
`page_sections[section_index].definitions[definition_index].blocks[block_index]`.
Store a compact `mention_path` string on the edge:

```
"<section_index>/<definition_index>/<block_index>"
```

For subsection-context edges (MENTIONS_TOPIC):

```
"<topic_natural_key>/<block_index>"
```

This lets hydration do a single `$elemMatch` query (or path lookup in Mongo) to
fetch only the relevant block, rather than the full document.

**`reference_edges.py`** — add `mention_path` param alongside `block_index`.
**`envelope.py`** — compute and pass `mention_path` at call site.
**Neo4j edge props**: `mention_path: str` (nullable for edges without one).

### Hydration query (Stage 6) with `block_index`

```python
# services/query_service/pipeline/hydrate.py

async def hydrate_mention(db, topic_nk: str, block_index: int | None) -> dict:
    doc = await db.topic_extracts.find_one({"natural_key": topic_nk})
    if doc is None or block_index is None:
        return doc or {}
    blocks = doc.get("blocks", [])
    if 0 <= block_index < len(blocks):
        return {**doc, "blocks": [blocks[block_index]]}   # single-block slice
    return doc
```

This reduces payload size from ~5–20 blocks to 1 block per hit.

---

## 2. `definition_index` and `section_index` on `CONTAINS_DEFINITION` edges

The `CONTAINS_DEFINITION` edge currently points from a Gatha/etc. to a Keyword.
But a Keyword page may have 5 definitions in SiddhantKosh and 3 in PuranKosh.
Knowing only the keyword isn't enough to resolve *which definition* was cited.

### Fix

Store `section_index: int` and `definition_index: int` on the edge (in addition
to `block_index` from §1):

```python
props["section_index"]    = section_index     # which h2 section
props["definition_index"] = definition_index  # which numbered definition
props["block_index"]      = block_index       # which block inside that definition
```

This triplet uniquely locates any block in `keyword_definitions` and matches
the `mention_path` format `"<section_index>/<definition_index>/<block_index>"`.

**`envelope.py`** — the definition loop already has access to `section_index`
(loop variable over `result.page_sections`) and `definition_index` (from
`Definition.definition_index`). Thread these through to `build_reference_edges`.

---

## 3. Source-document link on `MENTIONS_TOPIC` edges

Currently `MENTIONS_TOPIC` edges have `props.source = "jainkosh"`. When we
eventually ingest from multiple sources (nikkyjain, vyakaran OCR), the source
alone is insufficient to hydrate the correct Mongo document.

### Fix

Add `source_natural_key: str` to `MENTIONS_TOPIC` props — the `natural_key`
of the Mongo document that contains the block:

- For JainKosh subsection context: `source_natural_key = topic_natural_key`
  (the `topic_extracts` doc).
- For JainKosh definition context: `source_natural_key = keyword_natural_key`
  (the `keyword_definitions` doc).
- For nikkyjain: `source_natural_key = gatha_natural_key` (the `gatha_prakrit`
  or `teeka_gatha_mapping` doc).

```python
# In _make_edge:
props["source_natural_key"] = source_natural_key   # caller passes this
```

Stage 6 hydration uses `source_natural_key` to pick the correct collection and
document without ambiguity, even as new sources are added.

---

## 4. Query engine: traverse new node labels

The Stage 4 Cypher traverse query currently matches only `Topic` nodes. With
`CONTAINS_DEFINITION` edges pointing to `Keyword` nodes, the traversal can now
reach a keyword (and thus its topics, via `HAS_TOPIC`) in 2 hops:

```
Keyword_A → [CONTAINS_DEFINITION] ← Gatha → [MENTIONS_TOPIC] → Topic_B
```

This path is currently missed. Two approaches:

**Option A — Extend traversal pattern (recommended for v1)**

Allow the traversal to also follow `CONTAINS_DEFINITION` edges (in reverse,
since they point to Keyword):

```cypher
MATCH (k:Keyword {natural_key: seed})
MATCH p = (k)-[:HAS_TOPIC|MENTIONS_KEYWORD|RELATED_TO|IS_A|PART_OF*1..%d]-(t:Topic)
  WHERE NOT any(r IN relationships(p) WHERE type(r) IN ['IN_SHASTRA','IN_TEEKA','IN_PUBLICATION'])
RETURN ...
```

The structural edges (`IN_SHASTRA`, `IN_TEEKA`, `IN_PUBLICATION`) should be
excluded from the traversal — they form a backbone tree that is unrelated to
semantic proximity.

**Option B — Two-phase query**

Phase 1: find all `Gatha`/etc. nodes that `CONTAINS_DEFINITION` to any of the
seed keywords. Phase 2: find all `Topic` nodes those same nodes `MENTIONS_TOPIC`
to. Union the two result sets. More controllable weighting but requires 2 round
trips.

Update `12_query_engine.md §Stage 4` to document the chosen approach and the
edge-type filter.

---

## 5. `is_leaf` filter in Stage 4 traversal

The `Topic.is_leaf` property is set by the parser. Leaf topics are the
queryable content nodes; container topics (headings) add traversal noise. Add a
filter to Stage 4 that scores leaf topics higher or restricts to leaves by
default:

```cypher
MATCH (k:Keyword {natural_key: seed})
MATCH (k)-[r*1..2]-(t:Topic)
WHERE t.is_leaf = true        // or: add to ranking score instead
RETURN t, ...
```

Alternatively, keep container topics in traversal but apply a penalty in the
ranker (`score × 0.5` for `is_leaf = false`). Document the choice in
`12_query_engine.md §Stage 5`.

---

## 6. Ingestion: `gatha_teeka_mapping` enrichment as a pipeline stage

The existing `teeka_gatha_mapping` Mongo collection stores per-(teeka, gatha)
anvayartha. The new `gatha_teeka_hindi` and `gatha_teeka_sanskrit` collections
are richer and more precisely keyed. The ingestion pipeline should treat their
population as an explicit stage:

**New pipeline stage** — add to `docs/design/ingestion/phase_1_schema_and_apply.md`
(or a new `phase_4_teeka_content.md`):

```
Stage: Teeka Content Ingestion
Source: nikkyjain HTML (local clone) or cataloguesearch OCR
Output:
  - Postgres kalashas rows
  - Mongo: gatha_teeka_sanskrit, gatha_teeka_hindi, gatha_teeka_bhaavarth_hindi
  - Mongo: kalash_sanskrit, kalash_hindi, kalash_bhaavarth_hindi
  - Neo4j: sync_kalash, ensure_lazy_node for GathaTeeka and bhaavarth nodes
  - Neo4j: IN_TEEKA and IN_PUBLICATION edges
Trigger: after Teeka and Publication rows exist in Postgres
```

Define an `IngestionSource` value for this stage (e.g., `'nj'` already covers
nikkyjain; add `'teeka_content'` if it becomes a separate pipeline).

---

## 7. `weight` tuning on structural edges

`IN_SHASTRA`, `IN_TEEKA`, `IN_PUBLICATION` are structural edges that should
not contribute to the traversal ranking. Two options:

- Set `weight = 0.0` on these edges at creation time.
- OR exclude them by edge type in the Stage 4 query pattern (simpler, see §4).

Recommendation: exclude by type in the Cypher (Option A from §4), and set
`weight = 0.0` as a belt-and-suspenders guard in upserts.

---

## 8. Deduplication of reference edges across definitions

A Gatha (e.g., `धवला:गाथा:199`) cited in 3 definitions of the same keyword
produces 3 `CONTAINS_DEFINITION` edges from the same `(from, to)` pair. The
current `_dedupe(edges)` in `envelope.py` removes duplicates by `(type, from,
to)`, which is correct for uniqueness.

However, when multiple definitions cite the same gatha, it is semantically
meaningful that the definition appears multiple times (each citation is distinct).
Consider changing deduplication to key on `(type, from, to, mention_path)` so
that distinct citation contexts are preserved as distinct edges:

```python
def _dedupe(edges: list[dict]) -> list[dict]:
    seen = set()
    out = []
    for e in edges:
        key = (
            e["type"],
            e["from"]["label"], e["from"]["key"],
            e["to"]["label"], e["to"]["key"],
            e["props"].get("mention_path", ""),   # NEW: distinguish by location
        )
        if key not in seen:
            seen.add(key)
            out.append(e)
    return out
```

Update `envelope.py` and the golden tests accordingly.

---

## 9. Summary of doc edits implied

| Doc | What to add / change |
|-----|---------------------|
| `docs/design/12_query_engine.md` | §Stage 4: document structural-edge exclusion filter, `CONTAINS_DEFINITION` traversal option (§4 above). §Stage 5: document `is_leaf` penalty option (§5). §Stage 6: document `block_index`-aware hydration (§1), `source_natural_key` lookup (§3). |
| `docs/design/ingestion/phase_1_schema_and_apply.md` | Add Teeka Content Ingestion stage (§6). |
| `workers/ingestion/jainkosh/reference_edges.py` | Add `block_index`, `mention_path`, `section_index`, `definition_index`, `source_natural_key` to edge props (§1, §2, §3). |
| `workers/ingestion/jainkosh/envelope.py` | Thread new params through block loops; update `_dedupe` key (§1, §8). |
| `parser_configs/_meta/edge_types.yaml` | Document new optional props on `MENTIONS_TOPIC` and `CONTAINS_DEFINITION` (informational comment). |
