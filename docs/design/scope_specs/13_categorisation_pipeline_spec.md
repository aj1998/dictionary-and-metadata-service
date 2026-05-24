# 13 — Categorisation Pipeline Spec

Scope context: [`scope/04_translation_enrichment_pipeline.md`](../../scope/04_translation_enrichment_pipeline.md) (Categorisation section). Depends on the LLM router + audit table from [`09_translation_pipeline_ai_flow_spec.md`](./09_translation_pipeline_ai_flow_spec.md) and the graph node taxonomy in [`docs/design/04_data_model_graph.md`](../data_model/04_data_model_graph.md) (specifically the `CATEGORISED_AS` edge already reserved there).

Auto-categorises every content unit (shastra / adhikaar / gatha / paragraph / teeka chunk) into the **four anuyoga** branches and their sub-categories used across Jain research:

- `dravyānuyoga` — sub: jiva, ajiva, karma, gunasthana, dravya, paryaya, ...
- `karanānuyoga` — sub: loka, jyotish, ganita, samay, ...
- `charanānuyoga` — sub: shravakāchār, munidharma, vrata, samiti, gupti, ...
- `prathamānuyoga` — sub: katha, charitra, purana, tirthankara, ...

A single LLM call per unit returns one or more `(category_slug, confidence)` tuples. Multi-label is the norm: a single paragraph commonly hits both `dravyānuyoga/jiva` and `charanānuyoga/vrata`. Reviewer approvals promote AI proposals into the canonical `content_category_links` table; rejections land in an audit trail. Approved links emit `CATEGORISED_AS` edges in the graph.

This is intentionally a **single-phase** spec — the schema, worker, review flow, and read API are tight enough to land together.

## Module paths

```
workers/categorisation_worker/
├── __init__.py
├── main.py                   # Celery task entrypoints
├── prompts.py                # imports prompts/categorisation.md
├── resolver.py               # slug → research_categories.id resolver + cache
├── tests/
│   ├── conftest.py
│   ├── fixtures/
│   │   ├── tiny_paragraph_set.json
│   │   └── golden_categories.json
│   ├── test_schema_migration.py
│   ├── test_single_paragraph_categorisation.py
│   ├── test_multi_label_handling.py
│   ├── test_confidence_threshold_drops_low.py
│   └── test_reviewer_approval_flow.py

services/data-service/app/routers/
└── categories.py             # public + admin endpoints

packages/jain_kb_common/db/postgres/
├── enums.py                  # extend with category_source
└── categories.py             # ORM models

packages/jain_kb_common/llm/prompts/
└── categorisation.md         # exact prompt template
```

## Postgres schema (migration `0030_categorisation.py`)

```sql
CREATE TYPE category_source AS ENUM ('ai', 'manual');

CREATE TYPE category_link_status AS ENUM ('pending', 'approved', 'rejected');

CREATE TABLE research_categories (
  id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  parent_id          UUID REFERENCES research_categories(id) ON DELETE RESTRICT,
  slug               TEXT NOT NULL UNIQUE,                 -- e.g. 'dravyanuyoga.jiva'
  label_multilingual JSONB NOT NULL,                       -- [{lang, script, text, transliteration?}]
  description_multilingual JSONB NOT NULL DEFAULT '[]'::jsonb,
  is_leaf            BOOLEAN NOT NULL DEFAULT false,
  sort_order         INT NOT NULL DEFAULT 0,
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_research_categories_parent ON research_categories(parent_id);

CREATE TABLE content_category_links (
  id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  content_ref_type   TEXT NOT NULL,                        -- 'shastra' | 'adhikaar' | 'gatha' | 'paragraph' | 'teeka_chunk'
  content_ref_id     UUID NOT NULL,                        -- soft FK; integrity enforced by worker
  category_id        UUID NOT NULL REFERENCES research_categories(id) ON DELETE CASCADE,
  confidence         NUMERIC(4, 3) NOT NULL CHECK (confidence BETWEEN 0 AND 1),
  source             category_source NOT NULL,
  status             category_link_status NOT NULL DEFAULT 'pending',
  llm_call_id        UUID REFERENCES llm_calls(id) ON DELETE SET NULL,
  approved_by        UUID,                                 -- users.id (auth-service)
  approved_at        TIMESTAMPTZ,
  reject_reason      TEXT,
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT uq_content_category UNIQUE (content_ref_type, content_ref_id, category_id, source)
);
CREATE INDEX idx_cclinks_content ON content_category_links(content_ref_type, content_ref_id);
CREATE INDEX idx_cclinks_category ON content_category_links(category_id);
CREATE INDEX idx_cclinks_status ON content_category_links(status) WHERE status <> 'approved';

CREATE TABLE pending_category_proposals (
  id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  link_id            UUID NOT NULL REFERENCES content_category_links(id) ON DELETE CASCADE,
  rationale          TEXT,                                 -- LLM-supplied justification
  alt_candidates     JSONB NOT NULL DEFAULT '[]'::jsonb,   -- [{slug, confidence, rationale}]
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT uq_pending_proposal UNIQUE (link_id)
);
```

Seed migration `0031_seed_research_categories.py` inserts the four anuyoga root rows plus the sub-categories enumerated above (idempotent upsert by `slug`).

## Pydantic contracts

```python
# packages/jain_kb_common/db/postgres/categories.py

class CategoryProposal(BaseModel):
    slug: str                                  # 'dravyanuyoga.jiva'
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str = Field(max_length=300)

class CategorisationResponse(BaseModel):
    proposals: list[CategoryProposal]          # may be empty

class CategoryLinkOut(BaseModel):
    id: UUID
    content_ref_type: Literal['shastra','adhikaar','gatha','paragraph','teeka_chunk']
    content_ref_id: UUID
    category_slug: str
    category_label: list[dict]                 # multilingual label
    confidence: float
    source: Literal['ai','manual']
    status: Literal['pending','approved','rejected']
    rationale: str | None
    alt_candidates: list[dict] = []
```

## LLM prompt (`packages/jain_kb_common/llm/prompts/categorisation.md`)

Reuses the cached `_system_jain_context.md` block from spec 09. The categorisation user prompt:

```
TASK: Assign the content unit below to one or more research categories.

CATEGORY_TAXONOMY (slugs and labels):
{{taxonomy_jsonl}}     # one row per line: {"slug": "...", "label_hi": "...", "leaf": true}

CONTENT_TYPE: {{content_ref_type}}
CONTENT_TEXT (NFC, target_lang=hin):
'''
{{content_text}}
'''

Rules:
- Output only leaf categories (where leaf=true).
- Emit between 1 and 4 proposals. Multi-label is encouraged when the text
  spans more than one anuyoga branch.
- confidence reflects strength of match: >=0.9 only when the text explicitly
  invokes the category's central concept; 0.6-0.9 for clear thematic match;
  <0.6 for weak inference (these will be auto-dropped).
- Do not invent new slugs. If nothing fits, return an empty `proposals` array.
```

Task is registered as `llm_task='categorisation'` in `llm_calls`. Budget: input ≤ 4K tokens (≤ 2K content + ≤ 2K taxonomy), output ≤ 500 tokens. Default model: `claude-haiku-4-5` (overridable via `LLM_DEFAULT_MODEL_CATEGORISATION`).

## Worker

```python
# workers/categorisation_worker/main.py

CONFIDENCE_THRESHOLD = float(os.getenv("CATEGORISATION_MIN_CONFIDENCE", "0.6"))

@celery.task(name="categorisation.categorise_unit", bind=True,
             autoretry_for=(LLMTransient,), retry_backoff=True, max_retries=5)
def categorise_unit(self, *, content_ref_type: str, content_ref_id: str,
                    triggered_by: str) -> dict:
    text = load_content_text(content_ref_type, content_ref_id)
    taxonomy = load_leaf_taxonomy_jsonl()
    client = pick_provider(task='categorisation')
    result = await client.call_json(
        system=cached_system_blocks(),
        messages=[user_msg(prompt='categorisation', content_text=text,
                            content_ref_type=content_ref_type,
                            taxonomy_jsonl=taxonomy)],
        response_schema=CategorisationResponse.model_json_schema(),
        max_tokens=500, task='categorisation', caller='categorisation.categorise_unit')
    parsed = CategorisationResponse.model_validate(result.parsed)
    return persist_proposals(content_ref_type, content_ref_id, parsed,
                              llm_call_id=result.llm_call_id)

@celery.task(name="categorisation.bulk_categorise")
def bulk_categorise(*, scope_kind: str, scope_nk: str, content_ref_type: str):
    for ref_id in iter_content_refs(scope_kind, scope_nk, content_ref_type):
        categorise_unit.delay(content_ref_type=content_ref_type,
                               content_ref_id=str(ref_id),
                               triggered_by='bulk_categorise')
```

`persist_proposals`:

1. Resolves each `slug` to `research_categories.id` (LRU-cached). Unknown slug → log + skip.
2. Drops proposals with `confidence < CONFIDENCE_THRESHOLD`.
3. Upserts a row in `content_category_links` with `source='ai', status='pending'`.
4. Inserts a row in `pending_category_proposals` with the rationale + the dropped alts.
5. Idempotent: the `uq_content_category` UNIQUE means a re-run is a no-op (except `updated_at`).

## Endpoints (`services/data-service/app/routers/categories.py`)

```
GET    /v1/categories                         # tree, multilingual labels
GET    /v1/categories/{slug}                  # detail + counts
GET    /v1/content/{type}/{id}/categories     # approved links only
GET    /admin/categories/proposals?status=pending&page=...
POST   /admin/categories/proposals/{id}/approve
       body: { reviewer_note?: str }
POST   /admin/categories/proposals/{id}/reject
       body: { reason: str }
POST   /admin/categories/proposals/bulk-approve
       body: { ids: [str] }
POST   /admin/content/{type}/{id}/categories  # manual add by reviewer
       body: { slug: str }
```

Endpoints under `/admin/...` are gated by `require_role('reviewer','admin')` from spec 01.

### Approval algorithm

```python
async def approve_proposal(link_id: UUID, *, reviewer_id: UUID) -> None:
    async with pg.transaction() as tx:
        link = await get_link(tx, link_id)
        if link.status != 'pending':
            raise HTTPException(409, "already finalised")
        await tx.execute(update(ContentCategoryLink).where(
            ContentCategoryLink.id == link_id).values(
                status='approved', approved_by=reviewer_id, approved_at=func.now()))
        await tx.execute(delete(PendingCategoryProposal).where(
            PendingCategoryProposal.link_id == link_id))
    # Post-commit fan-out
    graph_sync_categorised_as.delay(link_id=str(link_id))
    counters_recompute.delay(scope='global', entity_kind='category',
                              entity_id=str(link.category_id))
```

`graph_sync_categorised_as` writes the `(:Content)-[:CATEGORISED_AS {confidence, source}]->(:ResearchCategory)` edge defined in `04_data_model_graph.md`.

## Tests (TDD — write these first)

1. `test_schema_migration.py` — applying `0030_categorisation.py` creates all four tables and types; rolling back drops them cleanly; `uq_content_category` blocks a duplicate insert.
2. `test_single_paragraph_categorisation.py` — fixture paragraph about `jiva` → stubbed LLM returns `[{slug:'dravyanuyoga.jiva', confidence:0.92}]` → one row in `content_category_links` (status=pending), one row in `pending_category_proposals` with rationale captured.
3. `test_multi_label_handling.py` — fixture about a `shravak` performing `vrata` → LLM returns two proposals (`charananuyoga.vrata` 0.88, `dravyanuyoga.jiva` 0.71) → both rows persist; `alt_candidates` empty (both above threshold).
4. `test_confidence_threshold_drops_low.py` — LLM returns one proposal at 0.55 (below `CATEGORISATION_MIN_CONFIDENCE=0.6`) → no row in `content_category_links`; the dropped proposal lands in `alt_candidates` of any sibling above threshold, or is logged + discarded if none survive.
5. `test_reviewer_approval_flow.py` — pending link → POST approve → status flips to `approved`, `pending_category_proposals` row removed, `graph_sync_categorised_as` task enqueued (assert via mock).
6. `test_idempotent_double_run.py` — run `categorise_unit` twice on the same paragraph → row count unchanged, `updated_at` advances.
7. `test_admin_endpoint_role_gate.py` — guest gets 401, `user` gets 403, `reviewer` gets 200.

## Manual verification

```bash
# 1. Apply migrations + seed taxonomy
alembic upgrade head
python -m workers.categorisation_worker.main seed-taxonomy

# 2. Categorise a single gatha
celery -A workers call categorisation.categorise_unit \
  --kwargs '{"content_ref_type":"gatha","content_ref_id":"<uuid>","triggered_by":"anu@local"}'

# 3. Inspect pending proposals
psql -c "SELECT l.id, rc.slug, l.confidence, p.rationale
         FROM content_category_links l
         JOIN research_categories rc ON rc.id = l.category_id
         LEFT JOIN pending_category_proposals p ON p.link_id = l.id
         WHERE l.status='pending' ORDER BY l.created_at DESC LIMIT 20;"

# 4. Approve one
curl -X POST http://localhost:8001/admin/categories/proposals/<id>/approve \
  -H 'authorization: Bearer <reviewer_jwt>' -d '{}'

# 5. Verify graph edge
cypher-shell "MATCH (c)-[r:CATEGORISED_AS]->(rc:ResearchCategory {slug:'dravyanuyoga.jiva'})
              RETURN c.natural_key, r.confidence LIMIT 10;"

# 6. Bulk categorise an adhikaar
celery -A workers call categorisation.bulk_categorise \
  --kwargs '{"scope_kind":"adhikaar","scope_nk":"samaysaar:1","content_ref_type":"gatha"}'

# 7. Read API
curl 'http://localhost:8001/v1/content/gatha/<uuid>/categories'
curl 'http://localhost:8001/v1/categories/dravyanuyoga.jiva'
```

## Definition of done

- [ ] Migrations `0030_categorisation.py` and `0031_seed_research_categories.py` apply clean.
- [ ] All 7 tests pass.
- [ ] LLM prompt `categorisation.md` committed and reuses cached system block.
- [ ] One adhikaar bulk-categorisation produces ≥ 30 pending proposals on the demo dataset.
- [ ] Reviewer approval emits a `CATEGORISED_AS` edge visible via Cypher.
- [ ] Admin endpoints gated by reviewer/admin role.

## Implementation notes

_(to be filled in after merge)_
