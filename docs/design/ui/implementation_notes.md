# Implementation Notes - UI

## Phase 0:
    
    Phase 0 deliverables at ui/:
    
    ┌──────────────────────┬──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┬──────┐
    │ Step │ File(s)│ Done │
    ├──────────────────────┼──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┼──────┤
    │ 0.1 Next.js scaffold │ ui/ — Next.js 16, Tailwind 4, shadcn (Button, Card, Switch, Tabs, Tooltip, Pagination, Sheet, Popover, Separator, Badge) │ ✓    │
    ├──────────────────────┼──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┼──────┤
    │ 0.2 CSS token layer  │ src/styles/theme.css — all 30+ CSS custom properties from 01_design_system.md                                            │ ✓    │
    ├──────────────────────┼──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┼──────┤
    │ 0.3 Tailwind config  │ src/app/globals.css — @theme inline block mapping every token to a Tailwind utility                                      │ ✓    │
    ├──────────────────────┼──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┼──────┤
    │ 0.4 Fonts            │ src/app/layout.tsx — Noto_Serif_Devanagari + Inter via next/font, --font-serif-hindi / --font-sans variables             │ ✓    │
    ├──────────────────────┼──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┼──────┤
    │ 0.5 Global CSS       │ src/app/globals.css — body uses --background + font-serif-hindi; @keyframes shimmer + prefers-reduced-motion override    │ ✓    │
    ├──────────────────────┼──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┼──────┤
    │ 0.6 next-intl        │ src/i18n/routing.ts, src/i18n/request.ts, src/proxy.ts, messages/hi.json + messages/en.json (all chrome strings)         │ ✓    │
    ├──────────────────────┼──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┼──────┤
    │ 0.7 Devanagari utils │ src/lib/format/devanagari.ts — toDevanagariNumerals, normalizeNFC, minGraphemeLength                                     │ ✓    │
    └──────────────────────┴──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┴──────┘
    
    Notable adaptation: Next.js 16 (vs spec's Next.js 14) renamed middleware.ts → proxy.ts, and Tailwind 4 uses CSS-only @theme inline instead of tailwind.config.ts
Both changes are transparent to future phases —
    all token names and Tailwind classes work identically.
    
    Build passes cleanly (pnpm build — no errors, no warnings). The checkpoint criterion (correct background colour #F7F7F8, tokens resolve) is satisfied.

### Tests:

- src/lib/format/devanagari.test.ts -> toDevanagariNumerals (digits, multi-digit, large), normalizeNFC (idempotent, NFD→NFC, ASCII), minGraphemeLength (ASCII, Devanagari conjuncts, empty)
- src/lib/format/messages.test.ts -> hi.json and en.json have identical leaf-key sets; neither is empty
- src/styles/theme.test.ts -> Every required CSS token is declared in theme.css; accent/background/category hex values match the spec exactly

Run with pnpm test (single pass) or pnpm test:watch (interactive).

---

## Phase 1:
    
    ┌─────────────────────────────────┬──────────────────────────────────┬────────┐
    │Task                             │ File                             │ Status │
    ├─────────────────────────────────┼──────────────────────────────────┼────────┤
    │ 1.1 TopBar                      │ src/components/TopBar.tsx        │ ✅ │
    ├─────────────────────────────────┼──────────────────────────────────┼────────┤
    │ 1.2 BreadcrumbBar               │ src/components/BreadcrumbBar.tsx │ ✅ │
    ├─────────────────────────────────┼──────────────────────────────────┼────────┤
    │ 1.3 Footer                      │ src/components/Footer.tsx        │ ✅ │
    ├─────────────────────────────────┼──────────────────────────────────┼────────┤
    │ 1.4a Shell A — Graph            │ src/app/graph/layout.tsx         │ ✅ │
    ├─────────────────────────────────┼──────────────────────────────────┼────────┤
    │ 1.4b Shell B — Content          │ src/app/(content)/layout.tsx     │ ✅ │
    ├─────────────────────────────────┼──────────────────────────────────┼────────┤
    │ 1.4c Shell C — Reading          │ src/app/(reading)/layout.tsx     │ ✅ │
    ├─────────────────────────────────┼──────────────────────────────────┼────────┤
    │ 1.5 Skeleton                    │ src/components/Skeleton.tsx      │ ✅ │
    ├─────────────────────────────────┼──────────────────────────────────┼────────┤
    │ 1.6 Root layout                 │ src/app/layout.tsx               │ ✅ │
    ├─────────────────────────────────┼──────────────────────────────────┼────────┤
    │ LocaleSwitch (needed by Footer) │ src/components/LocaleSwitch.tsx  │ ✅ │
    └─────────────────────────────────┴──────────────────────────────────┴────────┘
    
    Key decisions:

    - TopBar is a 'use client' component mounted in the root layout — it derives activeRoute from usePathname() internally
    - Shell A (graph) has no footer; Shells B and C include the Footer
    - At < xl (1280px), the graph left pane hides; at < 1200px, nav items शस्त्र/विषय/प्रतिक्रिया fold into a "More ▾" popover; at < 768px, the entire nav moves into an off-canvas Sheet drawer
    - The old app/page.tsx was replaced by app/(content)/page.tsx
    - src/lib/nav.ts — extracted isNavActive, truncateLabel, and all three nav item arrays into a shared module, so TopBar and BreadcrumbBar import from it instead of defining their own copies.
    
### Tests:

    src/lib/nav.test.ts — 19 tests across three suites:
    
    ┌───────────────┬────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
    │ Suite         │ What it covers                                                                                                                 │
    ├───────────────┼────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
    │ isNavActive   │ Exact / match, prefix matching for sub-routes, false-positive prevention (/graph-preview ≠ /graph), trailing-slash edge case   │
    ├───────────────┼────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
    │ truncateLabel │ Under/at/over limit, custom max, ellipsis shape and length                                                                     │
    ├───────────────┼────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
    │ nav item data │ Item counts, PRIMARY+MORE = ALL, unique routes, Devanagari labels non-empty, every labelKey maps to a real hi.json nav.* entry │

---
## Bug fix: locale routing (applied after Phase 3)

**Symptom:** `localhost:3000/en` returned 404 despite next-intl being configured.

**Root cause:** next-intl with URL-based locale switching (`localePrefix: "as-needed"`) requires an `src/app/[locale]/` folder so Next.js App Router can capture the locale segment from the URL. Without it, `/en` has no matching page component. The proxy.ts file itself was correct — Next.js 16 did rename `middleware.ts` → `proxy.ts` — but the `[locale]` folder structure was never created.

**Changes made:**

- Created `src/app/[locale]/layout.tsx` — locale shell: validates locale via `hasLocale()`, calls `getMessages()`, mounts `NextIntlClientProvider` and `TopBar`. Calls `notFound()` for unrecognised locales.
- Moved all route files under `src/app/[locale]/`:
  - `(content)/layout.tsx` + `(content)/page.tsx` (Shell B — homepage)
  - `(reading)/layout.tsx` (Shell C — reading view)
  - `graph/layout.tsx` + `graph/page.tsx` (Shell A — graph)
  - `dev/page.tsx` (component gallery)
- Simplified `src/app/layout.tsx` to a pure html/body shell (fonts + `lang` attribute via `getLocale()`). `NextIntlClientProvider` and `TopBar` moved to locale layout.

**Route table after fix:**

```
/[locale]        → homepage (Shell B)
/[locale]/dev    → component gallery
/[locale]/graph  → graph shell (Shell A)
```

Proxy (Middleware) row confirms next-intl locale routing is active.

**URL behaviour** (`localePrefix: "as-needed"`, defaultLocale `hi`):
- `localhost:3000/` → Hindi (no prefix for default locale)
- `localhost:3000/en` → English

---
## Bug fix: locale-aware navigation + stub pages (applied after Phase 3)

**Symptom:** Nav links from `/en` dropped the locale prefix (clicking शब्दकोश went to `/dictionary` not `/en/dictionary`); active-state highlight never fired on `/en/...` routes; `/en/dictionary` and all other nav routes returned 404.

**Root causes:**
1. `TopBar` imported `Link`, `usePathname`, `useRouter` from `next/navigation`. Next.js's own versions are not locale-aware: `usePathname()` returns the full path including the locale prefix (so `/en/dictionary` never matched `/dictionary` in `isNavActive`), and `Link` never prepends the locale segment.
2. Stub pages for nav routes (dictionary, about, shastras, topics, feedback) were never created — so even correct locale-prefixed URLs returned 404.

**Changes made:**
- Added `src/i18n/navigation.ts` — exports locale-aware `Link`, `redirect`, `usePathname`, `useRouter` via `createNavigation(routing)` from next-intl. These automatically strip the locale prefix from `usePathname()` output and prepend it on `Link` hrefs.
- Updated `src/components/TopBar.tsx` to import `Link`, `usePathname`, `useRouter` from `@/i18n/navigation` instead of `next/navigation`.
- Created stub pages (Shell B content shell) for all nav routes:
  - `src/app/[locale]/(content)/dictionary/page.tsx`
  - `src/app/[locale]/(content)/about/page.tsx`
  - `src/app/[locale]/(content)/shastras/page.tsx`
  - `src/app/[locale]/(content)/topics/page.tsx`
  - `src/app/[locale]/(content)/feedback/page.tsx`

**Nav label language:** Nav labels always render in Hindi (Devanagari) regardless of locale — this is by design for a Jain scripture application. The `locale` prop on `TopBar` is reserved for future phase use (e.g. aria attributes, locale-specific formatting).

---
## Phase 2:
    
    ┌─────────────────────────────────────┬───────────────────────────────────────────────────────────────────────────────────────────────────────┐
    │File                                 │ Component │
    ├─────────────────────────────────────┼───────────────────────────────────────────────────────────────────────────────────────────────────────┤
    │ src/lib/types.ts                    │ EntityKind type shared across components│
    ├─────────────────────────────────────┼───────────────────────────────────────────────────────────────────────────────────────────────────────┤
    │ src/lib/icons.ts                    │ Reserved icon re-exports (all 20 icons from 01_design_system.md §6)│
    ├─────────────────────────────────────┼───────────────────────────────────────────────────────────────────────────────────────────────────────┤
    │ src/components/BadgeChip.tsx        │ Entity pill — 4 kinds × 2 sizes (sm/md), correct category colors│
    ├─────────────────────────────────────┼───────────────────────────────────────────────────────────────────────────────────────────────────────┤
    │ src/components/StatTile.tsx         │ Stat card with Devanagari numerals, text-h1 count, muted uppercase label│
    ├─────────────────────────────────────┼───────────────────────────────────────────────────────────────────────────────────────────────────────┤
    │ src/components/StatTileRow.tsx      │ 3-up flex row of StatTiles with 12 px gap│
    ├─────────────────────────────────────┼───────────────────────────────────────────────────────────────────────────────────────────────────────┤
    │ src/components/ConnectedItemRow.tsx │ Badge + title + chevron row; renders as <a> when href given, <button> otherwise; hover accent chevron │
    ├─────────────────────────────────────┼───────────────────────────────────────────────────────────────────────────────────────────────────────┤
    │ src/components/PrimaryCTA.tsx       │ 44 px red CTA button, Hindi + English label, right Bookmark icon, hover darkens│
    ├─────────────────────────────────────┼───────────────────────────────────────────────────────────────────────────────────────────────────────┤
    │ src/components/ListCards.tsx        │ KeywordCard, TopicCard, GathaTile — white surface, hover lift, Devanagari count, arrow│
    ├─────────────────────────────────────┼───────────────────────────────────────────────────────────────────────────────────────────────────────┤
    │ src/app/dev/page.tsx                │ Checkpoint 2 gallery — all components in all states at /dev│
    └─────────────────────────────────────┴───────────────────────────────────────────────────────────────────────────────────────────────────────┘
    
    LocaleSwitch already existed from Phase 1 and is correct. TypeScript compiles clean and the production build succeeds with /dev in the route table
    
### Tests:
    
src/components/BadgeChip.test.ts (18 tests)
- BADGE_DEFAULT_LABELS — covers all 4 EntityKinds, non-empty Hindi/English labels, Devanagari script validation, exact label spot-checks
- BADGE_CAT_CLASSES — covers all 4 kinds, bg-cat-* prefix invariant, uniqueness, exact class name spot-checks

src/lib/icons.test.ts (3 tests)
- All 20 reserved icons from 01_design_system.md §6 are exported
- Each export is a renderable React component (handles both plain functions and forwardRef objects)
- No extra icons — export set matches the reserved set exactly
    
    BadgeChip.tsx had its two data constants renamed to BADGE_DEFAULT_LABELS / BADGE_CAT_CLASSES and exported so the tests can import them without rendering any JSX.

---
## Phase 3:

New files created: 
- ui/src/lib/api/_fetch.ts — apiFetch<T> base wrapper with ApiError class; Devanagari-safe path encoding (splits on ? so query strings aren't encoded) 
- ui/src/lib/api/metadata.ts — getShastras, getShastra, getShastraTeekas (port 8001) 
- ui/src/lib/api/data.ts — 12 functions: activity, stats, entity detail, keywords, topics, gathas (port 8002)
- ui/src/lib/api/navigation.ts — getNavLanding, expandNode, getPreview, getTopicNeighbors (port 8003)
- ui/src/lib/api/query.ts — searchTopics via POST, caller defaults to 'public-ui' (port 8004)

Updated: 
- ui/src/lib/types.ts — expanded from 1 line to all shared types: EdgeKind (11 variants), GraphNode/Edge/Payload, Paginated<T>, and all domain response shapes

### Tests
- 5 test files covering success paths, error paths (ApiError with correct status), URL construction, and Devanagari encoding 

From regressions -

- nav.test.ts (+1 suite) -> locale-prefixed paths fail isNavActive -> Documents the contract: isNavActive must receive the locale-stripped path, proving why next-intl's usePathname is required
- i18n/routing.test.ts -> locales, defaultLocale, localePrefix, localeCookie -> Locks the config that makes [locale] folder mandatory — changing defaultLocale or localePrefix must be an intentional decision
- i18n/navigation.test.ts -> 4 exports exist and are functions -> next-intl/navigation is mocked (it pulls in next/navigation which isn't resolvable in Node) — verifies the destructuring in navigation.ts is correct
- lib/locale-pages.test.ts -> every nav route has a page file on disk -> Acts as a manifest: adding a nav item in nav.ts without a matching page.tsx under [locale]/ will fail here

---
## Phase 4:

Completed in two parts:

1) Previously implemented UI modules:
- `ui/src/components/NodeCard.tsx` — 4 entity kinds and 5 visual states (`resting`, `hover`, `selected`, `faded`, `pinned`), plus exported `NODE_KIND_META` for deterministic tests.
- `ui/src/components/RelationConnector.tsx` — static cubic Bézier connector with endpoint circles and midpoint pill label; exported `EDGE_LABELS` and `EDGE_TOOLTIPS`.
- `ui/src/components/CategoryFilterList.tsx` — category toggles, layout radio group, depth stepper (1–4), reset action; exported `CATEGORY_DATA`.
- `ui/src/app/[locale]/graph/useForceSimulation.ts` — D3-force hook that updates SVG/foreignObject refs directly per tick; exported pure `buildBezierPath`.
- `ui/src/app/[locale]/graph/ZoomControls.tsx` — zoom in/out + fit controls.
- `ui/src/app/[locale]/graph/GraphCanvas.tsx` — dotted grid, pan/zoom camera, memoized edge/node subtree for force-sim compatibility.
- `ui/src/app/[locale]/graph/layout.tsx` — left pane mounts `CategoryFilterList` with local Phase 4 state.
- `ui/src/app/[locale]/graph/page.tsx` — demo graph with 5 nodes and 4 edges.

2) Completed now (remaining deliverables):
- Added the 4 planned test files:
  - `ui/src/components/NodeCard.test.ts`
  - `ui/src/components/RelationConnector.test.ts`
  - `ui/src/components/CategoryFilterList.test.ts`
  - `ui/src/app/[locale]/graph/useForceSimulation.test.ts`
- Updated this document with the Phase 4 architecture notes and verification.
- Build verification run: `pnpm build && pnpm test` in `ui/`.

### Phase 4 architecture decisions

- `React.memo` boundary (`EdgesAndNodes`) isolates camera React state from force-simulation-managed DOM refs. Camera updates re-render only transform wrappers/patterns, not the edge/node DOM subtree that D3 mutates.
- Grid pattern is screen-space driven via `<pattern>` transform offsets (`camera.x % tileSize`, `camera.y % tileSize`), with dot radius clamped to `[0.75, 1.5]` so dots remain readable across zoom levels.
- `RelationConnector` remains a standalone static component for gallery/static previews. `GraphCanvas` renders raw edge SVG primitives (`path`, two `circle`, `foreignObject`) so each piece can be registered and updated directly by the simulation hook.
- `useForceSimulation` exposes `restart` (and registration handlers) through stable `useRef(...).current` function identities, avoiding memo-boundary invalidation during re-execution.
- `accumulateEdgeRef` registers each edge part independently and only calls `registerEdge` when all 4 elements exist, ensuring complete edge handles before simulation ticks.
- `CategoryFilterList` state is intentionally local in Phase 4; planned lift to Zustand graph state is deferred to Phase 5.

### Phase 4 tests added

- `NodeCard.test.ts`
  - Verifies `NODE_KIND_META` covers all 4 `EntityKind`s.
  - Ensures each metadata entry has non-empty Hindi/English labels, `catVar` prefix `var(--cat-`, and renderable icon function.
  - Spot-checks `shastra` Hindi label and category variable.
- `RelationConnector.test.ts`
  - Verifies `EDGE_LABELS` covers all 11 `EdgeKind` values.
  - Ensures `EDGE_TOOLTIPS` keys exactly match `EDGE_LABELS`.
  - Ensures every label/tooltip is non-empty.
  - Spot-checks `IS_A` and `RELATED_TO` Hindi labels.
- `CategoryFilterList.test.ts`
  - Verifies `CATEGORY_DATA` has exactly 4 items.
  - Ensures required fields exist and `catVar` has `var(--cat-` prefix.
  - Ensures all 4 `EntityKind`s are covered without duplicates.
- `useForceSimulation.test.ts`
  - Verifies `buildBezierPath` path-string shape.
  - Verifies horizontal anchors (`a1`, `a2`) for left-to-right edges.
  - Verifies angle clamp range `[-20, +20]`.
  - Verifies midpoint coordinates are defined.

### Manual UI verification checklist for phase 4 (/[locale]/graph):

1. Dotted grid renders, pans with drag, and scales correctly on zoom.
2. Node cards show all visual states (selected/faded/pinned/rest/hover behavior).
3. Edges render as Bézier with endpoint circles and midpoint pill labels.
4. Active edge uses accent styling; inactive edges use muted graph-edge color.

---
## Bug fix: graph bootstrap blocked by cross-origin API calls (applied after Phase 5)

**Symptom:** `/[locale]/graph` showed empty state ("No graph data yet") even when navigation service logs showed:
`GET /v1/landing 200` with records returned.

**Root cause:** Phase 3 API clients called service ports directly from the browser (`http://localhost:8001..8004`). In browser runtime this introduces cross-origin restrictions; requests can still reach backend, but response access can fail in UI runtime and boot falls back to empty graph state.

**Changes made:**
- Added Next.js rewrites in `ui/next.config.ts`:
  - `/api/metadata/:path* -> METADATA_SVC_URL (default http://localhost:8001)`
  - `/api/data/:path* -> DATA_SVC_URL (default http://localhost:8002)`
  - `/api/navigation/:path* -> NAV_SVC_URL (default http://localhost:8003)`
  - `/api/query/:path* -> QUERY_SVC_URL (default http://localhost:8004)`
- Updated UI API base URLs to same-origin proxy paths:
  - `metadata.ts`: `/api/metadata`
  - `data.ts`: `/api/data`
  - `navigation.ts`: `/api/navigation`
  - `query.ts`: `/api/query`
- Updated API unit tests to assert rewritten same-origin URLs.

**Operational alignment:**
- Navigation service default Neo4j database is set to `neo4j` in `services/navigation_service/config.py` to match the expected default graph DB name.
5. Force simulation starts and settles automatically.
6. Left filter pane shows 4 category toggles, layout radios (only Force enabled), depth stepper clamped 1–4, and reset action.
7. Zoom controls: plus/minus and fit/reset behavior work.
8. Empty state appears when nodes=[].
9. Responsive behavior: left pane hidden below xl, canvas expands; reduced-motion doesn’t break functionality.

## Phase 5:

Implemented Phase 5 graph interactivity/state in `ui/` with Zustand-backed graph state, URL sync, live expansion, and details panel rendering.

### Files added
- `ui/src/lib/store/graphStore.ts`
  - Added `useGraphStore` Zustand store with Phase 5 state + actions:
    - selection (`selectNode`, `selectEdge`, `clearSelection`)
    - pinning (`togglePin`)
    - expansion (`expandFromNode`) with merge/de-dupe by `nk`/`id`
    - category visibility / depth / layout / camera setters
    - reset + seeded payload merge (`seedFromPayload`)
  - Added 300-node guard in `expandFromNode` with confirmation gate.
  - Added `loading`/`lastError` for error visibility.

- `ui/src/lib/store/graphUrlState.ts`
  - Added URL parser/serializer helpers:
    - `parseGraphQuery(...)` for `node`, `edge`, `depth`, `cat`
    - `buildGraphQuery(...)` for debounced URL writeback

- `ui/src/components/DetailsPanel.tsx`
  - Implemented node-mode and edge-mode details panel:
    - Node mode: badge, title, stats row, description, related rows, expand action, bottom CTA
    - Edge mode: relation pill, src→dst header, edge kind + description, two connected rows
  - Desktop: right panel (380px); Mobile: bottom sheet (75vh)
  - Node detail fetch via `data.getEntityDetail(kind, nk)` on selection change

### Files updated
- `ui/src/app/[locale]/graph/page.tsx`
  - Replaced static Phase 4 demo data with store-driven graph.
  - Boot sequence:
    - reads URL params (`node`, `edge`, `depth`, `cat`)
    - applies depth/category visibility
    - `?node` path triggers `expandFromNode`
    - no `?node` path seeds from `navigation.getNavLanding()`
  - Added URL sync (500ms debounce, `history.replaceState`).
  - Added keyboard `Esc` to clear selection.
  - Added SR-only linear graph nav tree (`aria-label="ग्राफ लीनियर दृश्य"`).
  - Wired interaction handlers (node click/double-click, edge click, canvas click clear, pin toggle).

- `ui/src/app/[locale]/graph/layout.tsx`
  - Replaced local Phase 4 filter state with store-backed filter state.
  - Wired right `DetailsPanel` into shell.

- `ui/src/app/[locale]/graph/GraphCanvas.tsx`
  - Added callbacks:
    - `onEdgeClick`
    - `onCanvasClick`
    - `onNodePinToggle`
  - Edge groups now dispatch click selection.
  - Empty-canvas click clears selection before drag.

- `ui/src/components/CategoryFilterList.tsx`
  - Added controlled layout props:
    - `layout`
    - `onLayoutChange`
  - Radio group now fully controlled by graph store.

### Tests added (TDD)
- `ui/src/lib/store/graphStore.test.ts`
  - Seed merge + selected state
  - Pin toggling behavior
  - `expandFromNode` de-dupe + expanded marker
  - 300-node guard cancel path

- `ui/src/lib/store/graphUrlState.test.ts`
  - URL parse for node/depth/category
  - depth bound clamp and invalid cat filtering
  - stable query serialization

### Verification commands run
- `cd ui && pnpm test -- src/lib/store/graphStore.test.ts src/lib/store/graphUrlState.test.ts`
- `cd ui && pnpm build` (successful after running with network permission due Google Fonts fetch)
- `cd ui && pnpm test`

### Notes / implementation deltas
- The Phase 5 keyboard map is partially implemented (`Esc`). Other shortcuts (`f`, `+/-`, `0`, arrows, `/`, `Cmd+K`, `Space+drag`) remain to be wired end-to-end.
- Category-off behavior currently filters hidden categories from canvas data, which effectively hides those nodes/edges without re-simulation control flags.
- Expand error visuals/toasts and node shake animation are not yet implemented; errors are logged and kept in store `lastError`.

### Manual UI checks for phase 5:

1. Open /en/graph and /graph; verify graph seeds when no ?node.
2. Open /graph?node=<nk>&depth=3&cat=topic; verify selected node expands and category/depth reflect URL.
3. Click a node; details panel opens with title, stats, description, related rows, CTA.
4. Click edge pill; edge details mode shows relation + source/target rows.
5. Click empty canvas; selection clears and panel closes.
6. Toggle category switches; matching nodes/edges disappear/reappear.
7. Change depth stepper; click unexpanded node; URL updates after ~500ms debounce.
8. Pin/unpin from node pin icon and verify pin state persists in current session.
9. On mobile width (<1100), verify details open as bottom sheet.
10. Inspect DOM for SR-only nav: nav[aria-label="ग्राफ लीनियर दृश्य"] contains visible-node links.

---
## Bug fix: details panel used non-existent composite data-service endpoint

**Symptom:** Selecting graph nodes (notably keyword nodes like `वस्तु`) triggered requests such as:
`GET /v1/entity/keyword/{nk}/detail` and resulted in `404 Not Found` from `data-service`.

**Root cause:** UI `getEntityDetail(...)` still followed a planned composite endpoint contract from phase docs, but backend exposes per-entity endpoints:
- `data-service`: `/v1/keywords/{nk}`, `/v1/topics/{nk}`, `/v1/gathas/{nk}`
- `metadata-service`: `/v1/shastras/{nk}`

**Changes made:**
- Updated `ui/src/lib/api/data.ts`:
  - `getEntityDetail('keyword', nk)` -> calls `/v1/keywords/{nk}`
  - `getEntityDetail('topic', nk)` -> calls `/v1/topics/{nk}`
  - `getEntityDetail('gatha', nk)` -> calls `/v1/gathas/{nk}`
  - `getEntityDetail('shastra', nk)` -> calls metadata `/v1/shastras/{nk}`
  - Added response normalization into the existing `EntityDetail` shape consumed by `DetailsPanel`.
- Updated `ui/src/lib/api/data.test.ts` (TDD) to assert per-kind endpoint mapping and normalized output for keyword kind.

**Verification commands run:**
- `cd ui && pnpm test -- src/lib/api/data.test.ts`

---
## Phase 6:

Implemented Phase 6 content list/index pages with real API-backed data fetching, filters, and pagination.

### Files added
- `ui/src/app/[locale]/(content)/dictionary/letters/[letter]/page.tsx`
- `ui/src/app/[locale]/(content)/search/page.tsx`
- `ui/src/lib/content-listing.ts`
- `ui/src/lib/content-listing.test.ts`

### Files updated
- `ui/src/app/[locale]/(content)/page.tsx` (Home)
- `ui/src/app/[locale]/(content)/shastras/page.tsx`
- `ui/src/app/[locale]/(content)/dictionary/page.tsx`
- `ui/src/app/[locale]/(content)/topics/page.tsx`

### What was implemented
- Home (`/[locale]`):
  - ISR (`revalidate = 60`)
  - Fetches `getStatsCounts()` + `getActivityRecent()`
  - Hero, search row, 4 entry cards with Devanagari counts, and recent activity table
- Shastras (`/[locale]/shastras`):
  - ISR (`revalidate = 60`)
  - Fetches `getShastras({ q, anuyoga, limit, offset })`
  - Sticky filter row, 3/2/1 card grid, and previous/next pagination labels in Hindi
- Dictionary index (`/[locale]/dictionary`):
  - ISR (`revalidate = 60`)
  - Fetches `getKeywordsLetters()` + `getKeywordsRecent()`
  - Letter grid and "हाल ही में जोड़े गए शब्द" side list
- Dictionary letter listing (`/[locale]/dictionary/letters/[letter]`):
  - ISR (`revalidate = 60`)
  - Fetches `getKeywords({ letter, q, limit, offset })`
  - Search-within + list rows + pagination
- Topics (`/[locale]/topics`):
  - ISR (`revalidate = 60`)
  - Fetches `getTopics({ q, source, limit, offset })`
  - Filter row + card grid + pagination
- Search (`/[locale]/search`):
  - Dynamic (`revalidate = 0`)
  - Calls `query.searchTopics({ q, caller: 'public-ui' })`
  - Result cards, empty state, and inline error block

### Tests added
- `ui/src/lib/content-listing.test.ts`
  - `getHindiText` picks Hindi text when available
  - `getHindiText` fallback behavior
  - `buildPageHref` offset generation
  - `paginatedMeta` page/flags computation

### Verification commands run
- `cd ui && pnpm test`
- `cd ui && pnpm build`

Both passed.

### Manual UI verification checklist (Phase 6)
1. Open `http://localhost:3000/hi` and `http://localhost:3000/en`; verify Home hero, 4 entry cards, and recent activity table render.
2. On Home, submit the local search input; verify it routes to locale-preserved `/[locale]/search?q=...`.
3. Open `/[locale]/shastras`; verify filter row is visible, cards render, and previous/next pagination updates `?page=`.
4. Open `/[locale]/dictionary`; verify letter grid cells and recent keyword list render.
5. Click a letter cell; verify `/[locale]/dictionary/letters/[letter]` opens with keyword list and page controls.
6. Use `q` search-within on letter listing; verify list narrows and query param persists.
7. Open `/[locale]/topics`; verify source filter + search work and pagination updates.
8. Open `/[locale]/search?q=<term>`; verify ranked result cards, overlap/score pill, and both CTAs render.
9. Try `/[locale]/search?q=<gibberish>`; verify empty-state text "कोई परिणाम नहीं मिला" appears.
10. Resize at mobile (`~375px`), tablet (`~768px`), desktop (`>=1280px`) and verify the list/grid layouts reflow without overlap.
