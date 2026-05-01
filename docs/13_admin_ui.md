# 13 — Admin UI

Internal control plane for the service. Lives in the same Next.js app as the public UI but under route prefix `/admin/*`. Gated by HTTP basic auth + IP allowlist at the nginx layer for v1. No user accounts.

## Goals

1. Trigger and monitor ingestion runs.
2. Review and approve parsed extracts before they go public.
3. Review and approve AI-generated topic candidates from `cataloguesearch-chat`.
4. Curate synonyms (keyword aliases).
5. Edit the topic graph (add/remove edges).
6. Operate parser configs and inspect logs.

## Page list

| Route | Purpose | Source data |
|---|---|---|
| `/admin` | Dashboard: counts, recent runs, queue depth | metadata + ingestion + dictionary services |
| `/admin/parser-configs` | List / view active parser config files; show checksum + version history | Postgres `parser_configs` |
| `/admin/ingest` | Trigger ingestion (jainkosh letter, nikkyjain shastra, vyakaran shastra); view live progress | Celery + Postgres `ingestion_runs` |
| `/admin/ingest/runs/[run_id]` | Run detail: stats, errors, iterator state, raw HTML browser | Postgres + filesystem |
| `/admin/review-queue` | Pending parsed entities awaiting approval. Bulk approve/reject. | Postgres `ingestion_review_queue` |
| `/admin/review-queue/[id]` | Single entity review — diff vs existing if any, side-by-side preview, blocks visualization | + Mongo |
| `/admin/topic-candidates` | Pending AI-generated topic candidates from chat | Postgres `topic_candidates` |
| `/admin/topic-candidates/[id]` | Approve as new / merge / reject; chunk previews via cataloguesearch chunk-fetch | + cataloguesearch API |
| `/admin/keywords` | Search keywords; edit aliases | Postgres `keywords` + `keyword_aliases` |
| `/admin/keywords/[nk]` | Aliases editor (add/remove), "scrape now" if `unscraped` stub | + Neo4j |
| `/admin/topics` | Search topics; manage edges | Postgres `topics` + Neo4j |
| `/admin/topics/[nk]` | Edges editor (add/remove IS_A, PART_OF, RELATED_TO); mentions list (add manual mention) | Neo4j + Postgres `topic_mentions` |
| `/admin/graph` | Graph stats, full resync trigger, node/edge counts by label/type | Neo4j |
| `/admin/logs/queries` | Recent query logs (top tokens, zero-match queries, latency p50/p95) | Postgres `query_logs` |
| `/admin/ocr` | OCR pages awaiting review (placeholder for v1 stub) | Mongo `ocr_pages` |

## Wireframes (textual)

### `/admin/review-queue`
```
[ Source: ▼ all | jainkosh | nikkyjain | vyakaran ]
[ Status: ▼ pending | approved | rejected ] [ Run: ▼ all | <run_id> ]

Bulk: [Approve selected]  [Reject selected]  [Reason: ____ ]

| ☐ | Entity | Source | Run | Diff | Created     | Action  |
| ☐ | jainkosh:आत्मा | jainkosh | run-2026-05-01-aa | NEW         | 12:01 | [View] |
| ☐ | jainkosh:पर्याय | jainkosh | run-2026-05-01-aa | UPDATE (3♯) | 12:02 | [View] |
```

### `/admin/review-queue/[id]` (single entity)
- Top: entity natural_key, type, source, run id.
- Two columns: **Proposed** vs **Existing** (existing = "—" if NEW).
- Tabbed sections:
  - **Postgres fragment**: row diff (yaml view).
  - **Mongo fragment**: rendered preview (JainKosh-style) + raw JSON tab.
  - **Graph fragment**: graphviz/d3 mini-render of nodes & edges.
- Buttons: `Approve`, `Approve and continue to next`, `Reject` (requires reason).

### `/admin/keywords/[natural_key]`
```
Keyword: आत्मा   [Postgres id: ...]   [Source: jainkosh]   [Last updated: 2026-05-01]

Aliases:
  ▸ आतम       (jainkosh_redirect)  [×]
  ▸ आत्मन्     (jainkosh_redirect)  [×]
  ▸ ____      [Add alias]   source: ▼ admin

Topics from this keyword:
  • जैनकोष:आत्मा:बहिरात्मादि-3-भेद  [open]
  ...

Graph neighbors:
  IS_A → ...  PART_OF → ...  RELATED_TO ↔ ...
```

### `/admin/topic-candidates/[id]`
```
Proposed: "द्रव्य गुण पर्याय भेद"  (from chat candidate cs-tc-887)
Associated keywords: [पर्याय] [गुण] [द्रव्य]
LLM explanation: ...
Cataloguesearch chunks:
  • cs-chunk-44231  [Preview]
  • cs-chunk-12089  [Preview]

Existing topic match? → "जैनकोष:द्रव्य:द्रव्य-गुण-पर्याय-भेद" (similarity 0.96)
[ Approve as NEW topic ]   [ Merge into match ]   [ Reject ]
```

## Backend support endpoints

These are the admin-facing endpoints exposed by metadata-service / dictionary-service / query-service. UI calls them with the basic-auth header.

```
GET    /v1/admin/ingest/runs                              list runs
POST   /v1/admin/ingest/runs                              start a run (source, params)
POST   /v1/admin/ingest/runs/{id}/cancel
GET    /v1/admin/ingest/review-queue?status=pending&run_id=
POST   /v1/admin/ingest/review-queue/{id}/approve
POST   /v1/admin/ingest/review-queue/{id}/reject

GET    /v1/admin/topic-candidates?status=pending
POST   /v1/admin/topic-candidates/{id}/approve  (body: {mode: 'new'|'merge', merge_target_id?})
POST   /v1/admin/topic-candidates/{id}/reject

POST   /v1/admin/keywords/{id}/aliases
DELETE /v1/admin/keywords/{id}/aliases/{alias_id}
POST   /v1/admin/keywords/scrape                          {natural_key} → triggers single-keyword JainKosh fetch

POST   /v1/admin/topics/{id}/edges
DELETE /v1/admin/topics/{id}/edges/{edge_id}
POST   /v1/admin/topics/{id}/mentions
DELETE /v1/admin/topics/{id}/mentions/{mention_id}

POST   /v1/admin/graph/resync                             {scope: 'full'|'keyword'|'topic', id?}

GET    /v1/admin/logs/queries?since=&caller=
GET    /v1/admin/stats                                    dashboard counters
```

## Auth

```
location /admin/ {
    auth_basic           "Restricted";
    auth_basic_user_file /etc/nginx/.htpasswd;
    allow 192.168.0.0/16;
    allow 10.0.0.0/8;
    deny all;
    proxy_pass http://nextjs:3000/admin/;
}

location /v1/admin/ {
    auth_basic           "Restricted";
    auth_basic_user_file /etc/nginx/.htpasswd;
    allow 192.168.0.0/16;
    allow 10.0.0.0/8;
    deny all;
    # proxy to the relevant service based on path prefix
}
```

App-side, every admin route validates the basic auth header again as defense-in-depth.

## Frontend stack notes

- Next.js 14 App Router.
- Pages live under `ui/app/admin/`.
- Tailwind for layout, **shadcn/ui** for tables / dialogs / forms.
- React Server Components for data fetching where possible; client components for interactive editors (alias editor, edge editor).
- Realtime progress for ingest runs: Server-Sent Events (`text/event-stream`) from the orchestrator's status endpoint, polled fallback every 5s.
- Hindi-first: admin UI labels in Hindi by default with English fallback (`next-intl`).

## Folder layout

```
ui/app/admin/
├── layout.tsx              admin shell (sidebar, top bar)
├── page.tsx                dashboard
├── parser-configs/
├── ingest/
│   ├── page.tsx
│   └── runs/[run_id]/page.tsx
├── review-queue/
│   ├── page.tsx
│   └── [id]/page.tsx
├── topic-candidates/
│   ├── page.tsx
│   └── [id]/page.tsx
├── keywords/
│   ├── page.tsx
│   └── [nk]/page.tsx
├── topics/
│   ├── page.tsx
│   └── [nk]/page.tsx
├── graph/page.tsx
├── logs/queries/page.tsx
└── ocr/page.tsx
```

## Definition of Done

- [ ] All listed routes render without errors against a seeded local stack.
- [ ] Review-queue flow: trigger ingest → see pending row → approve → row turns into real DB rows + graph nodes.
- [ ] Topic-candidates flow: seed candidate → approve as new → topic + mentions + graph edges appear.
- [ ] Alias add/remove reflected in Postgres and Neo4j within 5s of action.
- [ ] Basic auth enforced at nginx and re-validated app-side.
- [ ] Hindi labels default; English available via locale switcher.
