# 07 — API Integration

Backend endpoints already specified in `../api/data/01_spec.md`,
`../api/navigation/01_spec.md`, `../api/metadata/01_spec.md`, and
`../07_api_query_service.md`. This file maps each UI surface to the calls
that drive it. The UI never talks to the databases directly — only via
the four FastAPI services.

## 1. Service base URLs

Resolved at build time from env. In Docker Compose the names are the DNS
hostnames; in `pnpm dev` they fall back to `localhost`.

| Logical name | Env var | Default (dev) |
|---|---|---|
| metadata-service | `METADATA_SVC_URL` | `http://localhost:8001` |
| data-service | `DATA_SVC_URL` | `http://localhost:8002` |
| navigation-service | `NAV_SVC_URL` | `http://localhost:8003` |
| query-service | `QUERY_SVC_URL` | `http://localhost:8004` |

All thin clients live under `ui/lib/api/{metadata,data,navigation,query}.ts`.

## 2. Page → endpoint mapping

| Route | Server-side calls | Notes |
|---|---|---|
| `/` | `data:/v1/activity/recent`, `data:/v1/stats/counts` | ISR 60 s |
| `/shastras` | `metadata:/v1/shastras?...` | ISR 60 s |
| `/shastras/[nk]` | `metadata:/v1/shastras/{nk}`, `data:/v1/shastras/{nk}/teekas`, `nav:/v1/preview/{nk}?hops=1` | ISR 60 s |
| `/shastras/[nk]/gathas/[number]` | `data:/v1/gathas/{nk}`, `data:/v1/gathas/{nk}/related-topics`, `data:/v1/gathas/{nk}/related-keywords` | ISR 60 s |
| `/dictionary` | `data:/v1/keywords/letters`, `data:/v1/keywords/recent` | ISR 60 s |
| `/dictionary/letters/[letter]` | `data:/v1/keywords?letter=…` | ISR 60 s |
| `/dictionary/[nk]` | `data:/v1/keywords/{nk}`, `nav:/v1/preview/{nk}?hops=1` | ISR 60 s |
| `/topics` | `data:/v1/topics?...` | ISR 60 s |
| `/topics/[nk]` | `data:/v1/topics/{nk}`, `nav:/v1/topics/{nk}/neighbors` | ISR 60 s |
| `/search` | `query:POST /v1/graphrag/topics` `{ caller: "public-ui" }` | dynamic (`revalidate=0`) |
| `/graph` | client-only via `useGraphState`; initial fetch `nav:/v1/landing` or `nav:/v1/expand/{nk}?depth=2` | client-rendered after first paint |
| `/about`, `/feedback` | none / Next route handler | static |

## 3. Graph page client calls

Implemented in `ui/lib/api/navigation.ts` (browser fetch wrappers).

| Action | Call |
|---|---|
| Initial load | `GET nav:/v1/landing` |
| Deep link `?node=<nk>` | `GET nav:/v1/expand/{nk}?depth={depth}` |
| Click-to-expand | `GET nav:/v1/expand/{nk}?depth={depth}` |
| View All Connections | re-run expand with `depth+1` |
| Open in graph from detail page | navigates to `/graph?node=<nk>&depth=2`, which triggers the call above |

Every navigation-service response carries:

```jsonc
{
  "nodes": [
    { "nk": "...", "kind": "topic", "title_hi": "...", "title_en": "...",
      "meta": { ...optional }, "degree": 14 }
  ],
  "edges": [
    { "id": "e-...", "src": "<nk>", "dst": "<nk>", "kind": "RELATED_TO",
      "weight": 0.7 }
  ],
  "focus_nk": "...",
  "depth": 2
}
```

The client merges these into the store (de-duped by `nk` / `id`).
Force-sim positions are preserved for existing nodes; new nodes are
seeded at the focus node's position so they "burst out".

## 4. Details panel content fetch

When a node is selected, the store already has its title and degree.
For the full panel (description, stat tiles, connected list), fire:

`GET data:/v1/entity/{kind}/{nk}/detail` (composite endpoint;
returns description, stats, and a first-page list of connected entities).

For an edge selection, no extra fetch is needed — kind + endpoints come
from the edge object already in the store.

## 5. Search

Calls `query-service` as specified. The result shape:

```jsonc
{
  "results": [
    { "topic_nk": "...", "title_hi": "...",
      "overlap": { "matched": 2, "total": 3 },
      "score": 25.0,
      "matched_tokens": ["पर्याय", "गुण"],
      "excerpt": "...",
      "mentions": [{ "kind": "gatha", "ref": "pravachansaar:093" }] }
  ]
}
```

Mentions render as clickable chips that link to the canonical detail
page.

## 6. Caching headers

Set on the Next response from each route:

```
Cache-Control: public, s-maxage=300, stale-while-revalidate=600
```

The only exception is `/search` (`Cache-Control: no-store`).

## 7. Error handling

Service errors map to UI states:

| Backend response | UI behavior |
|---|---|
| `4xx` (e.g., 404 on detail page) | Render the page's not-found component (Hindi + English). |
| `5xx` | Render the page's error component with retry button. Log to Sentry. |
| Network/abort | Same as 5xx, but no Sentry log. |

## 8. Hindi-safe URL params

All `nk` values are Devanagari-bearing. They are stored URL-encoded
(`encodeURIComponent`) and only decoded for display. The API clients do
this encoding centrally so route handlers and components never have to.
