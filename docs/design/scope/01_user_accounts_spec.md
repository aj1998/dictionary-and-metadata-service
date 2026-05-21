# 01 — User Accounts & Preferences Spec

Scope context: [`scope/08_user_accounts.md`](../../scope/08_user_accounts.md).

A new `auth-service` (port 8005) issues JWTs. Every other service treats JWT as optional — a missing JWT means `guest`. Personalisation tables live in Postgres + Mongo and are referenced by `user_id UUID`.

## Phase A — auth-service + JWT

### Files

```
services/auth_service/
├── __init__.py
├── main.py                FastAPI app, /healthz, lifespan, CORS
├── config.py              Settings (DATABASE_URL, JWT_SECRET, JWT_TTL_S, REFRESH_TTL_DAYS,
│                          GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, MAGIC_LINK_FROM_EMAIL,
│                          EMAIL_PROVIDER (resend|ses|postmark), EMAIL_API_KEY, PORT=8005)
├── deps.py                AsyncSession dep, current_user dep (optional + required variants)
├── routers/
│   ├── auth.py            POST /v1/auth/magic-link/request, /v1/auth/magic-link/verify
│   │                      POST /v1/auth/google (OAuth code exchange)
│   │                      POST /v1/auth/refresh, /v1/auth/logout
│   │                      GET  /v1/auth/me
│   └── admin.py           GET /admin/auth/users (paged), POST /admin/auth/users/{id}/role
├── tokens.py              issue_access_token(), issue_refresh_token(), verify(), rotate()
├── magic_link.py          create_link(), send_email(), verify_token()
├── google.py              code-for-token exchange + JWKS verify
└── tests/
    ├── conftest.py
    ├── test_magic_link_flow.py
    ├── test_google_flow.py
    ├── test_refresh_rotation.py
    ├── test_role_enforcement.py
    └── test_account_deletion.py
```

Shared models live in `packages/jain_kb_common/db/postgres/auth.py` and `packages/jain_kb_common/auth/jwt.py` (so every service can decode tokens).

### Postgres schema (migration `0017_users.py`)

```sql
CREATE TYPE user_role AS ENUM ('guest','user','reviewer','admin','service');

CREATE TABLE users (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email           CITEXT UNIQUE,                     -- nullable for service tokens
  email_verified  BOOLEAN NOT NULL DEFAULT false,
  google_sub      TEXT UNIQUE,
  display_name    TEXT,
  role            user_role NOT NULL DEFAULT 'user',
  status          TEXT NOT NULL DEFAULT 'active'     -- 'active' | 'disabled' | 'pending_delete'
                  CHECK (status IN ('active','disabled','pending_delete')),
  last_login_at   TIMESTAMPTZ,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE magic_link_tokens (
  token_hash      TEXT PRIMARY KEY,                  -- sha256 of opaque token
  email           CITEXT NOT NULL,
  expires_at      TIMESTAMPTZ NOT NULL,
  used_at         TIMESTAMPTZ,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_magic_link_expires ON magic_link_tokens(expires_at);

CREATE TABLE refresh_tokens (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  token_hash      TEXT NOT NULL UNIQUE,
  expires_at      TIMESTAMPTZ NOT NULL,
  revoked_at      TIMESTAMPTZ,
  user_agent      TEXT,
  ip              INET,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_refresh_user ON refresh_tokens(user_id);

CREATE EXTENSION IF NOT EXISTS citext;
```

### JWT contract

Access token (httpOnly cookie `saar_at`):

```json
{
  "sub": "<user uuid>",
  "role": "user",
  "iat": 1700000000,
  "exp": 1700000900,                // TTL 15 minutes
  "iss": "jinvani-saar",
  "aud": "jinvani-saar"
}
```

Refresh token (httpOnly cookie `saar_rt`, 30 days). Both tokens sliding-rotated on every `/v1/auth/refresh`.

`current_user(required=False)` dependency lives in `packages/jain_kb_common/auth/jwt.py` and is imported by every service. Returns `User | None`. Required variant raises 401.

### Magic link flow

1. `POST /v1/auth/magic-link/request { email }` — generate opaque 32-byte token, store sha256 with 15-min TTL, email link `https://saar.example/auth/verify?t=<token>`.
2. `POST /v1/auth/magic-link/verify { token }` — look up by `sha256(token)`, ensure unused & unexpired, mark `used_at`, upsert user, issue access+refresh.

### Google OAuth (Authorisation Code with PKCE)

UI handles the redirect; backend just receives `{ code, code_verifier, redirect_uri }`, exchanges via `https://oauth2.googleapis.com/token`, verifies the `id_token` against JWKS, upserts user keyed by `google_sub`.

### Role enforcement helper

```python
# packages/jain_kb_common/auth/decorators.py
def require_role(*allowed: UserRole):
    async def dep(user: User | None = Depends(current_user_required)):
        if user.role not in allowed:
            raise HTTPException(403, "insufficient role")
        return user
    return dep
```

### Account deletion

`DELETE /v1/auth/me` sets `status='pending_delete'`. A nightly Celery task `auth.purge_pending_deletes` hard-deletes after 7 days:
- drops rows in `user_preferences`, `saved_views`, `saved_highlights`, `chat_sessions`, `user_scratchpads` (Mongo)
- anonymises `query_logs` rows by NULL-ing the `user_id` column added in phase B (kept for retrieval improvement)
- deletes the `users` row.

### Tests (TDD — write these first)

1. `test_magic_link_flow.py`: request → email captured by stub → verify → user created → access cookie set.
2. `test_magic_link_replay.py`: same token used twice → 400.
3. `test_magic_link_expired.py`: token > 15 min → 400.
4. `test_google_flow.py`: stub the token endpoint + JWKS; assert user upserts.
5. `test_refresh_rotation.py`: refresh once → new pair; old refresh → revoked.
6. `test_role_enforcement.py`: `user` cannot hit `require_role(REVIEWER)`; `admin` can.
7. `test_account_deletion.py`: deletion → status flips → purge task drops rows.

## Phase B — preferences, saved views, saved highlights

### Files

```
services/auth_service/
├── routers/
│   ├── preferences.py     GET/PUT /v1/me/preferences
│   ├── saved_views.py     GET/POST/DELETE /v1/me/saved-views
│   └── highlights.py      GET/POST/PUT/DELETE /v1/me/highlights

packages/jain_kb_common/db/postgres/auth.py  (extended)
packages/jain_kb_common/db/mongo/scratchpads.py  (Motor; for user_scratchpads collection)
```

### Postgres schema (migration `0018_user_prefs_and_saves.py`)

```sql
CREATE TABLE user_preferences (
  user_id          UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  lang_default     TEXT NOT NULL DEFAULT 'hi',         -- 'hi' | 'en'
  lang_overlay     TEXT,                                -- 'kn' | 'gu' | 'sa' | 'pr' | null
  ui               JSONB NOT NULL DEFAULT '{}'::jsonb,  -- {font_size, theme, density, font_family, ...}
  layout_variants  JSONB NOT NULL DEFAULT '{}'::jsonb,  -- { shastra_natural_key: variant_id }
  default_ai_model TEXT,                                -- foreign string into model_registry.id
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE saved_views (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name            TEXT NOT NULL,
  view_type       TEXT NOT NULL,                       -- 'graph' | 'reader_selection'
  payload         JSONB NOT NULL,                      -- view-specific: graph: {nodes:[nk], filters}, reader: {shastra_nk, range}
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (user_id, view_type, name)
);
CREATE INDEX idx_saved_views_user ON saved_views(user_id);

CREATE TABLE saved_highlights (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  gatha_id        UUID NOT NULL REFERENCES gathas(id) ON DELETE CASCADE,
  panel           TEXT NOT NULL,                       -- 'prakrit' | 'hindi' | 'bhaavarth' | 'anvayartha'
  char_start      INT NOT NULL,
  char_end        INT NOT NULL,
  color           TEXT NOT NULL DEFAULT 'yellow',      -- 'yellow' | 'green' | 'pink' | 'blue'
  note            TEXT,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_highlights_user_gatha ON saved_highlights(user_id, gatha_id);
```

### Pydantic contracts (excerpt)

```python
class PreferencesIn(BaseModel):
    lang_default: Literal['hi','en'] = 'hi'
    lang_overlay: Literal['kn','gu','sa','pr'] | None = None
    ui: dict = Field(default_factory=dict)
    layout_variants: dict[str, str] = Field(default_factory=dict)
    default_ai_model: str | None = None

class SavedViewIn(BaseModel):
    name: constr(min_length=1, max_length=80)
    view_type: Literal['graph','reader_selection']
    payload: dict
```

### Tests (TDD)

1. `test_preferences_round_trip.py`: PUT → GET returns same JSON.
2. `test_saved_views_uniqueness.py`: same (user, view_type, name) → 409.
3. `test_highlights_overlap_allowed.py`: two highlights overlapping ranges both persist.
4. `test_preference_guest_blocked.py`: guest hits 401.
5. `test_account_delete_cascades.py`: deletion of user cascades into all 3 tables.

## Wiring into other services

- Every other service uses `from jain_kb_common.auth.jwt import current_user_optional` for read endpoints (sees `user_id` if logged in; uses it for personalisation).
- Add `user_id UUID NULL` column to `query_logs` in migration `0019_query_logs_user.py` (additive; default null for guests).

## Frontend (in `ui/` Next.js app)

```
ui/app/
├── (auth)/
│   ├── login/page.tsx               # magic-link form + Google button
│   ├── verify/page.tsx              # consumes ?t= and calls /v1/auth/magic-link/verify
│   └── logout/page.tsx
└── account/
    ├── page.tsx                     # profile + danger zone
    ├── preferences/page.tsx
    ├── saved-views/page.tsx
    └── highlights/page.tsx
```

`ui/lib/auth/client.ts` provides `useSession()`, `signIn()`, `signOut()`, `requireSession()`. Implementation wraps fetch with credentials and exposes the optional `User` from `/v1/auth/me`.

## Manual verification

```bash
# Spin up auth-service
docker compose up -d postgres auth-service

# Request a magic link (email is stubbed in dev to stdout)
curl -X POST http://localhost:8005/v1/auth/magic-link/request \
  -H 'content-type: application/json' \
  -d '{"email":"test@example.com"}'

# Copy the printed token, then:
curl -X POST http://localhost:8005/v1/auth/magic-link/verify \
  -H 'content-type: application/json' \
  -d '{"token":"<TOKEN>"}' -i

# Cookies set. /v1/auth/me echoes the user.
curl http://localhost:8005/v1/auth/me -b cookies.txt

# Preferences round-trip
curl -X PUT http://localhost:8005/v1/me/preferences \
  -b cookies.txt -H 'content-type: application/json' \
  -d '{"lang_default":"en","lang_overlay":"sa"}'
```

## Definition of done

- [ ] All Phase A tests pass.
- [ ] All Phase B tests pass.
- [ ] `current_user_optional` available in `jain_kb_common`, imported by at least one other service (data-service) as a smoke test.
- [ ] `account/preferences` page changes the active locale in the UI without a refresh.
- [ ] Account deletion E2E test green.

## Implementation notes

_(to be filled in after merge)_
