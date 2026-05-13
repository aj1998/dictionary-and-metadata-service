# Metadata Service API — Updated Spec

> **Supersedes**: `docs/design/05_api_metadata_service.md`
> **Status**: Draft — open questions listed at bottom
> **Schema source of truth**: `packages/jain_kb_common/jain_kb_common/db/postgres/`

---

## Service identity

- **Module path**: `services/metadata_service/`
- **Default port**: `8001`
- **Base path**: `/v1`
- **Health**: `GET /healthz` → `{"status": "ok"}`
- **OpenAPI**: auto-served at `/openapi.json`
- **Auth**: `GET` endpoints are unauthenticated. `POST/PATCH/DELETE` under `/v1/admin/` require HTTP Basic Auth (env `ADMIN_USER` / `ADMIN_PASSWORD`).

---

## What changed from doc 05

| Area | Change |
|---|---|
| `publications` | New table. Endpoint group added. |
| `kalashas` | **Not in this service** — same boundary as gathas (dictionary-service) |
| `topics` | `topic_path`, `parent_topic_id`, `is_leaf`, `is_synthetic` added — **topics live in dictionary-service, not here** |
| `teekas` | Has multiple publications as sub-resources |
| Auth | Basic auth (same as old doc); `X-Admin-Key` was wrong in initial draft |
| `DELETE` author | Removed — authors are never deleted; ingestion is idempotent |
| Gatha listing | `GET /v1/shastras/{id}/gathas` removed — lives in dictionary-service |

---

## Scope

The metadata-service owns these Postgres tables:

| Table | Served by |
|---|---|
| `authors` | this service |
| `shastras` | this service |
| `anuyogas` | this service (read-only; seeded) |
| `shastra_anuyogas` | this service (via shastra detail) |
| `teekas` | this service |
| `publications` | this service (sub-resource of teeka) |
| `books` | this service |
| `book_anuyogas` | this service (via book detail) |
| `pravachans` | this service |

**Not in scope here** (owned by dictionary-service): `keywords`, `keyword_aliases`, `gathas`, `kalashas`, `topics`, `topic_mentions`.

---

## Common types

```python
# All multilingual JSONB fields use this shape
class LangText(BaseModel):
    lang: str    # ISO-639-3 e.g. "hin", "san", "pra"
    script: str  # ISO-15924 e.g. "Deva", "Latn"
    text: str

class Pagination(BaseModel):
    total: int
    limit: int
    offset: int

class ErrorDetail(BaseModel):
    code: Literal["not_found", "validation_error", "conflict", "unauthorized", "internal"]
    message: str
    details: dict | None = None

class ErrorEnvelope(BaseModel):
    error: ErrorDetail
```

All list endpoints accept `?limit=` (default 50, max 200) and `?offset=` (default 0).

HTTP status codes: 200, 201, 204, 400, 401, 404, 409, 422, 500.

---

## Endpoints

### Authors

```
GET    /v1/authors                      list all authors
GET    /v1/authors/{id|natural_key}     fetch one
POST   /v1/admin/authors                create
PATCH  /v1/admin/authors/{id}           update
```

**Author response:**
```json
{
  "id": "uuid",
  "natural_key": "kundkundacharya",
  "display_name": [{"lang": "hin", "script": "Deva", "text": "कुन्दकुन्दाचार्य"}],
  "kind": "acharya",
  "bio": [{"lang": "hin", "script": "Deva", "text": "..."}],
  "created_at": "2026-05-01T12:00:00Z",
  "updated_at": "2026-05-01T12:00:00Z"
}
```

`kind` values: `acharya` | `gyaani` | `scholar` | `unknown`

**List response:**
```json
{
  "items": [ /* Author */ ],
  "pagination": {"total": 12, "limit": 50, "offset": 0}
}
```

**Create/Update body** (`POST /v1/admin/authors`):
```json
{
  "natural_key": "kundkundacharya",
  "display_name": [{"lang": "hin", "script": "Deva", "text": "..."}],
  "kind": "acharya",
  "bio": null
}
```

---

### Shastras

```
GET    /v1/shastras                              list (filter: ?author_id=, ?anuyoga=, ?q=)
GET    /v1/shastras/{id|natural_key}             fetch with embedded author + anuyogas + stats
GET    /v1/shastras/{id|natural_key}/teekas      list teekas of this shastra
POST   /v1/admin/shastras                        create
PATCH  /v1/admin/shastras/{id}                   update
```

**Shastra detail response:**
```json
{
  "id": "uuid",
  "natural_key": "pravachansaar",
  "title": [{"lang": "hin", "script": "Deva", "text": "प्रवचनसार"}],
  "author": {
    "id": "uuid",
    "natural_key": "kundkundacharya",
    "display_name": [{"lang": "hin", "script": "Deva", "text": "कुन्दकुन्दाचार्य"}],
    "kind": "acharya"
  },
  "anuyogas": [{"kind": "dravyanuyoga", "display_name": [...]}],
  "source_url": "https://...",
  "description": [...],
  "stats": {
    "total_gathas": 275,
    "total_teekas": 2
  },
  "created_at": "...",
  "updated_at": "..."
}
```

`stats.total_gathas` — count query against `gathas` table on `shastra_id`.
`stats.total_teekas` — count query against `teekas` table on `shastra_id`.

**List response** uses `ShastraSummary` (no `stats`, `description` omitted):
```json
{
  "items": [
    {
      "id": "uuid",
      "natural_key": "pravachansaar",
      "title": [...],
      "author": { /* AuthorSummary */ },
      "anuyogas": [...]
    }
  ],
  "pagination": {...}
}
```

**Filters on `GET /v1/shastras`:**
- `?author_id=<uuid>` — filter by author UUID
- `?anuyoga=dravyanuyoga` — filter by anuyoga kind
- `?q=<text>` — pg_trgm fuzzy search on title JSON text (Devanagari aware)

---

### Anuyogas

```
GET /v1/anuyogas     list all four (no pagination, always 4 rows)
```

**Response:**
```json
[
  {
    "id": "uuid",
    "kind": "dravyanuyoga",
    "display_name": [{"lang": "hin", "script": "Deva", "text": "द्रव्यानुयोग"}],
    "description": [...]
  }
]
```

---

### Teekas

```
GET    /v1/teekas                              list (filter: ?shastra_id=, ?teekakar_id=)
GET    /v1/teekas/{id|natural_key}             fetch with embedded shastra + teekakar
GET    /v1/teekas/{id|natural_key}/publications  list publications of this teeka
POST   /v1/admin/teekas                        create
PATCH  /v1/admin/teekas/{id}                   update
```

**Teeka detail response:**
```json
{
  "id": "uuid",
  "natural_key": "pravachansaar:amritchandra",
  "shastra": {
    "id": "uuid",
    "natural_key": "pravachansaar",
    "title": [...]
  },
  "teekakar": {
    "id": "uuid",
    "natural_key": "amritchandracharya",
    "display_name": [...],
    "kind": "acharya"
  },
  "publisher": [{"lang": "hin", "script": "Deva", "text": "..."}],
  "translator": null,
  "editor": null,
  "cataloguesearch_shastra_id": "cs-shastra-12345",
  "public_url": "https://...",
  "publisher_url": "https://...",
  "stats": {
    "total_publications": 2
  },
  "created_at": "...",
  "updated_at": "..."
}
```

> **Note on `publisher`/`translator`/`editor`**: The SQLAlchemy model uses `dict | None` (JSONB). For the API, treat these as multilingual arrays `list[LangText] | null` at the Pydantic layer. If stored as a single `dict`, wrap in a list on read.

---

### Publications

A publication is a specific print edition of a teeka. A single teeka (commentary text) can have multiple editions from different publishers, and different publications may contain different bhaavarths (devotional verses) on the same teekas' gathas — modelled as `GathaTeekaBhaavarth` nodes in Neo4j.

```
GET    /v1/publications                          list (filter: ?teeka_id=, ?publisher_id=)
GET    /v1/publications/{id|natural_key}         fetch
POST   /v1/admin/publications                    create
PATCH  /v1/admin/publications/{id}               update
```

**Publication response:**
```json
{
  "id": "uuid",
  "natural_key": "pravachansaar:amritchandra:17",
  "teeka": {
    "id": "uuid",
    "natural_key": "pravachansaar:amritchandra"
  },
  "publisher_id": "17",
  "publisher": [{"lang": "hin", "script": "Deva", "text": "परम श्रुत प्रभावक मण्डल"}],
  "public_url": "https://...",
  "publisher_url": "https://...",
  "created_at": "...",
  "updated_at": "..."
}
```

`publisher_id` is the integer ID from `parser_configs/_manual_configs/publishers.json` (e.g. `"17"` → `"परम श्रुत प्रभावक मण्डल"`). The `publisher` JSONB field stores the resolved display name from that file at ingestion time. The API also serves the `GET /v1/publishers` lookup endpoint (see below).

---

### Publishers (lookup)

Read-only lookup served from `parser_configs/_manual_configs/publishers.json` — no DB table, loaded at startup.

```
GET /v1/publishers     list all publishers
```

**Response:**
```json
[
  {"publisher_id": "17", "publisher": "परम श्रुत प्रभावक मण्डल"},
  ...
]
```

---

### Books

```
GET    /v1/books                                 list (filter: ?shastra_id=, ?anuyoga=)
GET    /v1/books/{id|natural_key}                fetch with embedded shastra + anuyogas
POST   /v1/admin/books                           create
PATCH  /v1/admin/books/{id}                      update
```

**Book response:**
```json
{
  "id": "uuid",
  "natural_key": "...",
  "title": [...],
  "shastra": { /* ShastraSummary | null */ },
  "anuyogas": [...],
  "publisher": [...],
  "translator": [...],
  "editor": [...],
  "public_url": "...",
  "publisher_url": "...",
  "created_at": "...",
  "updated_at": "..."
}
```

---

### Pravachans

```
GET    /v1/pravachans                            list (filter: ?shastra_id=, ?speaker_id=)
GET    /v1/pravachans/{id|natural_key}           fetch with embedded shastra + speaker
POST   /v1/admin/pravachans                      create
PATCH  /v1/admin/pravachans/{id}                 update
```

**Pravachan response:**
```json
{
  "id": "uuid",
  "natural_key": "...",
  "title": [...],
  "shastra": { /* ShastraSummary | null */ },
  "speaker": { /* AuthorSummary | null */ },
  "publisher": [...],
  "translator": [...],
  "editor": [...],
  "public_url": "...",
  "publisher_url": "...",
  "created_at": "...",
  "updated_at": "..."
}
```

---

### Admin search

```
GET /v1/admin/search?q=...&types=shastra,author,teeka,book,pravachan
```

Fuzzy cross-entity search using `pg_trgm`. Used by the admin UI global search box.

Response:
```json
{
  "results": [
    {
      "entity_type": "shastra",
      "id": "uuid",
      "natural_key": "pravachansaar",
      "display": "प्रवचनसार",
      "score": 0.92
    }
  ]
}
```

---

## Module layout

```
services/metadata_service/
├── main.py                  # FastAPI app, lifespan (DB init), routers, error handlers
├── config.py                # pydantic-settings: DATABASE_URL, ADMIN_USER, ADMIN_PASSWORD, LOG_LEVEL
├── deps.py                  # get_session(), require_admin() (HTTP Basic) dependencies
├── routers/
│   ├── authors.py
│   ├── shastras.py
│   ├── anuyogas.py
│   ├── teekas.py
│   ├── publications.py
│   ├── publishers.py        # read-only lookup from publishers.json
│   ├── books.py
│   ├── pravachans.py
│   └── admin_search.py
├── services/                # business logic — calls jain_kb_common.db.postgres
│   ├── authors.py
│   ├── shastras.py
│   ├── teekas.py
│   ├── publications.py
│   ├── books.py
│   └── pravachans.py
├── schemas/                 # Pydantic request/response models
│   ├── common.py            # LangText, Pagination, ErrorEnvelope, AuthorSummary, ShastraSummary
│   ├── authors.py
│   ├── shastras.py
│   ├── anuyogas.py
│   ├── teekas.py
│   ├── publications.py
│   ├── books.py
│   └── pravachans.py
└── tests/
    ├── conftest.py          # async test client + per-test DB transaction rollback
    ├── test_authors.py
    ├── test_shastras.py
    ├── test_teekas.py
    ├── test_publications.py
    ├── test_books.py
    └── test_pravachans.py
```

---

## Configuration

Environment variables (loaded via `pydantic-settings`):

| Var | Required | Default | Notes |
|---|---|---|---|
| `DATABASE_URL` | yes | — | `postgresql+asyncpg://...` |
| `ADMIN_USER` | yes | — | Basic auth username for admin endpoints |
| `ADMIN_PASSWORD` | yes | — | Basic auth password for admin endpoints |
| `LOG_LEVEL` | no | `INFO` | |
| `PORT` | no | `8001` | |

---

## Auth

```python
# services/metadata_service/deps.py
from fastapi.security import HTTPBasic, HTTPBasicCredentials
import secrets

security = HTTPBasic()

def require_admin(credentials: HTTPBasicCredentials = Depends(security)):
    ok = (
        secrets.compare_digest(credentials.username, settings.ADMIN_USER) and
        secrets.compare_digest(credentials.password, settings.ADMIN_PASSWORD)
    )
    if not ok:
        raise HTTPException(401, headers={"WWW-Authenticate": "Basic"})
```

All `GET` endpoints are open (no auth). Admin mutation endpoints use `Depends(require_admin)`.

---

## Startup / lifespan

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Init async engine; no migration run (Alembic handles that separately)
    await init_db()
    yield
    await close_db()
```

No Alembic `upgrade head` on startup — migrations are run explicitly via `alembic upgrade head` in the deploy pipeline.

---

## Fetch-by-id-or-natural-key pattern

Every `GET /v1/{resource}/{ident}` endpoint supports both UUID and `natural_key`:

```python
async def get_by_ident(session, model, ident: str):
    try:
        uid = uuid.UUID(ident)
        return await session.get(model, uid)
    except ValueError:
        result = await session.execute(
            select(model).where(model.natural_key == ident)
        )
        return result.scalar_one_or_none()
```

---

## Tests strategy

- Each test function wraps in a savepoint (`SAVEPOINT` / `ROLLBACK TO SAVEPOINT`) so tests don't pollute each other.
- Seed fixtures: one author, one shastra, one teeka, one publication — created once per module via `session_scoped` fixture.
- All `GET` endpoints get a happy-path test + 404 test.
- All `POST/PATCH` admin endpoints get: valid body → 201/200, missing required field → 422, wrong credentials → 401, duplicate natural_key → 409.
- Target: ≥ 80% coverage on `routers/` and `services/`.

---

## Implementation phases

### Phase A — Read-only GET endpoints (unblocks frontend navigation)
Authors, Shastras, Anuyogas, Teekas, Publications, Publishers, Books, Pravachans.
No auth required. Basic pagination + filters.

### Phase B — Admin mutation endpoints
POST/PATCH for all resources behind `require_admin`. Enables manual data entry without re-running full ingestion.

### Phase C — Admin search
`GET /v1/admin/search` — cross-entity pg_trgm search.

---

## Example handler

```python
# services/metadata_service/routers/shastras.py
@router.get("/{ident}", response_model=ShastraDetail)
async def get_shastra(ident: str, session: AsyncSession = Depends(get_session)):
    shastra = await shastras_svc.get_by_id_or_natural_key(session, ident)
    if shastra is None:
        raise NotFound("shastra", ident)
    return ShastraDetail.from_orm(shastra)
```

---

## Definition of Done

- [ ] All listed endpoints implemented and reachable.
- [ ] OpenAPI spec served at `/openapi.json` includes all routes with examples.
- [ ] All `GET` endpoints covered by integration tests against a Postgres test container.
- [ ] All `POST/PATCH` admin endpoints validated against Pydantic models and reject unauthenticated requests (401) and duplicate `natural_key` (409).
- [ ] `pytest -q` passes; coverage ≥ 80% on `routers/` and `services/`.
- [ ] Service starts with `uvicorn services.metadata_service.main:app --port 8001`.

---

## Open questions

**Q-1 — Anuyoga filter on Books**
`book_anuyogas` link table exists. Should `GET /v1/books?anuyoga=dravyanuyoga` filter be implemented, mirroring the shastra filter?

**Q-2 — Admin review queue**
The ingestion review queue (`ingestion_review_queue` table) needs admin endpoints (list pending, approve, reject). Deferred — will be addressed when the ingestion worker is built.
