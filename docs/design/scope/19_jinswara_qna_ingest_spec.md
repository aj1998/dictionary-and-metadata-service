# 19 — Jinswara Q/A Ingestion Spec (verified-author Q/As as graph entities)

Scope context: [`scope/06_advanced_rag_and_finetuning.md`](../../scope/06_advanced_rag_and_finetuning.md) §Jinswara Q/A; Q14 default = admin-maintained allowlist `parser_configs/jinswara_authors.yaml`.

Jinswara is a Jain Q/A site. Verified-author Q/As become first-class entities: a Postgres row per Q/A, full text in Mongo, a `JinswaraQnA` node in Neo4j, and edges to `Author` / `Topic` / `Keyword`. The GraphRAG path (spec 17) surfaces them as citation tiles on the AI page; clicking the tile opens a deep link back to Jinswara.

## Expected upstream contract (black box)

Jinswara has no public structured API; this is a scrape. The HTML structure is captured in the parser config (Phase A). If Jinswara exposes a future JSON endpoint, swap the scraper for an API client — the rest of the pipeline is unchanged.

## Phase A — scraper + parser

### Files

```
workers/ingestion/jinswara/
├── __init__.py
├── celery_app.py
├── config.py              JINSWARA_* env (BASE_URL='https://jinswara.com',
│                          USER_AGENT, REQUEST_DELAY_S=2.0, MAX_PAGES_PER_RUN=500,
│                          RETRIES=2)
├── tasks.py               ingest_jinswara_pages(start_url=None, force_reingest=False)
├── scraper.py             httpx.AsyncClient wrapper + rate-limit bucket (Redis)
├── parser.py              parse_qna_page(html) -> ParsedQnA
├── apply.py               apply_parsed(qna) -> JinswaraQnA row (idempotent)
├── allowlist.py           load_verified_authors(); is_verified(author_handle)
└── tests/
    ├── conftest.py
    ├── fixtures/
    │   ├── page_valid_author.html
    │   ├── page_unverified_author.html
    │   ├── page_multilang_question.html
    │   └── page_no_answer.html
    ├── test_parse_question_answer.py
    ├── test_parse_multilang.py
    ├── test_allowlist_filter.py
    ├── test_idempotent_reingest.py
    └── test_apply_writes_pg_mongo.py

parser_configs/jinswara_authors.yaml
parser_configs/jinswara.yaml           selectors, multilang detection, url patterns
```

Shared models: `packages/jain_kb_common/db/postgres/jinswara.py`.

### `parser_configs/jinswara_authors.yaml`

```yaml
# Verified-author allowlist. Admin-curated. New entries require admin approval
# (the admin UI surface in spec 13 will manage this file via PR-style review).
verified_authors:
  - handle: "kanjisaheb"
    pg_author_natural_key: "kanjisaheb"
    display_name: "पूज्य कानजी स्वामी"
    jinswara_profile_url: "https://jinswara.com/author/kanjisaheb"
  - handle: "todarmalji"
    pg_author_natural_key: "panditji-todarmal"
    display_name: "पंडित टोडरमलजी"
    jinswara_profile_url: "https://jinswara.com/author/todarmalji"
```

Any author handle parsed from a page but not present here causes the QnA row to be written with `verified=false` and `status='pending'` (held back from public surfaces until an admin approves and either adds the author to the allowlist or rejects).

### Postgres schema (migration `0032_jinswara_qna.py`)

```sql
ALTER TYPE ingestion_source ADD VALUE IF NOT EXISTS 'jinswara';

CREATE TABLE jinswara_qna (
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  natural_key           TEXT NOT NULL UNIQUE,    -- 'jinswara:<sha1(source_url)[0:12]>'
  question_text         JSONB NOT NULL,          -- [{lang,script,text}]; multilingual
  answer_text_doc_id    TEXT NOT NULL,           -- Mongo _id stringified
  author_id             UUID REFERENCES authors(id) ON DELETE SET NULL,
  author_handle_raw     TEXT NOT NULL,           -- as parsed from page; never normalised
  source_url            TEXT NOT NULL UNIQUE,
  verified              BOOLEAN NOT NULL DEFAULT false,
  status                candidate_status NOT NULL DEFAULT 'pending',
  topic_ids             JSONB NOT NULL DEFAULT '[]'::jsonb,
  keyword_ids           JSONB NOT NULL DEFAULT '[]'::jsonb,
  ingestion_run_id      UUID REFERENCES ingestion_runs(id) ON DELETE SET NULL,
  reviewed_by           TEXT,
  reviewed_at           TIMESTAMPTZ,
  reject_reason         TEXT,
  created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_jinswara_qna_author    ON jinswara_qna(author_id);
CREATE INDEX idx_jinswara_qna_status    ON jinswara_qna(status);
CREATE INDEX idx_jinswara_qna_verified  ON jinswara_qna(verified) WHERE verified = true;
CREATE INDEX idx_jinswara_qna_topics    ON jinswara_qna USING gin (topic_ids   jsonb_path_ops);
CREATE INDEX idx_jinswara_qna_keywords  ON jinswara_qna USING gin (keyword_ids jsonb_path_ops);
```

### Mongo collection `jinswara_answers`

```json
{
  "_id": "<stable_id(qna_natural_key)>",
  "natural_key": "jinswara:<sha1>",
  "qna_natural_key": "jinswara:<sha1>",
  "question": [{"lang":"hin","script":"Deva","text":"…"},
               {"lang":"eng","script":"Latn","text":"…"}],
  "answer":   [{"lang":"hin","script":"Deva","text":"…"}],
  "raw_html":  "<html>…</html>",
  "source_url": "https://jinswara.com/q/…",
  "author_handle_raw": "kanjisaheb",
  "ingestion_run_id": "uuid",
  "created_at": ISODate(...),
  "updated_at": ISODate(...)
}
```

Indexes: `{natural_key:1}` UNIQUE; `{qna_natural_key:1}`.

### Pydantic contracts

```python
class ParsedQnA(BaseModel):
    source_url: HttpUrl
    author_handle_raw: str
    question: list[LangText]          # at least one entry, lang in {hin, eng}
    answer:   list[LangText]
    raw_html: str

class LangText(BaseModel):
    lang: Literal['hin','eng','san','pra']
    script: Literal['Deva','Latn']
    text: constr(min_length=1)
```

### Scraper rules

- Respect `robots.txt` (fetch and cache for 24h; skip disallowed paths).
- `REQUEST_DELAY_S` minimum between requests to a single host.
- Per `ingestion_runs` row, persist `iterator_state` = `{"last_url": str, "remaining_seeds": [...]}` so the run resumes cleanly after a crash.
- Store full raw HTML in `raw_html_snapshots` (existing collection in Mongo) for re-parse without re-scrape.

### `apply_parsed(qna)` algorithm

```
1. nk = f"jinswara:{sha1(qna.source_url)[0:12]}"
2. mongo_id = upsert_jinswara_answer(natural_key=nk, doc=...)
3. resolve author:
     verified = is_verified(qna.author_handle_raw)
     author_id = (lookup authors.natural_key from allowlist mapping, or NULL if not verified)
4. UPSERT jinswara_qna (natural_key) values (
     question_text=qna.question, answer_text_doc_id=str(mongo_id),
     author_id=author_id, author_handle_raw=qna.author_handle_raw,
     source_url=qna.source_url, verified=verified,
     status = 'approved' if verified else 'pending'
   )
5. If verified: enqueue enrichment.enrich_jinswara_qna(qna_id).
   If not verified: write an ingestion_review_queue row (entity_type='jinswara_qna',
     proposed_payload={qna_row, mongo_doc}); admin can approve/reject.
```

`status='approved'` for verified-author Q/As skips admin review per Q14 default (allowlist *is* the verification).

## Phase B — enrichment + graph mirror

### Files (added)

```
workers/enrichment/jinswara_qna_enrichment.py
    enrich_jinswara_qna(qna_id: UUID)
        - load question+answer text (concatenated, language='hi' primary)
        - call extract_keywords_and_topics(...) (same pipeline as gathas)
        - resolve to UUIDs; create candidates for unknowns via ingestion_review_queue
        - update jinswara_qna.topic_ids / keyword_ids
        - call graph_sync.sync_jinswara_qna(...)
        - trigger counter recompute for affected topic/keyword IDs
```

### Neo4j extension

New node label and constraints:

```cypher
CREATE CONSTRAINT jinswara_qna_natural_key IF NOT EXISTS
  FOR (n:JinswaraQnA) REQUIRE n.natural_key IS UNIQUE;
CREATE INDEX jinswara_qna_pg_id IF NOT EXISTS FOR (n:JinswaraQnA) ON (n.pg_id);
```

Node properties:

```
JinswaraQnA { natural_key, pg_id, source_url, question_hi, verified,
              created_at, updated_at }
```

Edges (added to `parser_configs/_meta/edge_types.yaml`):

| Type | From → To | Properties | Meaning |
|---|---|---|---|
| `ANSWERS`           | `Author → JinswaraQnA`         | `source='jinswara'`          | Author wrote this answer. |
| `MENTIONS_TOPIC`    | `JinswaraQnA → Topic`          | `weight`, `source='jinswara'` | Enrichment-tagged topics. |
| `MENTIONS_KEYWORD`  | `JinswaraQnA → Keyword`        | `weight`, `source='jinswara'` | Enrichment-tagged keywords. |

Reverse `MENTIONS_TOPIC` traversal already exists in the GraphRAG pipeline (`12_query_engine.md` stage 4) — the new node label flows in without query changes, because the traversal matches by edge type, not node label.

### `sync_jinswara_qna` upsert (Cypher, idempotent)

```cypher
MERGE (q:JinswaraQnA {natural_key: $nk})
SET q.pg_id = $pg_id, q.source_url = $url,
    q.question_hi = $question_hi, q.verified = $verified,
    q.updated_at = datetime()
ON CREATE SET q.created_at = datetime()
WITH q
OPTIONAL MATCH (a:Author {natural_key: $author_nk})
FOREACH (_ IN CASE WHEN a IS NULL THEN [] ELSE [1] END |
  MERGE (a)-[r:ANSWERS]->(q) SET r.source = 'jinswara'
);
```

Topic/keyword edges follow the same pattern as `sync_topic` in `04_data_model_graph.md`.

### GraphRAG response: new mention kind

Extend `mentions[]` (same approach as spec 18):

```json
{"kind": "jinswara_qna",
 "qna_natural_key": "jinswara:abc123",
 "source_url": "https://jinswara.com/q/...",
 "author_natural_key": "kanjisaheb",
 "author_display": "पूज्य कानजी स्वामी",
 "question_hi": "...",
 "answer_excerpt_hi": "..."}
```

`answer_excerpt_hi` is the first 280 chars of the Hindi answer text. Hydration fetches it from `jinswara_answers` in the same batched Mongo call already issued in stage 6 (`hydrate_topic_extracts_hi` is extended with an optional `extra_collections` parameter, or a parallel `hydrate_jinswara_excerpts` helper is added — pick whichever keeps round-trip count constant).

## Phase C — AI page integration

```
ui/src/components/citations/JinswaraCitationTile.tsx
    Props: { qna_natural_key, source_url, author_display, question_hi, answer_excerpt_hi }
    Renders:
      - top line: badge "Jinswara · {author_display}"
      - question (bold, 2-line clamp)
      - answer excerpt (4-line clamp)
      - footer: external-link icon -> source_url (target=_blank rel="noreferrer")
```

The chat answer renderer (already mounted from `cataloguesearch-chat`) picks this component when `citation.kind === 'jinswara_qna'`. No backend changes beyond Phase B.

## Admin surface (additive, optional in this spec)

- `GET /admin/jinswara/pending` — paged list of `jinswara_qna` rows with `status='pending'`.
- `POST /admin/jinswara/{id}/approve` — flips `verified=true` (if author handle is now in allowlist) **or** sets `status='approved'` for one-off acceptance.
- `POST /admin/jinswara/{id}/reject` — `status='rejected'`, store `reject_reason`.

These endpoints live in `services/metadata_service/routers/admin_jinswara.py` (no new service needed). Gated by `require_role('admin')`.

## Tests (TDD — write these first)

1. `test_parse_question_answer.py`: fixture HTML → `ParsedQnA` with correct question + answer text.
2. `test_parse_multilang.py`: fixture with `<div lang="en">` blocks → both Hindi and English `LangText` entries.
3. `test_allowlist_filter.py`: handle present in YAML → verified; unknown handle → not verified.
4. `test_apply_writes_pg_mongo.py`: end-to-end on one fixture → row in `jinswara_qna`, doc in `jinswara_answers`, stable `_id`.
5. `test_idempotent_reingest.py`: parse + apply twice → identical row count, `updated_at` advances, `created_at` does not.
6. `test_unverified_goes_to_review_queue.py`: unknown handle → row inserted with `verified=false`, exactly one `ingestion_review_queue` row created.
7. `test_robots_disallow_skips_url.py`: stub robots.txt disallowing a path → that path is not fetched.
8. `test_rate_limit.py`: 3 sequential fetches → at least `2 * REQUEST_DELAY_S` elapsed.
9. `test_enrichment_tags_qna.py`: stub extraction returning topics/keywords → row populated; graph_sync called once.
10. `test_graph_sync_creates_qna_node.py`: Neo4j testcontainer (or mock) → `JinswaraQnA` node + `ANSWERS` edge + tag edges.
11. `test_admin_approve_flow.py`: pending row → admin POSTs approve → status flips, graph sync invoked.

## Manual verification

```bash
# Seed the allowlist (edit parser_configs/jinswara_authors.yaml)

# Trigger ingestion
celery -A workers.ingestion.jinswara.celery_app call jinswara.ingest \
  --args='[null,false]'

# Inspect
psql "$DATABASE_URL" -c "
  SELECT id, verified, status, author_handle_raw, source_url
  FROM jinswara_qna ORDER BY created_at DESC LIMIT 5;
"

# Force enrichment on one Q/A
celery -A workers.enrichment.celery_app call enrichment.enrich_jinswara_qna \
  --args='[\"<QNA_UUID>\"]'

# GraphRAG should now return a jinswara_qna mention for a relevant topic
curl -X POST http://localhost:8004/v1/query/graphrag \
  -H 'content-type: application/json' \
  -d '{"tokens":["आत्मा"],"top_k":5,"include_extracts":false}' \
  | jq '.topics[].mentions[] | select(.kind=="jinswara_qna")'

# Admin approves a pending row
curl -X POST http://localhost:8001/admin/jinswara/<QNA_UUID>/approve \
  -b cookies.txt
```

## Definition of done

- [ ] Migration `0032_jinswara_qna.py` applies cleanly; `ingestion_source` enum extended.
- [ ] All Phase A–B tests pass with HTML fixtures.
- [ ] End-to-end: ingest ≥ 2 verified authors (per `06` Definition of Done), get ≥ 20 rows in `jinswara_qna` with `verified=true`, enrichment tags ≥ 80% of them with at least one topic.
- [ ] GraphRAG returns `jinswara_qna` mentions for at least one seed-keyword query.
- [ ] AI page renders the citation tile with a working external link.
- [ ] Re-running ingestion produces zero new rows and zero new Mongo docs.
- [ ] Unverified authors land in `ingestion_review_queue`; admin approve/reject flow round-trips.

## Implementation notes

_(to be filled in after merge)_
