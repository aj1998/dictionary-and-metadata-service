# 12 — Query Engine (GraphRAG path)

The brain of `query-service`. Takes pre-extracted keyword tokens (from `cataloguesearch-chat`'s LLM), resolves them to graph keyword nodes via aliases, traverses to topics, and ranks the result by weighted overlap.

Per FQ1: **graph-only + synonym dictionary in v1, embeddings deferred to v2**. Architecture leaves a clean seam for v2.

## Stages

```
tokens
  ↓ stage 1: NFC normalize
  ↓ stage 2: light Hindi-suffix strip (configurable)
  ↓ stage 3: alias-aware keyword resolution
  ↓ seed_keywords[]
  ↓ stage 4: graph traversal
  ↓ candidate_topics[]
  ↓ stage 5: weighted-overlap ranking
  ↓ ranked_topics[:top_k]
  ↓ stage 6: hydrate (Mongo extracts + Postgres mentions)
  ↓ response
```

Each stage is a pure function in `services/query_service/pipeline/` with explicit inputs/outputs. Easy to unit-test, easy to swap.

## Stage 1 — NFC normalization

```python
# pipeline/normalize.py
import unicodedata

ZWJ = "\u200D"
ZWNJ = "\u200C"

def nfc(s: str) -> str:
    s = unicodedata.normalize("NFC", s)
    s = s.replace(ZWJ, "").replace(ZWNJ, "")    # both stylistic in our sources
    return s.strip()
```

Apply to every token and to every stored keyword/alias `natural_key` at write time. This guarantees the join works.

## Stage 2 — Light Hindi-suffix strip (configurable)

Per FQ on point 21: chat hands us mostly-clean keyword tokens. We do **only conservative** suffix stripping. Aggressive lemmatization is out of scope.

```python
# pipeline/normalize.py

# Order matters — longer suffixes first.
HINDI_SUFFIXES = [
    "ियाँ", "ियों", "ोंमें", "ोंकी", "ोंका", "ोंके",
    "ें", "ों", "ाओं", "ाएँ", "ाएं",
    "ीं", "ी", "ये", "या",
    "का", "के", "की", "में", "से", "पर", "को",
    "ा", "े", "ो",
]

def strip_one_suffix(token: str) -> str:
    for suf in HINDI_SUFFIXES:
        if token.endswith(suf) and len(token) > len(suf) + 1:
            return token[: -len(suf)]
    return token
```

Stripping is **best-effort**. We try both the original and the stripped form when resolving (Stage 3 below). False positives become misses, not wrong matches, because we match against an explicit dictionary, not a free-form index.

## Stage 3 — Alias-aware resolution

Resolve `token → keyword_natural_key`. Two passes:

1. **Exact** match against `keywords.natural_key` or `keyword_aliases.alias_text` (Postgres, single batch query for all tokens).
2. **Suffix-stripped** retry on tokens that missed in pass 1.

Optionally a third **fuzzy** pass via `pg_trgm`, **off by default** in v1 (avoids surprising wrong matches; toggle via request flag `fuzzy: true`).

```sql
-- Single batched lookup for all tokens
WITH input(tok) AS (SELECT unnest($1::text[]))
SELECT i.tok, k.natural_key AS keyword_natural_key, 'exact' AS match_kind
FROM input i
JOIN keywords k ON k.natural_key = i.tok
UNION ALL
SELECT i.tok, k.natural_key, 'alias'
FROM input i
JOIN keyword_aliases ka ON ka.alias_text = i.tok
JOIN keywords k ON k.id = ka.keyword_id
WHERE NOT EXISTS (SELECT 1 FROM keywords k2 WHERE k2.natural_key = i.tok);
```

```python
# pipeline/resolve.py
async def resolve_tokens(pg, tokens: list[str]) -> list[Resolution]:
    normalized = [nfc(t) for t in tokens]
    resolved = await batch_lookup(pg, normalized)            # pass 1
    missed = [t for t in normalized if not in_resolved(t, resolved)]
    if missed:
        stripped = [strip_one_suffix(t) for t in missed]
        more = await batch_lookup(pg, stripped)
        resolved.extend(merge_back(missed, stripped, more, kind_suffix="suffix_strip"))
    return resolved   # one Resolution per input token, possibly with match_kind="none"
```

## Stage 4 — Graph traversal

One Cypher round trip with all seed keywords as input. Default depth = 2. Edge types restricted by request param.

```python
# pipeline/traverse.py
TRAVERSE_QUERY = """
UNWIND $seed_kws AS seed
MATCH (k:Keyword {natural_key: seed})
MATCH (k)-[r*1..%d]-(t:Topic)
WITH t, collect(DISTINCT k.natural_key) AS reached_seeds, r AS path_rels
WITH t, reached_seeds,
     [rel IN path_rels | type(rel)] AS rel_types,
     reduce(w = 0.0, rel IN path_rels | w + coalesce(rel.weight, 1.0)) AS path_weight
RETURN t.natural_key AS topic_nk,
       t.pg_id AS topic_pg_id,
       t.display_text_hi AS heading_hi,
       t.source AS source,
       reached_seeds,
       rel_types,
       path_weight
"""

async def traverse(neo4j, seed_kws: list[str], max_hops: int,
                   edge_types: list[str] | None) -> list[TopicHit]:
    cypher = TRAVERSE_QUERY % max_hops
    if edge_types:
        # restrict relationship pattern; substitute pipe-joined types
        cypher = cypher.replace("[r*1..", f"[r:{ '|'.join(edge_types) }*1..")
    async with neo4j.session(database="jainkb") as s:
        result = await s.run(cypher, seed_kws=seed_kws)
        return [TopicHit(**rec) async for rec in result]
```

`TopicHit` is one row per (topic, path) — multiple paths to the same topic remain as separate rows. The ranker collapses them.

## Stage 5 — Weighted-overlap ranking

```python
# pipeline/ranking.py
@dataclass
class RankedTopic:
    topic_nk: str
    topic_pg_id: str
    heading_hi: str
    source: str
    score: float
    matched_seed_keywords: list[str]
    edge_path_summary: list[dict]
    overlap_count: int
    weight_sum: float

def rank(hits: list[TopicHit], seed_kws: list[str]) -> list[RankedTopic]:
    # Collapse multi-path hits by topic_nk
    by_topic: dict[str, list[TopicHit]] = {}
    for h in hits:
        by_topic.setdefault(h.topic_nk, []).append(h)

    ranked = []
    for topic_nk, paths in by_topic.items():
        seeds_reached: set[str] = set()
        weight_sum = 0.0
        path_summary = []
        for p in paths:
            seeds_reached.update(p.reached_seeds)
            weight_sum += p.path_weight
            path_summary.append({"reached_seeds": p.reached_seeds,
                                 "rel_types": p.rel_types,
                                 "path_weight": p.path_weight})

        overlap = len(seeds_reached)
        # v1 score: dominate by overlap, tiebreak by weight_sum, penalize long paths.
        score = overlap * 10.0 + min(weight_sum, 5.0)

        ranked.append(RankedTopic(
            topic_nk=topic_nk,
            topic_pg_id=paths[0].topic_pg_id,
            heading_hi=paths[0].heading_hi,
            source=paths[0].source,
            score=score,
            matched_seed_keywords=sorted(seeds_reached),
            edge_path_summary=path_summary,
            overlap_count=overlap,
            weight_sum=weight_sum,
        ))

    ranked.sort(key=lambda r: (-r.score, -r.overlap_count, -r.weight_sum, r.topic_nk))
    return ranked
```

This module is intentionally tiny so a **v2** swap to PageRank or to a hybrid graph+vector ranker is a one-file change. The function signature `rank(hits, seed_kws) -> list[RankedTopic]` is the seam.

## Stage 6 — Hydration

Batch fetch:
- Mongo `topic_extracts` for every `topic_pg_id` in the top_k → single `find({_id: {$in: stable_ids}})`.
- Postgres `topic_mentions` for the top_k → single `IN` query.

Embed only Hindi blocks in extracts when `include_extracts=true`. Truncate each block to ~1500 chars to bound payload size.

## v2 extension points

When we add embeddings (post-MVP):

- **Stage 3.5 (new)**: between resolve and traverse, run a vector ANN search on token embeddings against keyword/topic embeddings. Add unmatched-but-semantically-close keywords to `seed_kws`. No other stage changes.
- **Stage 5 update**: include cosine-similarity component in score. Keep it as `score = α * overlap + β * weight_sum + γ * cosine_sim`, with α,β,γ tunable. v1 has γ=0.

Where embeddings live: a separate Postgres table `keyword_embeddings(keyword_id, embedding vector(384))` using `pgvector` extension. No new infra.

## Testing strategy

```
services/query_service/tests/
├── test_normalize.py            NFC, ZWJ stripping, suffix stripping table
├── test_resolve.py              alias resolution, fallback, fuzzy off by default
├── test_traverse.py             mock Neo4j, depth-1 and depth-2
├── test_ranking.py              overlap dominance, tiebreak by weight, ordering stable
├── test_pipeline_e2e.py         seeded fixture graph in real Neo4j (testcontainer)
└── fixtures/
    └── golden_query_responses.json
```

Golden fixtures cover:
- exact 3-token match (`पर्याय गुण भेद` → `द्रव्य गुण पर्याय भेद`)
- partial match (1 of 3 tokens unknown)
- alias hit (`आतम` → `आत्मा`)
- zero match (returns empty topics list)
- depth-2 reach (token's keyword has no direct topic, but a `RELATED_TO` keyword does)

## Definition of Done

- [ ] All six stages implemented as pure functions with type hints.
- [ ] `pipeline/ranking.py` is the only place ranking math lives — no scoring in Cypher.
- [ ] Resolve handles exact/alias/suffix-strip; fuzzy is opt-in via request flag.
- [ ] One Cypher call, one Mongo call, one Postgres call per request (verified by integration test counting DB roundtrips).
- [ ] Golden fixtures pass.
- [ ] Documentation comment in `ranking.py` calls out the v2 swap point with the proposed weighted-sum formula.
