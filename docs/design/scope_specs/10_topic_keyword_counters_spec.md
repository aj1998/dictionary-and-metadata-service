# 10 — Topic & Keyword Counters Spec

Scope context: [`scope/04_translation_enrichment_pipeline.md`](../../scope/04_translation_enrichment_pipeline.md) (Counters section). Per `09_open_questions.md` Q9, the v1 scope is `(keyword|topic) × (shastra | teeka | anuyoga | global)` — no per-author roll-up yet (cheap to add later).

Counters are the SAAR USP per design-tenet 5: every keyword / topic card and every reader popover renders mention counts, the ranker uses them as priors, and finetune dataset weighting reads from them. This spec defines storage, recompute scheduling, read API, and the UI chip component.

## Phase A — Schema

### Files

```
packages/jain_kb_common/db/postgres/
├── enums.py            # extend with counter_scope_kind
├── counters.py         # TopicCounter, KeywordCounter ORM models
└── upserts.py          # upsert_topic_counter, upsert_keyword_counter
```

### Migration `0022_counters.py`

```sql
CREATE TYPE counter_scope_kind AS ENUM ('global', 'shastra', 'anuyoga', 'teeka');

CREATE TABLE keyword_counters (
  id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  keyword_id             UUID NOT NULL REFERENCES keywords(id) ON DELETE CASCADE,
  scope_kind             counter_scope_kind NOT NULL,
  scope_id               UUID,                                 -- nullable for 'global'
  mentions_count         BIGINT NOT NULL DEFAULT 0,            -- sum of extraction_spans + gathas.keyword_ids hits
  distinct_gathas_count  INT    NOT NULL DEFAULT 0,
  approved_spans_count   INT    NOT NULL DEFAULT 0,            -- spans with status='approved'
  pending_spans_count    INT    NOT NULL DEFAULT 0,
  last_recomputed_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT uq_keyword_counter UNIQUE (keyword_id, scope_kind, scope_id),
  CONSTRAINT chk_scope_id_global CHECK (
    (scope_kind = 'global'  AND scope_id IS NULL) OR
    (scope_kind <> 'global' AND scope_id IS NOT NULL)
  )
);
CREATE INDEX idx_keyword_counters_scope ON keyword_counters(scope_kind, scope_id);
CREATE INDEX idx_keyword_counters_keyword ON keyword_counters(keyword_id);

CREATE TABLE topic_counters (
  id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  topic_id               UUID NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
  scope_kind             counter_scope_kind NOT NULL,
  scope_id               UUID,
  mentions_count         BIGINT NOT NULL DEFAULT 0,
  distinct_gathas_count  INT    NOT NULL DEFAULT 0,
  approved_spans_count   INT    NOT NULL DEFAULT 0,
  pending_spans_count    INT    NOT NULL DEFAULT 0,
  last_recomputed_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT uq_topic_counter UNIQUE (topic_id, scope_kind, scope_id),
  CONSTRAINT chk_scope_id_topic_global CHECK (
    (scope_kind = 'global'  AND scope_id IS NULL) OR
    (scope_kind <> 'global' AND scope_id IS NOT NULL)
  )
);
CREATE INDEX idx_topic_counters_scope ON topic_counters(scope_kind, scope_id);
CREATE INDEX idx_topic_counters_topic ON topic_counters(topic_id);

CREATE TABLE counter_recompute_state (
  id                  INT PRIMARY KEY DEFAULT 1 CHECK (id = 1),
  last_run_started_at TIMESTAMPTZ,
  last_run_finished_at TIMESTAMPTZ,
  last_run_status     TEXT,
  last_error          TEXT
);
```

Note: `scope_id` semantics —
- `scope_kind='shastra'` → `scope_id = shastras.id`
- `scope_kind='teeka'`   → `scope_id = teekas.id`
- `scope_kind='anuyoga'` → `scope_id = anuyogas.id`
- `scope_kind='global'`  → `scope_id IS NULL`

The check constraint enforces the global vs non-global pairing. We **don't** FK `scope_id` because the target table varies; integrity is enforced by the recompute job (which only writes valid pairs).

## Phase B — Recompute worker

### Files

```
workers/enrichment/
├── counters.py             # Celery tasks: recompute_global, recompute_for_scope, recompute_for_entity
└── tests/
    ├── fixtures/
    │   └── tiny_corpus.sql
    ├── test_recompute_global_matches_groundtruth.py
    ├── test_recompute_per_shastra.py
    ├── test_recompute_for_entity_after_approve.py
    └── test_idempotent_double_recompute.py
```

### Source of truth (SQL aggregations)

The counter values are derived (not authoritative) from three sources, in priority:
1. `extraction_spans` rows with `status='approved'` → primary mention count.
2. `gathas.keyword_ids` / `gathas.topic_ids` JSONB arrays → for legacy ingestion that didn't go through Stage A/B.
3. `topic_candidates` from chat enrichment (`archived/11_chat_enrichment_loop.md`) → counted as pending only, never approved.

### Keyword counter SQL (global)

```sql
INSERT INTO keyword_counters (keyword_id, scope_kind, scope_id,
                              mentions_count, distinct_gathas_count,
                              approved_spans_count, pending_spans_count,
                              last_recomputed_at)
SELECT
  k.id AS keyword_id,
  'global'::counter_scope_kind,
  NULL::uuid,
  COALESCE(span_stats.mentions, 0) + COALESCE(jsonb_stats.legacy_mentions, 0),
  COALESCE(GREATEST(span_stats.distinct_gathas, jsonb_stats.distinct_gathas), 0),
  COALESCE(span_stats.approved, 0),
  COALESCE(span_stats.pending, 0),
  now()
FROM keywords k
LEFT JOIN LATERAL (
  SELECT COUNT(*) FILTER (WHERE status='approved') AS mentions,
         COUNT(*) FILTER (WHERE status='approved') AS approved,
         COUNT(*) FILTER (WHERE status='pending')  AS pending,
         COUNT(DISTINCT gatha_id) FILTER (WHERE status='approved' AND gatha_id IS NOT NULL) AS distinct_gathas
  FROM extraction_spans es
  WHERE es.kind = 'keyword' AND es.entity_id = k.id
) span_stats ON true
LEFT JOIN LATERAL (
  SELECT COUNT(*) AS legacy_mentions, COUNT(DISTINCT g.id) AS distinct_gathas
  FROM gathas g
  WHERE g.keyword_ids @> jsonb_build_array(k.id::text)
) jsonb_stats ON true
ON CONFLICT (keyword_id, scope_kind, scope_id) DO UPDATE
SET mentions_count = EXCLUDED.mentions_count,
    distinct_gathas_count = EXCLUDED.distinct_gathas_count,
    approved_spans_count = EXCLUDED.approved_spans_count,
    pending_spans_count = EXCLUDED.pending_spans_count,
    last_recomputed_at = now();
```

### Per-shastra keyword counter SQL

```sql
INSERT INTO keyword_counters (keyword_id, scope_kind, scope_id, mentions_count, ...)
SELECT
  k.id, 'shastra', s.id,
  COUNT(es.id) FILTER (WHERE es.status='approved'),
  COUNT(DISTINCT es.gatha_id) FILTER (WHERE es.status='approved'),
  COUNT(es.id) FILTER (WHERE es.status='approved'),
  COUNT(es.id) FILTER (WHERE es.status='pending'),
  now()
FROM keywords k
CROSS JOIN shastras s
LEFT JOIN extraction_spans es ON es.entity_id = k.id AND es.kind='keyword'
LEFT JOIN gathas g ON es.gatha_id = g.id AND g.shastra_id = s.id
GROUP BY k.id, s.id
HAVING COUNT(es.id) > 0          -- skip empty pairs
ON CONFLICT (keyword_id, scope_kind, scope_id) DO UPDATE SET ...;
```

Per-anuyoga rolls through `shastra_anuyogas`. Per-teeka rolls through `gathas.teeka_mapping_doc_ids` (see `docs/design/03_data_model_mongo.md#5-teeka_gatha_mapping`) — for v1 we only count spans whose `mongo_collection='teeka_gatha_mapping'`.

Topic counters mirror keyword counters with `kind='topic'` and use `gathas.topic_ids`.

### Tasks

```python
# workers/enrichment/counters.py

@celery.task(name="enrichment.counters.recompute_global")
def recompute_global():
    """Full recompute. Runs nightly at 03:00 UTC and at the end of every enrichment run."""
    with pg.transaction() as tx:
        tx.execute(text(KEYWORD_GLOBAL_SQL))
        tx.execute(text(TOPIC_GLOBAL_SQL))
        tx.execute(text(KEYWORD_PER_SHASTRA_SQL))
        tx.execute(text(TOPIC_PER_SHASTRA_SQL))
        tx.execute(text(KEYWORD_PER_ANUYOGA_SQL))
        tx.execute(text(TOPIC_PER_ANUYOGA_SQL))
        tx.execute(text(KEYWORD_PER_TEEKA_SQL))
        tx.execute(text(TOPIC_PER_TEEKA_SQL))
        tx.execute(update(CounterRecomputeState).values(
            last_run_finished_at=func.now(), last_run_status='ok'))

@celery.task(name="enrichment.counters.recompute_for_entity")
def recompute_for_entity(*, entity_kind: str, entity_id: str):
    """Cheap path called after a single span approval. Updates only the rows
    affecting this entity (global + every shastra/anuyoga/teeka it appears in)."""
    # Same SQL but WHERE entity_id = :id.
    ...
```

Beat schedule:

```python
beat_schedule = {
    "counters-nightly": {
        "task": "enrichment.counters.recompute_global",
        "schedule": crontab(hour=3, minute=0),
    }
}
```

Triggered from extraction approval (`08_translation_pipeline_extraction_spec.md` §Phase C) via `counters_recompute.delay(...)` (cheap per-entity path).

### Tests (TDD)

1. `test_recompute_global_matches_groundtruth.py` — load `tiny_corpus.sql` with 3 keywords + 5 approved spans + 2 pending → `recompute_global()` → row counts match hand-computed values.
2. `test_recompute_per_shastra.py` — keyword `आत्मा` appears 4× in `samaysaar` (3 approved, 1 pending) and 2× in `pravachansaar` → two `keyword_counters` rows with correct splits.
3. `test_recompute_for_entity_after_approve.py` — approve a pending span → call `recompute_for_entity` → only the affected (entity, scope) rows are touched (`last_recomputed_at` changes; others remain stale).
4. `test_idempotent_double_recompute.py` — run global recompute twice → row count and `mentions_count` unchanged on second pass.
5. `test_legacy_jsonb_counts.py` — gatha with `keyword_ids=[<uuid>]` but no extraction_spans row → counter still includes it.
6. `test_scope_constraint_rejects_global_with_scope_id.py` — DDL CHECK blocks insertion of `('global', <uuid>)`.

## Phase C — Read API + UI chip

### Endpoints (added to `services/data_service/`)

```
GET /v1/keywords/{nk}/counters?scope=global|shastra|anuyoga|teeka&scope_nk=<nk>
GET /v1/topics/{nk}/counters?scope=...&scope_nk=...
GET /v1/keywords/{nk}/counters/breakdown
        # returns all (scope_kind, scope_nk) rows; useful for the keyword detail page
GET /v1/topics/{nk}/counters/breakdown

# Hot path inside reader popover; one batched call:
POST /v1/counters/batch
     body: { items: [{kind:'keyword'|'topic', nk:'...', scope_kind:'shastra', scope_nk:'...'}] }
     resp: { items: [{kind, nk, scope_kind, scope_nk,
                       mentions_count, distinct_gathas_count,
                       approved_spans_count, pending_spans_count,
                       last_recomputed_at}] }
```

### Pydantic response

```python
class CounterRow(BaseModel):
    kind: Literal['keyword','topic']
    natural_key: str
    scope_kind: Literal['global','shastra','anuyoga','teeka']
    scope_natural_key: str | None
    mentions_count: int
    distinct_gathas_count: int
    approved_spans_count: int
    pending_spans_count: int
    last_recomputed_at: datetime
```

### Caching

Response cached in Redis for `COUNTER_CACHE_TTL_S=300` (5 min) per `(kind, nk, scope_kind, scope_nk)` key. Invalidated explicitly by `recompute_for_entity` posting a Redis `DEL` on touched keys.

### UI counter-chip component

```
ui/components/CounterChip.tsx
ui/lib/counters/useCounters.ts        # batched fetcher with SWR-style cache
```

Visual contract:

```
[ आत्मा   4,217 mentions · 312 gathas ]
        ^small grey chip                ^right of keyword label
```

Tooltip on hover renders the breakdown table: `Global · Samaysaar · Pravachansaar · ...`. Pending-span count is shown in a muted secondary line only on admin sessions (`current_user_optional().role in {'admin','reviewer'}`).

Rendered wherever a keyword or topic surface appears: graph node label, shastra-reader popover, keyword detail page header, topic detail page header, and search-result rows.

## Manual verification

```bash
# 1. Apply migration
alembic upgrade head

# 2. Seed
psql -f workers/enrichment/tests/fixtures/tiny_corpus.sql

# 3. Run global recompute
celery -A workers call enrichment.counters.recompute_global

# 4. Inspect
psql -c "SELECT k.natural_key, c.scope_kind, c.scope_id, c.mentions_count
         FROM keyword_counters c JOIN keywords k ON c.keyword_id = k.id
         ORDER BY c.mentions_count DESC LIMIT 20;"

# 5. Read API
curl 'http://localhost:8001/v1/keywords/आत्मा/counters?scope=global'
curl 'http://localhost:8001/v1/keywords/आत्मा/counters/breakdown'

# 6. Batched fetch (UI hot path)
curl -X POST http://localhost:8001/v1/counters/batch \
  -H 'content-type: application/json' \
  -d '{"items":[{"kind":"keyword","nk":"आत्मा","scope_kind":"shastra","scope_nk":"samaysaar"}]}'

# 7. Approve a span (spec 08) and confirm per-entity refresh
curl -X POST http://localhost:8001/admin/extraction-spans/<id>/approve ...
sleep 5
psql -c "SELECT mentions_count, last_recomputed_at FROM keyword_counters WHERE ..."
```

## Definition of done

- [ ] Migration `0022_counters.py` applies clean.
- [ ] All 6 Phase-B tests pass.
- [ ] Nightly Celery beat job is scheduled and demoably writes one row to `counter_recompute_state`.
- [ ] Per-entity recompute path is invoked from `extraction-spans/approve` and observable in `last_recomputed_at`.
- [ ] `/v1/counters/batch` returns 200 in < 50 ms for 50-item batches on the demo dataset.
- [ ] CounterChip renders on the demo Graph page and Shastra reader popover.
- [ ] At least 100 keywords and 50 topics have non-zero counter rows in the demo dataset (matches `scope/04` DoD).

## Implementation notes

_(to be filled in after merge)_
