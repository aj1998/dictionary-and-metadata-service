# 11 — Topic Hierarchy (Stage C) Spec

Scope context: [`scope/04_translation_enrichment_pipeline.md`](../../scope/04_translation_enrichment_pipeline.md) (Stage C). Implements the third stage of the enrichment pipeline: for each newly approved topic, propose `IS_A | PART_OF | RELATED_TO` edges into the topic graph, run them through admin review, then apply approved edges into Neo4j with provenance.

Per `09_open_questions.md` Q10, AI proposals **coexist** with existing edges via `RELATED_TO` (soft) and never replace an admin-approved `IS_A`/`PART_OF` without explicit re-review.

Depends on: `08_translation_pipeline_extraction_spec.md` (provides approved candidate topics), `09_translation_pipeline_ai_flow_spec.md` (defines `hierarchy_proposal` task + schema), `04_data_model_graph.md` (edge types).

## Phase A — Candidate-generation worker

### Files

```
packages/jain_kb_common/db/postgres/
├── hierarchy.py             # ProposedTopicEdge ORM
└── upserts.py               # upsert_proposed_topic_edge(...)

packages/jain_kb_common/db/postgres/
└── vectors.py               # ensure_pgvector_extension; topic_embedding helpers

workers/enrichment/
├── hierarchy.py             # Celery tasks: enqueue_hierarchy, propose_for_topic
├── embeddings.py            # embed_topic_text -> 1024-dim float[]
└── tests/
    ├── test_neighbourhood_uses_pgvector.py
    ├── test_propose_emits_edges.py
    ├── test_clash_with_existing_edge.py
    ├── test_proposed_edges_dedupe.py
    └── test_skip_when_no_neighbours.py
```

### Migration `0023_topic_hierarchy.py`

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TYPE topic_edge_kind AS ENUM ('IS_A', 'PART_OF', 'RELATED_TO');

ALTER TABLE topics
  ADD COLUMN display_text_embedding vector(1024),
  ADD COLUMN embedding_model TEXT,
  ADD COLUMN embedding_updated_at TIMESTAMPTZ;

CREATE INDEX idx_topics_embedding_hnsw
  ON topics USING hnsw (display_text_embedding vector_cosine_ops);

CREATE TABLE proposed_topic_edges (
  id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id                  UUID NOT NULL REFERENCES enrichment_runs(id) ON DELETE CASCADE,
  child_topic_id          UUID NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
  parent_topic_id         UUID NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
  relation                topic_edge_kind NOT NULL,
  cosine_similarity       REAL,                          -- 0..1, from vector neighbourhood
  llm_confidence          extraction_confidence NOT NULL,
  llm_model               TEXT NOT NULL,
  llm_rationale           TEXT,
  clash_with_existing     BOOLEAN NOT NULL DEFAULT false,
                                                          -- true if existing IS_A/PART_OF disagrees
  clash_existing_edge_id  TEXT,                          -- Neo4j relationship elementId, for trace
  status                  candidate_status NOT NULL DEFAULT 'pending',
  reviewed_by             TEXT,
  reviewed_at             TIMESTAMPTZ,
  reject_reason           TEXT,
  applied_at              TIMESTAMPTZ,
  created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (child_topic_id <> parent_topic_id),
  CONSTRAINT uq_proposed_edge UNIQUE (child_topic_id, parent_topic_id, relation)
);
CREATE INDEX idx_proposed_topic_edges_status ON proposed_topic_edges(status);
CREATE INDEX idx_proposed_topic_edges_child ON proposed_topic_edges(child_topic_id);
```

### Worker flow

```python
# workers/enrichment/hierarchy.py

@celery.task(name="enrichment.hierarchy.enqueue")
def enqueue_hierarchy(*, scope_kind: str, scope_nk: str, triggered_by: str) -> str:
    run = create_enrichment_run(stage='C_hierarchy', ...)
    # Backlog: topics either freshly approved or with embedding_updated_at < topic.updated_at
    for topic_id in iter_topics_needing_hierarchy(scope_kind, scope_nk):
        propose_for_topic.delay(run_id=str(run.id), topic_id=str(topic_id))
    return str(run.id)

@celery.task(name="enrichment.hierarchy.propose_for_topic",
             autoretry_for=(LLMTransient,), retry_backoff=True, max_retries=5)
def propose_for_topic(*, run_id: str, topic_id: str):
    topic = pg.get_topic(topic_id)
    embedding = ensure_embedding(topic)
    neighbours = pg.fetch(text("""
        SELECT id, natural_key, display_text,
               (display_text_embedding <=> :emb) AS cosine_distance
        FROM topics
        WHERE id <> :id AND display_text_embedding IS NOT NULL
        ORDER BY display_text_embedding <=> :emb
        LIMIT :k
    """), emb=embedding, id=topic.id, k=30)

    if not neighbours:
        return {"proposed": 0, "reason": "no_neighbours"}

    result = call_hierarchy_proposer(topic, neighbours)  # spec 09
    for edge in result.proposed_edges:
        parent = pg.get_topic_by_natural_key(edge.parent_topic_natural_key)
        if parent is None or parent.id == topic.id:
            continue
        clash, clash_id = detect_clash(parent.id, topic.id, edge.relation)
        upsert_proposed_topic_edge(
            run_id=run_id, child_topic_id=topic.id, parent_topic_id=parent.id,
            relation=edge.relation,
            cosine_similarity=1.0 - neighbour_distance(parent.id, neighbours),
            llm_confidence=edge.confidence, llm_model=result.model,
            llm_rationale=edge.rationale,
            clash_with_existing=clash, clash_existing_edge_id=clash_id)
```

### Embeddings

```python
# workers/enrichment/embeddings.py
EMBED_MODEL = os.environ.get("HIERARCHY_EMBED_MODEL", "text-embedding-3-large")

def embed_topic_text(topic: Topic) -> list[float]:
    text = pick_hindi(topic.display_text)            # primary heading
    if topic.extract_doc_ids:
        # Append first 1500 chars of extract for richer signal
        text += "\n" + fetch_extract_excerpt(topic.extract_doc_ids[0], chars=1500)
    return openai_embed(text, model=EMBED_MODEL)     # 1024-dim
```

Embeddings are written into `topics.display_text_embedding` on every approval and reused on subsequent runs. Re-embedding triggers on `topics.updated_at > embedding_updated_at`.

### Clash detection (Q10)

```python
def detect_clash(parent_id: UUID, child_id: UUID, proposed: TopicEdgeKind) -> tuple[bool, str|None]:
    """Return (clash, existing_edge_neo4j_id).
    Clash conditions:
      - proposed in {IS_A, PART_OF} AND any existing IS_A/PART_OF from child to ANY other parent
        with source='manual' (admin-approved).
      - proposed in {IS_A, PART_OF} AND existing reverse edge (parent → child) of same kind.
    RELATED_TO never clashes (soft).
    """
```

Per Q10 default: clashing IS_A/PART_OF proposals are **downgraded** by the worker (not silently rejected) — the row is written with `relation='RELATED_TO'` and `clash_with_existing=true` so the admin sees the downgrade. The original proposed relation is preserved in `llm_rationale` (prefixed `[downgraded from IS_A] ...`).

### Tests (TDD)

1. `test_neighbourhood_uses_pgvector.py` — seed 50 topics with random embeddings + one target; the 30 nearest are returned ordered by cosine_distance ASC.
2. `test_propose_emits_edges.py` — stub LLM returns 2 `IS_A` proposals → 2 rows in `proposed_topic_edges` with cosine_similarity > 0.
3. `test_clash_with_existing_edge.py` — child already has admin-approved `IS_A` → new `IS_A` proposal lands as `RELATED_TO` with `clash_with_existing=true`.
4. `test_proposed_edges_dedupe.py` — same `(child, parent, relation)` proposed twice in different runs → UNIQUE constraint hits; second run UPDATEs the row with the newer rationale + run_id.
5. `test_skip_when_no_neighbours.py` — topic without embeddings in the corpus → task returns `proposed=0, reason='no_neighbours'`; no row written.
6. `test_embedding_refresh_on_topic_update.py` — touch `topics.updated_at` → next run recomputes embedding.

## Phase B — Admin review UI

### Files

```
services/data_service/routers/admin/
└── hierarchy_review.py            # list/approve/reject endpoints

ui/app/admin/hierarchy-review/
├── page.tsx                       # extends review-queue grid from 13_admin_ui.md
└── components/
    ├── ProposedEdgeCard.tsx       # renders child + parent + relation + cosine
    ├── ClashBanner.tsx            # shown when clash_with_existing=true
    └── TopicMiniGraph.tsx         # 1-hop visualization around the candidate
```

### Endpoints

```
GET    /admin/proposed-topic-edges?status=pending&run_id=...&clash_only=true
POST   /admin/proposed-topic-edges/{id}/approve
POST   /admin/proposed-topic-edges/{id}/reject  body: { reason: str }
POST   /admin/proposed-topic-edges/bulk-approve body: { ids: [str] }
GET    /admin/topics/{nk}/edges                  # for the mini-graph viz
```

Default UI sort: `clash_with_existing DESC, llm_confidence ASC, cosine_similarity DESC` — clashes surface first, then low-confidence, then strong matches.

### Approval algorithm

```python
async def approve_edge(edge_id: UUID, *, reviewer: str) -> None:
    async with pg.transaction() as tx:
        edge = await tx.scalar(select(ProposedTopicEdge).where(...).with_for_update())
        if edge.status != 'pending':
            raise Conflict(f"edge already {edge.status}")
        await tx.execute(update(ProposedTopicEdge)
            .where(ProposedTopicEdge.id == edge_id)
            .values(status='approved', reviewed_by=reviewer,
                    reviewed_at=func.now()))

    # post-commit: apply into Neo4j (Phase C)
    apply_proposed_edge.delay(edge_id=str(edge_id))
```

Rejection sets `status='rejected'` and never applies.

### UI behaviours

- **Mini-graph**: side-panel shows the child topic at the centre with 1-hop neighbours from `MATCH (c:Topic {natural_key:$nk})-[r]-(n) RETURN ...`. The proposed parent is rendered as a dashed edge.
- **Clash banner**: when `clash_with_existing=true`, banner text reads "Downgraded from IS_A → RELATED_TO because admin-approved IS_A exists to {existing parent}. [View existing edge]."
- **Bulk approve**: limited to rows with `llm_confidence='high' AND clash_with_existing=false` (UI disables the checkbox otherwise).

## Phase C — Graph apply

### Files

```
workers/enrichment/
└── hierarchy_apply.py        # apply_proposed_edge celery task
```

### Apply algorithm

```python
@celery.task(name="enrichment.hierarchy.apply", max_retries=3)
def apply_proposed_edge(*, edge_id: str):
    with pg.transaction() as tx:
        edge = pg.get(ProposedTopicEdge, edge_id, for_update=True)
        if edge.status != 'approved' or edge.applied_at is not None:
            return
        child = pg.get(Topic, edge.child_topic_id)
        parent = pg.get(Topic, edge.parent_topic_id)

        neo4j.run("""
            MATCH (c:Topic {natural_key:$child}), (p:Topic {natural_key:$parent})
            MERGE (c)-[r:%s]->(p)
            ON CREATE SET r.source = 'enrichment_ai',
                          r.proposed_edge_id = $eid,
                          r.weight = 1.0,
                          r.llm_confidence = $conf,
                          r.created_at = datetime()
            ON MATCH  SET r.source = coalesce(r.source, 'enrichment_ai'),
                          r.proposed_edge_id = $eid,
                          r.llm_confidence = $conf,
                          r.updated_at = datetime()
        """ % edge.relation.name,
            child=child.natural_key, parent=parent.natural_key,
            eid=str(edge.id), conf=edge.llm_confidence.value)

        pg.execute(update(ProposedTopicEdge).where(ProposedTopicEdge.id == edge.id)
                   .values(applied_at=func.now()))
```

### Provenance back-fill

Every Neo4j edge written through this path carries:
- `source = 'enrichment_ai'`
- `proposed_edge_id` — link back to the Postgres row for audit
- `llm_confidence`
- `weight = 1.0` (admin can adjust later via `/admin/topics/{nk}/edges/{rid}` PATCH)

When an admin **overrides** an AI edge (deletes via admin UI), the Postgres `proposed_topic_edges.status` flips to `rejected` with `reject_reason='admin_override_post_apply'` to preserve the audit trail.

### Tests (TDD)

1. `test_apply_writes_neo4j_edge.py` — approve an edge → Neo4j MATCH returns one edge of correct type with `source='enrichment_ai'`.
2. `test_apply_idempotent.py` — call `apply_proposed_edge` twice → Neo4j edge count for that pair = 1; `applied_at` not overwritten by second call.
3. `test_apply_only_when_approved.py` — pending edge → apply task no-ops.
4. `test_existing_admin_edge_not_overwritten.py` — pre-existing admin `IS_A` between same pair; apply RELATED_TO → both edges exist (different types) and admin edge retains `source='manual'`.
5. `test_clash_reverse_direction.py` — existing `parent → child IS_A`; propose `child → parent IS_A` → downgraded to RELATED_TO at propose time, applies cleanly.

## Manual verification

```bash
alembic upgrade head

# 1. Backfill embeddings for the existing topic corpus
python -m workers.enrichment.hierarchy backfill-embeddings --limit 500

# 2. Enqueue Stage C for an adhikaar
celery -A workers call enrichment.hierarchy.enqueue \
  scope_kind=adhikaar scope_nk=samaysaar:1 triggered_by=anu@local

# 3. Inspect proposals
psql -c "SELECT pe.relation, pe.llm_confidence, pe.cosine_similarity, pe.clash_with_existing,
                ct.natural_key AS child, pt.natural_key AS parent
         FROM proposed_topic_edges pe
         JOIN topics ct ON pe.child_topic_id=ct.id
         JOIN topics pt ON pe.parent_topic_id=pt.id
         WHERE pe.status='pending'
         ORDER BY clash_with_existing DESC LIMIT 30;"

# 4. Approve via admin API
curl -X POST http://localhost:8001/admin/proposed-topic-edges/<id>/approve \
  -H 'authorization: Bearer <admin>'

# 5. Verify in Neo4j
cypher-shell "MATCH (c:Topic {natural_key:'<child>'})-[r:RELATED_TO]->(p:Topic)
              RETURN r.source, r.proposed_edge_id, p.natural_key;"

# 6. Mini-graph render check
curl 'http://localhost:8001/admin/topics/<nk>/edges'
```

## Definition of done

- [ ] Migration `0023_topic_hierarchy.py` applies clean (pgvector enabled).
- [ ] Embeddings populated for all approved topics in the demo corpus.
- [ ] All 11 tests (6 Phase A + 5 Phase C) pass.
- [ ] Admin review UI surfaces proposals with clash banner where applicable.
- [ ] Approving a proposal writes a Neo4j edge with full provenance; rejecting does not.
- [ ] Stage C runs E2E on samaysaar adhikaar 1 with ≥ 20 proposed edges (mix of `IS_A`, `PART_OF`, `RELATED_TO`).
- [ ] Per Q10: existing admin-approved edges are never silently overwritten.

## Implementation notes

_(to be filled in after merge)_
