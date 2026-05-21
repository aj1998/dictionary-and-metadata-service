# 14 — Vitrag Dictionary Ingest Spec

Scope context: [`scope/04_translation_enrichment_pipeline.md`](../../scope/04_translation_enrichment_pipeline.md) (Constrained vocabulary section) and [`scope/05_multilingual_strategy.md`](../../scope/05_multilingual_strategy.md). The Vitrag e-library publishes a curated Hindi↔English dictionary of Jain technical vocabulary — exactly the constrained list spec 08 (Stage B keyword extraction) consumes via the `vitrag_en_candidate` field. This spec defines how that dictionary lands in our Postgres, gets reviewed, and is published as the canonical `vitrag_dict` table that downstream pipelines read.

Three phases:

- **Phase A** — scrape + parse from `vitrag-elibrary` HTML into `vitrag_dict_raw`.
- **Phase B** — reviewer interface for promoting raw rows into curated entries.
- **Phase C** — publish to canonical `vitrag_dict`; expose read endpoints; cross-link from extraction spans.

## Module paths

```
workers/vitrag_dict_scraper/
├── __init__.py
├── main.py                       # Celery task entrypoints
├── fetcher.py                    # rate-limited HTTP fetch + retry
├── parser.py                     # HTML → VitragRawEntry
├── tests/
│   ├── conftest.py
│   ├── fixtures/
│   │   ├── sample_page.html
│   │   ├── golden_parsed.json
│   │   └── collisions.html
│   ├── test_rate_limiting.py
│   ├── test_parse_golden_fixture.py
│   ├── test_dedupe_hi_term_collisions.py
│   └── test_reviewer_approval_atomicity.py

services/metadata-service/app/routers/
└── vitrag_dict.py                # public search + admin endpoints

packages/jain_kb_common/db/postgres/
├── enums.py                      # extend with vitrag_dict_status
└── vitrag.py                     # ORM models + upserts
```

## Phase A — Scraper + parser

### Postgres schema (migration `0032_vitrag_dict_raw.py`)

```sql
CREATE TABLE vitrag_dict_raw (
  id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  source_url         TEXT NOT NULL,
  source_etag        TEXT,
  hi_term            TEXT NOT NULL,                  -- NFC-normalised Devanagari
  en_term            TEXT,                           -- nullable when source omits
  definitions        JSONB NOT NULL DEFAULT '[]'::jsonb,
                                                    -- [{lang, text, example?, pos?}]
  pos_hint           TEXT,
  raw_html           TEXT NOT NULL,                  -- exact <entry> fragment
  raw_text           TEXT NOT NULL,                  -- text-only fallback
  content_hash       TEXT NOT NULL,                  -- sha256(raw_html), for change detection
  scraped_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT uq_vitrag_raw UNIQUE (source_url, content_hash)
);
CREATE INDEX idx_vitrag_raw_hi ON vitrag_dict_raw(hi_term);
CREATE INDEX idx_vitrag_raw_scraped ON vitrag_dict_raw(scraped_at DESC);
```

### Fetcher contract

```python
# workers/vitrag_dict_scraper/fetcher.py
class VitragFetcher:
    base_url: str = os.environ['VITRAG_BASE_URL']
    rate_limit_qps: float = float(os.getenv('VITRAG_QPS', '0.5'))      # 1 req / 2s default
    user_agent: str = "JinvaniSAAR/1.0 (+https://saar.example/bot)"

    async def list_entry_urls(self) -> AsyncIterator[str]: ...
    async def fetch(self, url: str) -> FetchedPage:
        # uses asyncio.Semaphore + token-bucket; raises RateLimited on 429
        # respects ETag/If-Modified-Since; returns 304 → cached
```

Rate-limiting is enforced by an in-process token bucket (`aiolimiter`) **and** a Redis-backed semaphore so multiple Celery workers don't trample the source. Backoff on `429/503`: exponential with jitter, max 5 attempts.

### Parser

```python
# workers/vitrag_dict_scraper/parser.py
class VitragRawEntry(BaseModel):
    hi_term: str                    # NFC
    en_term: str | None
    definitions: list[Definition]
    pos_hint: str | None
    raw_html: str
    raw_text: str

def parse_page(html: str, source_url: str) -> list[VitragRawEntry]: ...
```

Parser uses `selectolax` (fast) with a `BeautifulSoup` fallback. The exact CSS selectors and field-extraction logic are encoded against the golden fixture and frozen by the test in Phase A.

### Celery tasks

```python
# workers/vitrag_dict_scraper/main.py

@celery.task(name="vitrag.scrape_all", bind=True)
def scrape_all(self, *, force_refresh: bool = False) -> dict:
    fetcher = VitragFetcher()
    n, dup = 0, 0
    async for url in fetcher.list_entry_urls():
        page = await fetcher.fetch(url)
        if page.status == 304 and not force_refresh:
            continue
        for entry in parse_page(page.html, source_url=url):
            n += 1
            stmt = pg_insert(VitragDictRaw).values(
                source_url=url, hi_term=nfc(entry.hi_term), en_term=entry.en_term,
                definitions=[d.model_dump() for d in entry.definitions],
                pos_hint=entry.pos_hint, raw_html=entry.raw_html,
                raw_text=entry.raw_text,
                content_hash=sha256(entry.raw_html),
            ).on_conflict_do_nothing(index_elements=['source_url','content_hash'])
            res = await pg.execute(stmt)
            if res.rowcount == 0:
                dup += 1
    return {"entries": n, "duplicates": dup}
```

### Phase A tests (TDD)

1. `test_rate_limiting.py` — fire 20 fetches against a stub server with `VITRAG_QPS=2.0`; assert total wall-time ≥ 9 s and all 20 succeed (no client-side throttle errors).
2. `test_parse_golden_fixture.py` — `parse_page(open('sample_page.html').read(), 'http://x/y')` returns the exact list in `golden_parsed.json` (round-trip JSON compare).

## Phase B — Reviewer flow

### Postgres schema (migration `0033_vitrag_dict.py`)

```sql
CREATE TYPE vitrag_dict_status AS ENUM ('draft', 'approved', 'deprecated');

CREATE TABLE vitrag_dict (
  id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  raw_id             UUID REFERENCES vitrag_dict_raw(id) ON DELETE SET NULL,
  hi_term            TEXT NOT NULL,                  -- NFC
  en_term            TEXT NOT NULL,
  pos                TEXT,                           -- 'n' | 'v' | 'adj' | 'adv' | ...
  definition_hi      TEXT,
  definition_en      TEXT,
  examples           JSONB NOT NULL DEFAULT '[]'::jsonb,
  status             vitrag_dict_status NOT NULL DEFAULT 'draft',
  reviewer_id        UUID,                           -- users.id (auth-service, soft FK)
  approved_at        TIMESTAMPTZ,
  deprecated_reason  TEXT,
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT uq_vitrag_hi_en UNIQUE (hi_term, en_term)
);
CREATE INDEX idx_vitrag_hi ON vitrag_dict(hi_term);
CREATE INDEX idx_vitrag_en ON vitrag_dict(en_term);
CREATE INDEX idx_vitrag_status ON vitrag_dict(status);
CREATE INDEX idx_vitrag_hi_trgm ON vitrag_dict USING gin (hi_term gin_trgm_ops);
CREATE INDEX idx_vitrag_en_trgm ON vitrag_dict USING gin (en_term gin_trgm_ops);
CREATE EXTENSION IF NOT EXISTS pg_trgm;
```

### Pydantic contracts

```python
class VitragRawOut(BaseModel):
    id: UUID
    hi_term: str
    en_term: str | None
    definitions: list[dict]
    pos_hint: str | None
    source_url: str
    scraped_at: datetime

class VitragDictOut(BaseModel):
    id: UUID
    hi_term: str
    en_term: str
    pos: str | None
    definition_hi: str | None
    definition_en: str | None
    examples: list[dict]
    status: Literal['draft','approved','deprecated']
    reviewer_id: UUID | None
    approved_at: datetime | None

class VitragApproveIn(BaseModel):
    en_term: str                                # may differ from raw
    pos: str | None = None
    definition_hi: str | None = None
    definition_en: str | None = None
    examples: list[dict] = []
```

### Promotion semantics

Promoting a raw row to canonical:

```python
async def promote_raw(raw_id: UUID, payload: VitragApproveIn, *, reviewer_id: UUID):
    async with pg.transaction() as tx:
        raw = await get_raw(tx, raw_id)
        hi = nfc(raw.hi_term)
        en = nfc(payload.en_term)
        stmt = pg_insert(VitragDict).values(
            raw_id=raw_id, hi_term=hi, en_term=en, pos=payload.pos,
            definition_hi=payload.definition_hi, definition_en=payload.definition_en,
            examples=payload.examples, status='approved',
            reviewer_id=reviewer_id, approved_at=func.now(),
        ).on_conflict_do_update(index_elements=['hi_term','en_term'],
            set_={'status':'approved', 'reviewer_id': reviewer_id,
                  'approved_at': func.now(), 'updated_at': func.now()})
        await tx.execute(stmt)
```

A single `(hi_term, en_term)` collision is treated as an update, not a duplicate. Multiple English senses for one Hindi term are allowed (different rows, same `hi_term`).

## Phase C — Read API + integration

### Endpoints

```
GET   /vitrag-dict/search?q=<hi or en>&status=approved&limit=20
GET   /vitrag-dict/{id}
GET   /vitrag-dict/by-hi/{hi_term}              # all senses for a Hindi term
GET   /admin/vitrag-dict/raw?has_canonical=false&page=...
POST  /admin/vitrag-dict/raw/{raw_id}/approve   body: VitragApproveIn
POST  /admin/vitrag-dict/{id}/deprecate         body: { reason: str }
POST  /admin/vitrag-dict/{id}                   body: VitragApproveIn   # edit canonical
```

Public endpoints (`GET /vitrag-dict/*`) return only `status='approved'` unless `?include_drafts=true` is set and the caller is admin. Admin endpoints gated by `require_role('reviewer','admin')`.

### Search

```sql
SELECT * FROM vitrag_dict
WHERE status='approved'
  AND (hi_term % :q OR en_term % :q OR hi_term ILIKE :q || '%' OR en_term ILIKE :q || '%')
ORDER BY GREATEST(similarity(hi_term, :q), similarity(en_term, :q)) DESC
LIMIT 20;
```

### Cross-link from extraction spans

Spec 08's `extraction_spans.vitrag_en_candidate` is a free-text suggestion from the LLM. On span approval, the data-service helper `link_span_to_vitrag(span_id)` finds the matching `vitrag_dict` row (exact `(hi_term, en_term)` match where `hi_term = nfc(span_text)` and `en_term = nfc(vitrag_en_candidate)`) and attaches its id to the keyword translation via `keyword_translations.vitrag_dict_id` (column added in this migration's down-pass to that table — non-destructive `ADD COLUMN`).

```sql
ALTER TABLE keyword_translations ADD COLUMN vitrag_dict_id UUID
  REFERENCES vitrag_dict(id) ON DELETE SET NULL;
CREATE INDEX idx_keyword_translations_vitrag ON keyword_translations(vitrag_dict_id);
```

### Phase B + C tests (TDD)

3. `test_dedupe_hi_term_collisions.py` — scrape a page containing two `<entry>` blocks with identical `raw_html` → second insert is a no-op (`content_hash` UNIQUE). Distinct entries with the same `hi_term` but different `raw_html` → both rows land.
4. `test_reviewer_approval_atomicity.py` — concurrent `promote_raw` calls for the same `(hi_term, en_term)` → exactly one row in `vitrag_dict` (UNIQUE wins); the loser path becomes an UPDATE, both reviewers' `approved_at` columns are observed (last-write-wins on `reviewer_id`); no orphan partial state.
5. `test_search_trgm_ranks_correctly.py` — query `q='atma'` returns approved `आत्मा / Soul` ahead of approved `परमात्मा / Supreme Soul`.
6. `test_deprecate_hides_from_public.py` — POST deprecate → `GET /vitrag-dict/search` no longer returns the row; admin search with `include_drafts=true` does.
7. `test_extraction_span_link_attaches_vitrag_dict_id.py` — approve a span whose `(hi_term, vitrag_en_candidate)` matches a canonical row → corresponding `keyword_translations` row picks up `vitrag_dict_id`.

## Manual verification

```bash
# 1. Apply migrations
alembic upgrade head

# 2. Run a bounded scrape (dev env, small whitelist)
celery -A workers call vitrag.scrape_all --kwargs '{}'
psql -c "SELECT COUNT(*) FROM vitrag_dict_raw;"

# 3. List raw rows awaiting promotion
curl -H 'authorization: Bearer <reviewer>' \
  'http://localhost:8002/admin/vitrag-dict/raw?has_canonical=false&page=1'

# 4. Approve one
curl -X POST -H 'authorization: Bearer <reviewer>' \
  -H 'content-type: application/json' \
  -d '{"en_term":"Soul","pos":"n","definition_en":"the conscious substance ..."}' \
  http://localhost:8002/admin/vitrag-dict/raw/<raw_id>/approve

# 5. Public search
curl 'http://localhost:8002/vitrag-dict/search?q=आत्मा'
curl 'http://localhost:8002/vitrag-dict/search?q=soul'

# 6. Verify Stage B extraction reads from the view
psql -c "SELECT hi_term, en_term FROM vitrag_dict WHERE status='approved' LIMIT 10;"

# 7. Deprecate
curl -X POST -H 'authorization: Bearer <admin>' \
  -d '{"reason":"superseded by sense-split entries"}' \
  http://localhost:8002/admin/vitrag-dict/<id>/deprecate
```

## Definition of done

- [ ] Migrations `0032_vitrag_dict_raw.py` and `0033_vitrag_dict.py` apply clean.
- [ ] All 7 tests pass.
- [ ] Scraper respects rate limit (observable via wall-time test) and supports ETag-driven re-scrapes.
- [ ] Reviewer can promote a raw row in < 5 clicks via the admin UI.
- [ ] At least 500 approved canonical rows on the demo dataset, queryable by either language.
- [ ] Stage B extraction (`08_translation_pipeline_extraction_spec.md`) consumes the canonical view and produces `vitrag_en_candidate` values that match.
- [ ] Approved span backfill populates `keyword_translations.vitrag_dict_id`.

## Implementation notes

_(to be filled in after merge)_
