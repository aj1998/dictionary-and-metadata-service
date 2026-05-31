# Refactor — Merge `metadata-service` + `data-service` + `navigation-service` into `core-service`

**Status**: Spec (not yet implemented)
**Author**: Architecture
**Scope**: Backend FastAPI consolidation only. Query-service stays independent (port 8004). UI, query-service, ingestion workers, and `jain_kb_common` are untouched except for one rewrite-target update in `ui/next.config.ts`.

---

## 1. Motivation

The three services ([`metadata`](../metadata/01_spec.md), [`data`](../data/01_spec.md), [`navigation`](../navigation/01_spec.md)) share business domain (the same Postgres schema, the same admin auth, the same `/v1` API contract) but currently run as three independent FastAPI processes on ports 8001 / 8002 / 8003. Running three uvicorns on a single laptop wastes RAM and heats the system without any isolation benefit — they all read/write the same DBs and there is no per-service scaling story.

`query-service` (port 8004, [`docs/design/query_engine/00_overview.md`](../../query_engine/00_overview.md)) **stays separate**: it implements distinct GraphRAG orchestration logic, has its own pipeline, and is the public seam for `cataloguesearch-chat`. Merging it in would couple a public contract to internal CRUD churn.

### Non-goals

- No endpoint URL changes — every existing `/v1/...` route keeps the same path, method, request, and response.
- No DB schema changes.
- No router/schema consolidation across former domains (deferred to a future cleanup; see §10).
- No change to ingestion workers, `jain_kb_common`, query-service, or test fixtures.
- No auth/permission changes.

---

## 2. Target architecture

| Name | Module | Port | Reads | Writes |
|---|---|---|---|---|
| `core-service` (new) | `services/core_service/` | **8001** | Postgres + Mongo + Neo4j | Postgres + Mongo + Neo4j |
| `query-service` (unchanged) | `services/query_service/` | 8004 | Postgres + Mongo + Neo4j | Postgres (query_logs) |

Ports 8002 and 8003 disappear. The UI proxy keeps using all three of its old prefixes (`/api/metadata/*`, `/api/data/*`, `/api/navigation/*`) — they all rewrite to `http://localhost:8001` in `ui/next.config.ts`. Zero changes to UI client code.

### Endpoint inventory after merge

All under base `/v1`, served by one FastAPI app. No paths collide (verified by inspection — paths under `/v1/keywords/...`, `/v1/topics/...`, and `/v1/admin/...` are sub-path-disjoint between former data and former navigation routers).

Former **metadata**: `/v1/authors`, `/v1/shastras`, `/v1/teekas`, `/v1/anuyogas`, `/v1/publications`, `/v1/publishers`, `/v1/books`, `/v1/pravachans`, `/v1/admin/search`
Former **data**: `/v1/keywords`, `/v1/keywords/letters`, `/v1/keywords/{ident}`, `/v1/topics`, `/v1/topics/{ident}`, `/v1/gathas`, `/v1/kalashas`, `/v1/browse/*`, `/v1/search`, `/v1/stats`, `PATCH /v1/admin/keywords/{ident}`
Former **navigation**: `/v1/keywords/{token}/resolve`, `/v1/keywords/{nk}/topics`, `/v1/topics/{nk}/neighbors`, `/v1/topics/{nk}/keywords`, `/v1/graph/shortest_path`, `/v1/landing`, `/v1/landing/random`, `/v1/expand/{nk}`, `/v1/preview/{nk}`, `/v1/admin/keywords/{id}/aliases`, `/v1/admin/topics/{nk}/edges`, `/v1/admin/graph/resync`, `/v1/admin/graph/stubs`

---

## 3. New layout

```
services/
├── core_service/
│   ├── __init__.py
│   ├── main.py                  # single FastAPI app — lifespan + all routers
│   ├── config.py                # merged Settings (superset of all three)
│   ├── deps.py                  # merged session/mongo/neo4j/admin deps
│   └── domains/
│       ├── __init__.py
│       ├── metadata/
│       │   ├── __init__.py
│       │   ├── routers/         # moved from services/metadata_service/routers/
│       │   ├── schemas/         # moved from services/metadata_service/schemas/
│       │   └── services/        # moved from services/metadata_service/services/
│       ├── data/
│       │   ├── routers/         # moved from services/data_service/routers/
│       │   ├── schemas/
│       │   └── services/
│       └── navigation/
│           ├── routers/         # moved from services/navigation_service/routers/
│           ├── schemas/
│           └── services/
└── query_service/               # unchanged
```

Each domain is a thin sub-package — no logic moves between files; only its parent package path changes. This is a literal lift-and-shift.

---

## 4. Merged `config.py`

Union of all three current `Settings` classes. Existing `.env` keeps working unchanged because each three-way superset is additive.

```python
# services/core_service/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import model_validator

LANDING_SEED_KEYWORDS: list[str] = ["द्रव्य", "पर्याय"]

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Postgres (was in all 3)
    DATABASE_URL: str

    # Mongo (was in data only)
    MONGO_URL: str = "mongodb://localhost:27017"
    MONGO_DB_NAME: str = "jain_kb"

    # Neo4j (was in navigation only)
    NEO4J_URL: str = "bolt://localhost:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str
    NEO4J_DATABASE: str = "neo4j"
    NEO4J_USE_DEFAULT_DATABASE: bool = False

    # Shared
    ADMIN_USER: str
    ADMIN_PASSWORD: str
    LOG_LEVEL: str = "INFO"
    PORT: int = 8001  # reuses former metadata port

    @model_validator(mode="after")
    def apply_neo4j_database_switch(self) -> "Settings":
        if self.NEO4J_USE_DEFAULT_DATABASE:
            self.NEO4J_DATABASE = "neo4j"
        return self

settings = Settings()  # type: ignore[call-arg]
```

**Note**: `NEO4J_PASSWORD` becomes required for any process that boots `core_service` (because navigation lifespan still pings Neo4j on startup). This is fine for dev (`.env` already has it) and is captured in the migration checklist (§8).

---

## 5. Merged `deps.py`

Concatenation of the three `deps.py` files. Names are already unique — `get_session`, `get_mongo_db`, `get_neo4j_driver`, `require_admin`, `security`. Only one copy of each remains. Module-level singletons (`_engine`, `_session_factory`, `_mongo_client`, `_neo4j_driver`) become single globals in `core_service/deps.py`.

```python
# services/core_service/deps.py — final shape
from __future__ import annotations
import secrets
from collections.abc import AsyncGenerator

from fastapi import Depends, HTTPException
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from neo4j import AsyncDriver
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from .config import settings

_engine = None
_session_factory: async_sessionmaker | None = None
_mongo_client: AsyncIOMotorClient | None = None
_neo4j_driver: AsyncDriver | None = None

def _get_factory() -> async_sessionmaker: ...           # copied verbatim
async def get_session() -> AsyncGenerator[AsyncSession, None]: ...
def _get_mongo_client() -> AsyncIOMotorClient: ...
async def get_mongo_db() -> AsyncIOMotorDatabase: ...
def get_neo4j_driver() -> AsyncDriver: ...

security = HTTPBasic()
def require_admin(credentials: HTTPBasicCredentials = Depends(security)) -> None: ...
```

(Each function body is byte-identical to its current source; only the import path of `settings` changes.)

---

## 6. Merged `main.py`

```python
# services/core_service/main.py
from __future__ import annotations
import json, logging, os, time
from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

from .config import settings
from .deps import get_neo4j_driver, _get_factory

# metadata domain
from .domains.metadata.routers import (
    admin_search, anuyogas, authors, books, pravachans,
    publications, publishers, shastras, teekas,
)
# data domain
from .domains.data.routers import (
    browse, gathas, kalashas, keywords as data_keywords,
    search, stats, topics as data_topics,
)
# navigation domain
from .domains.navigation.routers import (
    admin as nav_admin, graph, keywords as nav_keywords, topics as nav_topics,
)

logging.basicConfig(level=settings.LOG_LEVEL)

_node_count_cache: tuple[int, float] | None = None
_NODE_COUNT_TTL = 300.0


def _load_publishers() -> list[dict]:
    base = os.path.dirname(__file__)
    path = os.path.normpath(os.path.join(
        base, "..", "..", "parser_configs", "_manual_configs", "publishers.json"
    ))
    with open(path) as f:
        return json.load(f)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # publishers cache (was metadata.lifespan)
    app.state.publishers = _load_publishers()
    # neo4j ping (was navigation.lifespan)
    driver = get_neo4j_driver()
    logging.info("Core service using Neo4j database: %s", settings.NEO4J_DATABASE)
    try:
        async with driver.session(database=settings.NEO4J_DATABASE) as session:
            await session.run("RETURN 1")
    except Exception as exc:
        logging.warning("Neo4j not reachable on startup: %s", exc)
    yield
    await driver.close()


app = FastAPI(title="Core Service", version="1.0.0", lifespan=lifespan)


@app.get("/healthz", tags=["health"])
async def healthz() -> dict:
    # Composite health: copies navigation's richer check (it already pinged both Postgres + Neo4j)
    global _node_count_cache
    neo4j_status, postgres_status, node_count = "ok", "ok", 0
    driver = get_neo4j_driver()
    try:
        now = time.monotonic()
        if _node_count_cache and _node_count_cache[1] > now:
            node_count = _node_count_cache[0]
        else:
            async with driver.session(database=settings.NEO4J_DATABASE) as session:
                result = await session.run("MATCH (n) RETURN count(n) AS cnt")
                record = await result.single()
                node_count = int(record["cnt"]) if record else 0
            _node_count_cache = (node_count, now + _NODE_COUNT_TTL)
    except Exception:
        neo4j_status = "error"
    try:
        factory = _get_factory()
        async with factory() as session:
            await session.execute(text("SELECT 1"))
    except Exception:
        postgres_status = "error"
    return {"status": "ok", "neo4j": neo4j_status, "postgres": postgres_status, "graph_node_count": node_count}


@app.exception_handler(404)
async def not_found_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=404, content={"error": {"code": "not_found", "message": "Not found"}})


# Metadata routers
for r in (authors.router, shastras.router, anuyogas.router, teekas.router,
          publications.router, publishers.router, books.router, pravachans.router,
          admin_search.router):
    app.include_router(r)

# Data routers
for r in (data_keywords.router, data_topics.router, gathas.router, kalashas.router,
          browse.router, search.router, stats.router):
    app.include_router(r)

# Navigation routers
for r in (nav_keywords.router, nav_topics.router, graph.router, nav_admin.router):
    app.include_router(r)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("services.core_service.main:app", host="0.0.0.0", port=settings.PORT, reload=False)
```

### Router import-aliasing rationale

`data/routers/keywords.py` and `navigation/routers/keywords.py` both export a `router` symbol; same for `topics.py`. The `as data_keywords` / `as nav_keywords` aliasing in the import line is the only adjustment needed — neither file is modified.

### `/healthz` shape change

Former `metadata` and `data` returned `{"status": "ok"}`. Former `navigation` returned `{"status": "ok", "neo4j": ..., "postgres": ..., "graph_node_count": ...}`. The merged service uses the richer shape. **Compat check**: the UI does not call `/healthz`. The only callers are local manual testing and Docker healthcheck — both happy with an additive payload. No external consumer breakage.

---

## 7. Internal import updates

Inside each moved file (`services/{metadata|data|navigation}_service/routers/foo.py`, `schemas/...`, `services/...`):

```python
# OLD                              # NEW (after move)
from ..config import settings      from ....config import settings
from ..deps import get_session     from ....deps import get_session
from ..deps import require_admin   from ....deps import require_admin
```

Relative depth changes from 2 dots to 4 dots because each file is now nested two extra levels (`core_service/domains/<domain>/routers/foo.py`).

**Mechanical recipe** (run from repo root, dry-run first):

```bash
# domain = metadata | data | navigation
# 1. move
git mv services/${domain}_service/routers services/core_service/domains/${domain}/routers
git mv services/${domain}_service/schemas services/core_service/domains/${domain}/schemas
git mv services/${domain}_service/services services/core_service/domains/${domain}/services

# 2. relative-import rewrite, scoped to moved files
find services/core_service/domains/${domain} -name '*.py' -print0 \
  | xargs -0 sed -i '' -E 's/from \.\.config/from ....config/g; s/from \.\.deps/from ....deps/g'
```

No absolute `from services.<svc>...` imports exist in production code (verified: `grep -rn "from services\." services workers packages` returns hits only inside `tests/`). So production code requires no further import rewriting beyond the relative-depth bump above.

---

## 8. Test updates

Tests are the only place absolute `from services.<svc>...` imports exist. We do **not** move the test trees (keeps blame history readable). We only rewrite imports:

```bash
# Per former domain, rewrite test imports:
find tests/services/metadata -name '*.py' -print0 | xargs -0 sed -i '' \
  -e 's|from services\.metadata_service\.main|from services.core_service.main|g' \
  -e 's|from services\.metadata_service import deps|from services.core_service import deps|g' \
  -e 's|from services\.metadata_service\.routers|from services.core_service.domains.metadata.routers|g' \
  -e 's|from services\.metadata_service\.schemas|from services.core_service.domains.metadata.schemas|g' \
  -e 's|from services\.metadata_service\.services|from services.core_service.domains.metadata.services|g' \
  -e 's|from services\.metadata_service\.config|from services.core_service.config|g'

# Repeat with s/metadata/data/ and s/metadata/navigation/ in the two trailing slashes only
```

After the rewrite, the existing tests should pass as-is because:
- The mounted FastAPI app is bit-equivalent (same routes, same handlers).
- The dependency-override mechanism in each conftest now overrides on `core_service.deps` instead of the per-service `deps` module. The conftests already import `deps` by name (`from services.<svc> import deps; app.dependency_overrides[deps.get_session] = ...`), so the rewrite above takes care of this in one step.

### Single-suite consequence

`tests/services/metadata/`, `tests/services/data/`, `tests/services/navigation/` now all override deps on the same `core_service.deps` module. This is already the implicit state today when `python -m pytest tests/services/` runs them together (the README notes they share Postgres schema and are run as one suite). Test isolation is unaffected — `app.dependency_overrides` is per-app and pytest fixtures rebuild the app per test where needed.

---

## 9. Implementation steps (sequenced)

A single agent in one context window can complete this in the order below. Each step ends with a verification command.

### Step 1 — scaffold the package
- Create `services/core_service/{__init__.py, domains/__init__.py, domains/metadata/__init__.py, domains/data/__init__.py, domains/navigation/__init__.py}`.
- Verify: `python -c "import services.core_service"` — no error.

### Step 2 — write merged `config.py` and `deps.py`
- Copy code from §4 and §5 verbatim.
- Verify: `python -c "from services.core_service.config import settings; print(settings.PORT)"` prints `8001` (with `.env` exported).

### Step 3 — move each domain (one at a time, run tests after each)

For `domain` in `(metadata, data, navigation)`:
1. Run the `git mv` block from §7.
2. Run the `sed` relative-import rewrite from §7.
3. Run the corresponding test-import `sed` block from §8.
4. Run the domain's test suite to confirm green:
   ```bash
   export DATABASE_URL="postgresql+asyncpg://$(whoami)@localhost/jain_kb_test"
   export NEO4J_PASSWORD=jainkb_password
   python -m pytest tests/services/${domain}/ -v
   ```
   Tests should still pass because the merged `core_service.main` isn't wired yet, but tests import their own domain routers / app under construction. **Read this carefully**: at the end of step 3 for the first domain, `core_service/main.py` does not exist, so conftests that import `services.core_service.main` will fail. The correct order is:
   - Do steps 4 (main.py) **before** step 3's test runs. See revised order below.

### Step 3 (revised) — write `main.py` first, then move domains

- Write `services/core_service/main.py` per §6, but initially comment out the router imports for domains that haven't moved yet so the file imports cleanly.
- For each `domain` in (`metadata`, `data`, `navigation`):
  1. `git mv` directories per §7.
  2. `sed` rewrite production imports per §7.
  3. `sed` rewrite test imports per §8.
  4. Uncomment that domain's router imports + `include_router` calls in `main.py`.
  5. Run `python -m pytest tests/services/${domain}/ -v` — must be green.

### Step 4 — delete the old service packages

After all three domains have moved and their tests are green:
```bash
git rm -r services/metadata_service services/data_service services/navigation_service
```

Verify nothing else references them:
```bash
grep -rn "metadata_service\|data_service\|navigation_service" \
  services workers packages tests scripts --include='*.py' | grep -v __pycache__
# expected: 0 hits
```

### Step 5 — full test suite

```bash
export DATABASE_URL="postgresql+asyncpg://$(whoami)@localhost/jain_kb_test"
export MONGO_URL="mongodb://localhost:27017"
export NEO4J_URL="bolt://localhost:7687"
export NEO4J_USER="neo4j"
export NEO4J_PASSWORD="jainkb_password"
export NIKKYJAIN_LOCAL_PATH="/path/to/nikkyjain.github.io"
python -m pytest tests/ -v
# expected: 746 passed (same count as pre-refactor baseline in README:275)
```

### Step 6 — update the UI rewrites

Edit `ui/next.config.ts` — keep all three `source` paths, point them at the same target:

```typescript
async rewrites() {
  const coreTarget = process.env.CORE_SVC_URL
    ?? process.env.METADATA_SVC_URL  // legacy
    ?? "http://localhost:8001";
  const queryTarget = process.env.QUERY_SVC_URL ?? "http://localhost:8004";
  return [
    { source: "/api/metadata/:path*",   destination: `${coreTarget}/:path*` },
    { source: "/api/data/:path*",       destination: `${coreTarget}/:path*` },
    { source: "/api/navigation/:path*", destination: `${coreTarget}/:path*` },
    { source: "/api/query/:path*",      destination: `${queryTarget}/:path*` },
  ];
},
```

No changes to `ui/src/lib/api/*.ts`. The three UI client base paths (`/api/metadata`, `/api/data`, `/api/navigation`) keep working unchanged.

### Step 7 — manual verification

Start the core service and the UI side-by-side:

```bash
# terminal 1: core
source .venv/bin/activate
export DATABASE_URL="postgresql+asyncpg://$(whoami)@localhost/jain_kb_dev"
export NEO4J_PASSWORD=jainkb_password
python -m services.core_service.main

# terminal 2: ui
cd ui && pnpm dev

# terminal 3: smoke
curl -s http://localhost:8001/healthz | jq
curl -s http://localhost:8001/v1/shastras?limit=2 | jq
curl -s http://localhost:8001/v1/keywords?limit=2 | jq
curl -s http://localhost:8001/v1/landing/random?depth=1 | jq '.nodes | length'

# Browser smoke (each must render real data):
#   http://localhost:3000/                       (Home — stats)
#   http://localhost:3000/shastras               (metadata path)
#   http://localhost:3000/dictionary             (data path)
#   http://localhost:3000/graph                  (navigation path)
```

---

## 10. Future cleanup (out of scope for this refactor)

Captured here so it doesn't get lost:

1. **Resource-level router consolidation** — `domains/data/routers/keywords.py` and `domains/navigation/routers/keywords.py` could merge into one file under a single `keywords/` package. Same for `topics`. Defer until both domains stabilise.
2. **Admin route grouping** — `PATCH /v1/admin/keywords/{ident}` (former data), `POST /v1/admin/keywords/{id}/aliases` (former navigation), and `GET /v1/admin/search` (former metadata) could share a single `admin/` router package.
3. **Schema deduplication** — there may be similar Pydantic shapes (e.g. `KeywordSummary`) across `domains/data/schemas/` and `domains/navigation/schemas/`. Inventory and dedupe in a follow-up.
4. **README + design-doc updates** — once stable, fold the three `docs/design/api/{metadata,data,navigation}/01_spec.md` into a single `docs/design/api/core/01_spec.md`. Until then, those three specs remain accurate at the endpoint level; add a banner at the top of each linking to this refactor doc.
5. **Docker Compose** — the future deployment story drops from 4 service containers to 2 (`core`, `query`). Update `docker-compose.yml` when added.

---

## 11. Risk register

| Risk | Likelihood | Mitigation |
|---|---|---|
| Hidden import from `services.{metadata,data,navigation}_service` outside `tests/` | Low | Grep verified clean today; Step 4 re-grep is a hard gate. |
| Two routers register the same path | None | Verified disjoint by inspection of every `@router.get/post/...` decorator (see §2). |
| `/healthz` shape regression | Low | The richer shape is a superset; no caller depends on a specific field set. |
| `NEO4J_PASSWORD` now required in environments that previously ran only metadata or data | Medium | Document in §8 of this doc and in the migration PR description; CI already sets it. |
| Test fixture isolation breaks because all three test trees override the same `core_service.deps` module | Low | Each conftest scopes overrides per app instance; pytest tear-down restores. Existing combined `pytest tests/services/` run is the proof. |
| UI accidentally calls a path that didn't exist on its old prefix (e.g. UI hits `/api/data/v1/landing`) | Very low | All UI calls route through typed clients (`api/data.ts`, etc.) whose `path` literals match their domain. |

---

## 12. Rollback

Single commit / single PR. Rollback = `git revert`. No DB migration, no irreversible action. The three old service packages are recovered intact from git history.

---

## 13. Acceptance checklist

- [ ] `services/core_service/` exists with `config.py`, `deps.py`, `main.py`, `domains/{metadata,data,navigation}/`.
- [ ] `services/metadata_service/`, `services/data_service/`, `services/navigation_service/` are deleted.
- [ ] `grep -rn "metadata_service\|data_service\|navigation_service" services workers packages tests scripts --include='*.py'` returns 0 hits.
- [ ] `python -m pytest tests/ -v` passes with the same count as the pre-refactor baseline (746 as of README:275).
- [ ] `python -m services.core_service.main` boots cleanly with a populated `.env` and `/healthz` returns `{"status":"ok","neo4j":"ok","postgres":"ok",...}`.
- [ ] UI dev server (`pnpm dev`) renders Home, `/shastras`, `/dictionary`, `/graph` against the merged backend with no console errors.
- [ ] `ui/next.config.ts` rewrites point `metadata|data|navigation` to a single `CORE_SVC_URL`.
- [ ] This doc updated with an **Implementation Notes** section recording deviations and the final test count.

---

## 14. Implementation notes

- Implemented on **2026-05-31**.
- `services/core_service/` created with merged:
  - `config.py` (union of metadata/data/navigation settings)
  - `deps.py` (shared SQLAlchemy + Mongo + Neo4j + admin deps)
  - `main.py` (single FastAPI app, merged routers, composite `/healthz`)
- Lift-and-shift domain moves completed:
  - `services/core_service/domains/metadata/{routers,schemas,services}`
  - `services/core_service/domains/data/{routers,schemas,services}`
  - `services/core_service/domains/navigation/{routers,schemas,services}`
- Relative import depth was rewritten from `..config` / `..deps` to `....config` / `....deps` in moved domain files.
- Test imports were rewritten to `services.core_service.*`; navigation test string patch targets were updated to `services.core_service.main.get_neo4j_driver`.
- Legacy packages were removed:
  - `services/metadata_service/`
  - `services/data_service/`
  - `services/navigation_service/`
- `ui/next.config.ts` rewrites were updated so `/api/metadata/*`, `/api/data/*`, and `/api/navigation/*` all proxy to one core target.
- Added TDD regression test: `tests/services/core/test_main.py` asserting merged `/healthz` payload shape.

### Verification executed here

- ✅ `python -m pytest tests/services/core/test_main.py -q`
- ✅ `python -m pytest tests/services/core/test_main.py tests/services/navigation/test_config.py -q`
- ⚠️ DB-backed suites are blocked in this sandbox (`PermissionError` connecting to Postgres socket on localhost:5432), so full `tests/services/*` and `tests/*` counts were not reproducible in this environment.
