# 17 — Advanced RAG Enhancements Spec (graph-aware re-rank + observability)

Scope context: [`scope/06_advanced_rag_and_finetuning.md`](../../scope/06_advanced_rag_and_finetuning.md) (retrieval enhancements + observability).

A new `rag-enhancer-service` (port 8007) sits between `cataloguesearch-chat` and `cataloguesearch`. It does **not** modify either of those repos — they remain black boxes called over HTTP. For every chat query it: (1) hits `cataloguesearch /search` for the baseline vector+BM25 hits, (2) hits this repo's `query-service /v1/query/graphrag` for the graph topic/keyword set, (3) re-ranks the cataloguesearch chunks by overlap with that set + counter priors, (4) logs both rankings to `rag_query_logs` so admin dashboards can compare. A scheduled job populates `chunk_graph_coverage` from the same data so the admin UI can answer "which chunks are graph-orphaned?".

## Expected upstream contracts (black box)

```
POST {CATALOGUESEARCH_URL}/search
  body: {"query": str, "top_k": int, "lang": "hi"|"en"}
  resp: {"hits": [{"chunk_id": str,
                   "shastra_natural_key": str | null,
                   "gatha_natural_key":   str | null,
                   "text_hi": str,
                   "score": float,
                   "metadata": {...}}],
         "latency_ms": int}

POST {QUERY_SERVICE_URL}/v1/query/graphrag
  (existing — see 12_query_engine.md)
  resp.topics[*].topic.natural_key, resp.topics[*].topic.display_text_hi,
  resp.tokens_resolved[*].matched_keyword_natural_key
```

If either contract drifts, `rag-enhancer` returns the upstream cataloguesearch response unchanged and logs `reordered=false` with the error captured.

## Phase A — `rag-enhancer-service`

### Files

```
services/rag_enhancer_service/
├── __init__.py
├── main.py                FastAPI app, /healthz, lifespan, CORS
├── config.py              Settings (DATABASE_URL,
│                          CATALOGUESEARCH_URL, CATALOGUESEARCH_API_KEY,
│                          QUERY_SERVICE_URL,   QUERY_SERVICE_API_KEY,
│                          PORT=8007, RAG_TOP_K=20, RAG_RERANK_TOP_K=10,
│                          RAG_GRAPH_TIMEOUT_MS=400, RAG_LOG_ASYNC=true,
│                          RAG_ALPHA=0.60, RAG_BETA=0.25, RAG_GAMMA=0.15,
│                          RAG_COUNTER_HALF_LIFE=200)
├── deps.py                AsyncSession dep, httpx.AsyncClient singletons
├── routers/
│   ├── search.py          POST /v1/rag/search   (drop-in for chat)
│   └── debug.py           POST /v1/rag/explain  (returns both rankings)
├── upstreams/
│   ├── catalogue.py       async def search_baseline(query, top_k) -> list[ChunkHit]
│   └── graph.py           async def graph_topics(query) -> GraphContext
├── rerank.py              rerank(hits, ctx) -> list[RankedHit]; explain(...)
├── coverage.py            recompute_chunk_coverage()  (cron: hourly)
└── tests/
    ├── conftest.py
    ├── test_rerank_unit.py
    ├── test_rerank_orders_overlap.py
    ├── test_no_graph_hit_passthrough.py
    ├── test_upstream_timeout_falls_back.py
    ├── test_logs_written.py
    └── test_coverage_recompute.py
```

Shared models live in `packages/jain_kb_common/db/postgres/rag.py`.

### Postgres schema (migration `0030_rag_observability.py`)

```sql
CREATE TABLE rag_query_logs (
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  query_text            TEXT NOT NULL,
  query_lang            TEXT NOT NULL DEFAULT 'hi',
  base_top1_chunk_id    TEXT,
  graph_top1_chunk_id   TEXT,
  reordered             BOOLEAN NOT NULL DEFAULT false,
  base_ranking          JSONB NOT NULL DEFAULT '[]'::jsonb,   -- [{chunk_id, score}, ...]
  graph_ranking         JSONB NOT NULL DEFAULT '[]'::jsonb,   -- [{chunk_id, score, components}, ...]
  graph_topic_nks       JSONB NOT NULL DEFAULT '[]'::jsonb,
  graph_keyword_nks     JSONB NOT NULL DEFAULT '[]'::jsonb,
  latency_ms            INT  NOT NULL,
  catalogue_latency_ms  INT,
  graph_latency_ms      INT,
  caller                TEXT NOT NULL,             -- 'cataloguesearch-chat' | 'admin' | 'ui'
  user_id               UUID,                      -- nullable; from JWT if present
  created_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_rag_query_logs_created  ON rag_query_logs(created_at DESC);
CREATE INDEX idx_rag_query_logs_caller   ON rag_query_logs(caller, created_at DESC);
CREATE INDEX idx_rag_query_logs_no_graph ON rag_query_logs((graph_topic_nks = '[]'::jsonb))
  WHERE graph_topic_nks = '[]'::jsonb;

CREATE TABLE chunk_graph_coverage (
  chunk_id          TEXT PRIMARY KEY,
  shastra_nk        TEXT,
  topic_count       INT  NOT NULL DEFAULT 0,
  keyword_count     INT  NOT NULL DEFAULT 0,
  topic_nks         JSONB NOT NULL DEFAULT '[]'::jsonb,
  keyword_nks       JSONB NOT NULL DEFAULT '[]'::jsonb,
  last_computed_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_chunk_coverage_low ON chunk_graph_coverage(topic_count, keyword_count)
  WHERE topic_count = 0 AND keyword_count = 0;
CREATE INDEX idx_chunk_coverage_shastra ON chunk_graph_coverage(shastra_nk);
```

### Pydantic contracts

```python
class ChunkHit(BaseModel):
    chunk_id: str
    shastra_natural_key: str | None = None
    gatha_natural_key:   str | None = None
    text_hi: str
    base_score: float
    topic_nks:   list[str] = Field(default_factory=list)   # from chunk metadata if present
    keyword_nks: list[str] = Field(default_factory=list)

class GraphContext(BaseModel):
    topic_nks:       list[str]
    keyword_nks:     list[str]   # resolved seed keywords
    topic_weights:   dict[str, float] = Field(default_factory=dict)
    keyword_weights: dict[str, float] = Field(default_factory=dict)

class RankedHit(BaseModel):
    chunk_id: str
    final_score: float
    base_score: float
    overlap_topics:   list[str]
    overlap_keywords: list[str]
    components: dict[str, float]    # {'base','topic_overlap','keyword_overlap','counter_prior'}

class SearchIn(BaseModel):
    query: constr(min_length=1, max_length=2000)
    top_k: conint(ge=1, le=50) = 10
    lang:  Literal['hi','en'] = 'hi'
    caller: str = 'cataloguesearch-chat'

class SearchOut(BaseModel):
    query_id: UUID
    hits: list[RankedHit]
    reordered: bool
    stats: dict
```

### Re-rank formula (precise)

For each `ChunkHit h` with graph context `ctx`:

```
overlap_topics_set   = set(h.topic_nks)   ∩ set(ctx.topic_nks)
overlap_keywords_set = set(h.keyword_nks) ∩ set(ctx.keyword_nks)

topic_overlap   = Σ ctx.topic_weights[t]   for t in overlap_topics_set
keyword_overlap = Σ ctx.keyword_weights[k] for k in overlap_keywords_set

# counter prior: down-weight extremely frequent topics (anti-popularity bias).
# `cnt(t)` is `counters.topic_total_count` (already maintained, design doc 10).
# RAG_COUNTER_HALF_LIFE = h (default 200): chunks tagged with topics of count
# around the half-life get prior = 0.5; very rare topics → ≈1.0; very common → ≈0.
counter_prior = mean( h / (h + cnt(t))  for t in overlap_topics_set )
                # defaults to 0.0 when overlap_topics_set is empty

# Normalise base_score within this response: bz = (s - min) / (max - min + 1e-9)
final = α * bz
      + β * tanh(topic_overlap)
      + γ * tanh(keyword_overlap)
      + δ * counter_prior

# Defaults (env-overridable):
#   α = RAG_ALPHA   = 0.60
#   β = RAG_BETA    = 0.25
#   γ = RAG_GAMMA   = 0.15
#   δ = 1 - α - β - γ  (auto, currently 0.00 if defaults sum to 1.0 — see note)
```

`δ` is computed as `max(0, 1 - α - β - γ)` so admins changing the three weights via env see counter_prior contribute automatically. Default config sets δ=0 explicitly so launch behaviour is "graph-aware re-rank without counter prior" until counters are battle-tested; bumping any of α/β/γ below the unity line activates δ.

Ranking is stable by `(-final, -base_score, chunk_id)`. Top `RAG_RERANK_TOP_K` are returned.

If `ctx.topic_nks ∪ ctx.keyword_nks == ∅`, skip rerank entirely; return baseline order, set `reordered=false`, log `graph_topic_nks=[]`.

### Wiring the graph context

`upstreams/graph.py` does **one** call into the existing query-service:

```python
async def graph_topics(query: str) -> GraphContext:
    # Tokenisation: split on whitespace + punctuation, NFC normalise.
    # Send the whole token list — query-service does its own resolve.
    tokens = simple_tokenise(query)
    payload = {"tokens": tokens, "top_k": 20, "max_hops": 2,
               "include_extracts": False, "include_references": False,
               "caller": "rag-enhancer"}
    resp = await client.post(f"{settings.QUERY_SERVICE_URL}/v1/query/graphrag",
                             json=payload, timeout=settings.RAG_GRAPH_TIMEOUT_MS/1000)
    body = resp.json()
    return GraphContext(
        topic_nks=[t["topic"]["natural_key"] for t in body["topics"]],
        keyword_nks=[r["matched_keyword_natural_key"]
                     for r in body["tokens_resolved"]
                     if r["matched_keyword_natural_key"]],
        topic_weights={t["topic"]["natural_key"]: float(t["score"])
                       for t in body["topics"]},
        keyword_weights={r["matched_keyword_natural_key"]: 1.0
                         for r in body["tokens_resolved"]
                         if r["matched_keyword_natural_key"]},
    )
```

On timeout / 5xx / connection error: return empty `GraphContext()` and continue (passthrough).

### Chunk → topic/keyword resolution

`ChunkHit.topic_nks` / `.keyword_nks` come from the chunk's metadata fields written at ingest time. Two cases:

1. **Text chunks** ingested by `cataloguesearch` directly: the metadata may not include topics. In that case look them up by `gatha_natural_key`: `SELECT topic_ids, keyword_ids FROM gathas WHERE natural_key = $1`, then translate UUIDs to `natural_key` via a small cached batch query.
2. **A/V chunks** (spec 18) and Jinswara Q/A (spec 19): ingest already populates `metadata.topic_nks` / `metadata.keyword_nks`, so no DB lookup is needed.

A per-request LRU cache (capacity 2k entries, TTL 600s) on `gatha_nk → (topic_nks, keyword_nks)` keeps the lookup amortised.

### Logging

Every request writes one `rag_query_logs` row. With `RAG_LOG_ASYNC=true` (default) the insert is fire-and-forget via `asyncio.create_task`; failures log but do not surface to the caller.

### `POST /v1/rag/search`

```http
POST /v1/rag/search
{
  "query": "द्रव्य के गुण और पर्याय में भेद",
  "top_k": 10,
  "lang": "hi",
  "caller": "cataloguesearch-chat"
}
```

Response: `SearchOut` (above). `reordered=true` when the top1 changed.

### `POST /v1/rag/explain`

Same input, additional response fields: `base_ranking`, `graph_context`, per-hit `components`. Used by the admin dashboard to debug a single query.

## Phase B — Observability dashboards (admin UI)

Three pages under `ui/app/admin/rag/`:

| Route | Backed by |
|---|---|
| `/admin/rag/no-graph-hits` | `GET /admin/rag/no-graph-hits?since=24h&caller=...&limit=50` |
| `/admin/rag/orphan-chunks` | `GET /admin/rag/orphan-chunks?shastra=...&limit=100` |
| `/admin/rag/topic-coverage` | `GET /admin/rag/topic-coverage?topic_nk=...` |

Admin endpoints live in `services/rag_enhancer_service/routers/admin.py`, gated by `require_role('admin')`.

### Endpoints

```
GET /admin/rag/no-graph-hits?since=24h&caller=cataloguesearch-chat&limit=50
  -> { "rows": [ {query_text, created_at, base_top1_chunk_id, latency_ms, ...} ],
       "total_no_graph_24h": int,
       "total_queries_24h":  int,
       "no_graph_ratio":     float }

GET /admin/rag/orphan-chunks?shastra=pravachansaar&limit=100
  -> { "rows": [{chunk_id, shastra_nk, topic_count, keyword_count, last_computed_at}],
       "total_orphans": int }

GET /admin/rag/topic-coverage?topic_nk=jainkosh:आत्मा
  -> { "topic_nk": str,
       "chunk_count": int,
       "chunks_sample": [...],
       "gatha_count":  int,
       "av_chunk_count": int }
```

### Coverage recompute job

`coverage.py: recompute_chunk_coverage()` runs hourly (Celery beat). Algorithm:

1. Page through `cataloguesearch /chunks?since=<last_run>` (or `/chunks/all` on first run).
2. For each chunk, resolve `(topic_nks, keyword_nks)` exactly as in the search path.
3. Upsert into `chunk_graph_coverage` keyed by `chunk_id`.
4. Persist `last_run_at` in a new `chunk_coverage_state` single-row table (added in same migration).

`POST /admin/rag/coverage/recompute` forces a full re-run.

### Expected upstream contract

```
GET {CATALOGUESEARCH_URL}/chunks?since=ISO8601&limit=500&cursor=...
  -> {"chunks":[{"chunk_id","shastra_natural_key","gatha_natural_key","metadata":{...}}],
      "next_cursor": str | null}
```

If this endpoint does not yet exist in cataloguesearch, the spec falls back to running coverage only against chunks observed in `rag_query_logs.base_ranking` (no full corpus walk). The UI surfaces "partial coverage" in that case.

## Tests (TDD — write these first)

1. `test_rerank_unit.py`: pure scoring math — exact overlap → score delta matches formula to 1e-9.
2. `test_rerank_orders_overlap.py`: 5 hits, 2 have topic overlap, 1 has both → ordering [both, topic, topic, none, none].
3. `test_no_graph_hit_passthrough.py`: empty `GraphContext` → response identical order to baseline, `reordered=false`.
4. `test_upstream_timeout_falls_back.py`: stub query-service 502 → passthrough, log row present with `graph_latency_ms=null`.
5. `test_logs_written.py`: one request → exactly one `rag_query_logs` row with both rankings.
6. `test_coverage_recompute.py`: seed 10 chunks (3 with no metadata, 7 with topic nks) → after recompute, 3 orphan rows queryable via `/orphan-chunks`.
7. `test_no_graph_hits_endpoint.py`: insert log rows with mix of empty/non-empty `graph_topic_nks` → `/admin/rag/no-graph-hits` returns only the empty ones.
8. `test_chunk_gatha_lookup_cached.py`: 50 hits sharing 10 gathas → exactly 1 batch Postgres query for the gathas lookup.

## Manual verification

```bash
# Bring up the stack
docker compose up -d postgres rag-enhancer-service query-service

# Drop-in chat search (cataloguesearch-chat-compatible call site)
curl -X POST http://localhost:8007/v1/rag/search \
  -H 'content-type: application/json' \
  -d '{"query":"पर्याय और गुण में क्या भेद है","top_k":10}' | jq

# Explain — see both rankings + components
curl -X POST http://localhost:8007/v1/rag/explain \
  -H 'content-type: application/json' \
  -d '{"query":"पर्याय और गुण में क्या भेद है","top_k":10}' | jq

# Trigger coverage recompute (admin-gated)
curl -X POST http://localhost:8007/admin/rag/coverage/recompute \
  -b cookies.txt

# Inspect orphans
curl 'http://localhost:8007/admin/rag/orphan-chunks?limit=20' -b cookies.txt | jq
```

## Definition of done

- [ ] Migration `0030_rag_observability.py` applies cleanly.
- [ ] All Phase A tests pass with mocked upstreams.
- [ ] One end-to-end test hits a docker-compose stub of cataloguesearch (or its real instance if available) and asserts p95 ≤ 500ms for the rerank path at 5 rps.
- [ ] `cataloguesearch-chat` config switched to point at `http://rag-enhancer:8007/v1/rag/search` for one canary route; baseline route preserved.
- [ ] Admin UI pages render at least one row each against seeded data.
- [ ] Hourly `recompute_chunk_coverage` Celery beat task green for 24h in staging.

## Implementation notes

_(to be filled in after merge)_
