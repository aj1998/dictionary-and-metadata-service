# Phase 5 — API + UI for compound gatha identifiers

> **Read first**: phases [`00`](./00_compound_identifiers_overview.md),
> [`03`](./03_envelope_and_apply_compound_nk.md).
>
> **Goal**: expose compound-identifier gathas through the data API and the
> reading UI without breaking single-identifier shastras. The chosen URL
> shape is **comma-encoded values in a single path segment**, mirroring the
> intuitive form `1,2` (adhikaar 1, gatha 2) while keeping the existing
> `/shastras/[nk]/gathas/[number]` route signature.

---

## 1. URL shape

| Shastra | URL today | URL after this phase |
|---|---|---|
| समयसार gatha 8 | `/shastras/समयसार/gathas/8` | unchanged |
| परमात्मप्रकाश adhikaar 1, gatha 2 | n/a | `/shastras/परमात्मप्रकाश/gathas/1,2` |
| परमात्मप्रकाश adhikaar 1, gathas 19-21 (combined) | n/a | `/shastras/परमात्मप्रकाश/gathas/1,19` (each gatha is its own page; navigation chip shows `19-21`) |

Encoding: the path segment is URL-encoded by the browser; the comma stays
literal (RFC 3986 sub-delim). No special escaping needed.

## 2. API layer

**File**: `services/data_api/...` (find the route handling
`GET /shastras/{shastra_nk}/gathas/{gatha_id}`).

### 2.1 Input normalisation

```python
from jain_kb_common.shastra_identifiers import get_identifier_fields

def parse_gatha_path_param(shastra_nk: str, raw: str) -> dict:
    """Map URL path segment to identifier_values dict for DB lookup."""
    fields = get_identifier_fields(shastra_nk, "gatha")
    if not fields:
        return {"__legacy__": raw}        # single-identifier shastra
    parts = raw.split(",")
    if len(parts) != len(fields):
        raise HTTPException(400, f"expected {len(fields)} values for {fields}, got {len(parts)}")
    return dict(zip(fields, parts))
```

### 2.2 NK reconstruction

```python
from jain_kb_common.shastra_identifiers import build_compound_suffix

def gatha_nk_for_request(shastra_nk: str, raw: str) -> str:
    fields = get_identifier_fields(shastra_nk, "gatha")
    if not fields:
        return f"{shastra_nk}:गाथा:{raw}"
    suffix = build_compound_suffix(shastra_nk, parse_gatha_path_param(shastra_nk, raw), kind="gatha")
    if not suffix:
        raise HTTPException(400, "could not build compound NK")
    return f"{shastra_nk}:{suffix}"
```

### 2.3 Response shape additions

The gatha detail response gains an optional `identifier` block:

```json
{
  "natural_key": "परमात्मप्रकाश:अधिकार:1:गाथा:2",
  "gatha_number": "अधिकार:1:गाथा:2",
  "identifier": {
    "fields": [
      { "name": "अधिकार", "label": "अधिकार", "value": "1", "display": "परमात्म-अधिकार" },
      { "name": "गाथा",    "label": "गाथा",    "value": "2" }
    ],
    "compact": "1,2",
    "is_compound": true
  },
  ...
}
```

For legacy shastras, set `"is_compound": false` and emit a single-field array
so the UI can render uniformly.

### 2.4 Update OpenAPI / API docs

- `docs/design/api/data/01_spec.md` — document the new `identifier` block and
  the `compound` URL form.
- `docs/design/api/navigation/01_spec.md` — note compound-aware previous /
  next gatha resolution (lexical sort by identifier-value tuple).

## 3. UI layer

**Folder**: `ui/src/app/[locale]/(reading)/shastras/[nk]/gathas/[number]/`

### 3.1 Route handler

The dynamic `[number]` segment continues to work because Next.js does not
parse commas specially. In `page.tsx`:

```ts
const rawGathaId = decodeURIComponent(params.number);
const identifierResp = await fetchGatha(params.nk, rawGathaId);
```

### 3.2 Breadcrumb / header

Replace the single "गाथा N" chip with a chip per identifier field. For
परमात्मप्रकाश:

```
[ अधिकार 1 — परमात्म-अधिकार ]  >  [ गाथा 2 ]
```

For legacy shastras the breadcrumb is unchanged ("गाथा 8").

### 3.3 Next / previous navigation

The current "next gatha" logic uses `gatha_number` arithmetic. For compound
shastras call a new API endpoint `GET /shastras/{nk}/gathas/{id}/adjacent`
that returns `previous` / `next` resolved server-side via the sorted gatha
index. Avoid client-side compound-aware sorting.

### 3.4 Graph link

`PanelActionsMenu`'s `actionsSourceNk` already uses the canonical Neo4j NK.
Confirm it picks up the compound NK from `gatha.natural_key` without
modification — this should "just work" because the API returns the NK
verbatim.

### 3.5 Translations

`ui/src/i18n/.../reading.json` — add a `gathaBreadcrumb.{field_name}` key
per identifier-field label. Fallback: use the field name verbatim.

## 4. Search / index endpoints

`services/data_api`'s gatha search endpoints (autocomplete, mention-resolution)
must accept the compound form. The simplest approach: maintain the
already-stored full NK string as the canonical search key and let users type
either:
- raw NK form (`अधिकार:1:गाथा:2`), or
- compact form (`1,2`), normalised to NK at query time by `gatha_nk_for_request`.

## 5. Tests

### 5.1 API
- `test_compound_route_resolves_to_correct_pg_row`
- `test_compound_route_400_on_arity_mismatch`
- `test_legacy_route_unchanged`
- `test_adjacent_endpoint_returns_compound_neighbour` (`1,21` → next `2,1`?
  Confirm cross-adhikaar boundary behaviour — return `null` if no next within
  current adhikaar; document this choice in the API spec.)

### 5.2 UI
- Playwright: load `/shastras/परमात्मप्रकाश/gathas/1,2` → page renders, breadcrumb
  shows both chips, content matches API.
- Playwright: load `/shastras/समयसार/gathas/8` → unchanged.
- Snapshot: breadcrumb component for compound vs legacy.

## 6. Implementation notes / done-checklist

- [x] `parse_gatha_path_param` + `gatha_nk_for_request` helpers in API
      (`services/core_service/domains/data/routers/gathas.py`)
- [x] API response carries new `identifier` block
      (`_build_identifier_block` in same file; `is_compound`, `fields`, `compact`)
- [x] `/adjacent` endpoint implemented as `GET /v1/shastras/{nk}/gathas/{raw}/adjacent`
      Returns `{previous, next}` each with `{natural_key, compact, gatha_number}`.
      **Cross-adhikaar navigation is enabled** (next after last gatha in adhikaar 1 is
      first gatha in adhikaar 2). Adjacent list is sorted numerically, not lexically.
- [x] UI breadcrumb renders per-field chips for compound gathas
      (`ui/src/app/[locale]/(reading)/shastras/[nk]/gathas/[number]/page.tsx`)
- [x] UI `GathaPageBottomNav` uses server-fetched adjacent links for compound shastras
      (`ui/src/components/GathaVerseGroup.tsx`)
- [x] API + UI types updated (`ui/src/lib/types.ts`, `ui/src/lib/api/data.ts`)
- [x] 11 API tests green (`tests/services/data/test_compound_gatha_routes.py`)
- [x] Full test suite (1202 tests) green — no regressions
- [ ] Playwright UI tests (deferred — no Playwright setup in current CI)
- [x] Update authoritative docs:
      - `docs/design/api/data/01_spec.md` — compound route + response shape
      - Mark phase 5 ✓ in [`00_compound_identifiers_overview.md`](./00_compound_identifiers_overview.md)

### Diversions from spec

- **`display` field omitted from identifier fields**: For compound shastras, the `adhikaar`
  column in Postgres stores the `identifier_values` dict (not LangText), so the human-readable
  adhikaar name (e.g. "परमात्म-अधिकार") is not readily available from the gatha row alone.
  The `display` key was omitted from identifier field entries. Can be added later via a
  separate adhikaar-heading lookup query.
- **New API prefix `/v1/shastras/{nk}/gathas/{raw}`**: The spec pointed to an existing
  route. A new prefixed route was added alongside the existing `/v1/gathas/{ident}` to
  avoid breaking the legacy NK-based lookup that other code depends on.

## 7. Out of scope

- No admin UI for editing `gatha_identifier` (manual JSON edit only).
- No bulk URL redirect from old legacy URLs (no such URLs exist for
  परमात्मप्रकाश yet).
- Search ranking unchanged.
