# UI — Developer Wiki

Comprehensive reference for the `ui/` Next.js application. Read this before touching any UI code. For pixel-level design decisions refer to `docs/design/ui/`; this document is the implementation-level source of truth.

---

## Table of Contents

1. [Project at a Glance](#1-project-at-a-glance)
2. [Directory Layout](#2-directory-layout)
3. [Tech Stack & Dependencies](#3-tech-stack--dependencies)
4. [Local Development](#4-local-development)
5. [Design System](#5-design-system)
6. [Page Shells (Layouts)](#6-page-shells-layouts)
7. [Routing & i18n](#7-routing--i18n)
8. [Component Catalogue](#8-component-catalogue)
9. [API Client Layer](#9-api-client-layer)
10. [Graph Page — Deep Dive](#10-graph-page--deep-dive)
11. [State Management](#11-state-management)
12. [Content Pages](#12-content-pages)
13. [Testing](#13-testing)
14. [Implementation Phase Log](#14-implementation-phase-log)
15. [Design Docs Index](#15-design-docs-index)

---

## 1. Project at a Glance

The `ui/` directory is a **Next.js 16 App Router** application that is the public-facing website for the Jain Knowledge Base. It is Hindi-first, Devanagari-forward, and built around a graph traversal view as the primary entry point.

**Canonical design references** (both files are in `docs/design/ui/ux_template_images/`):
- `overall_theme_and_panels.png` — colour palette, nav bar, left filter panel, right details panel, badge and card anatomy.
- `navigation_and_graph_look.png` — graph canvas, dotted-grid background, node card shape, connector curves.

**Brand summary:**
- Accent colour `#E63946` (red) used sparingly: CTAs, active node fill, selected badge.
- Body chrome: neutral white / `#F7F7F8` background, `#1A1A1A` text.
- Two font families: **Noto Serif Devanagari** (body default, all Devanagari text) and **Inter** (English chrome, badges, numerals).
- Devanagari numerals (०–९) everywhere the reader sees counts; ASCII only for technical IDs.

## Getting Started

First, run the development server:

```bash
npm run dev
# or
yarn dev
# or
pnpm dev
# or
bun dev
```

Open [http://localhost:3000](http://localhost:3000) with your browser to see the result.

This project uses [`next/font`](https://nextjs.org/docs/app/building-your-application/optimizing/fonts) to automatically optimize and load [Geist](https://vercel.com/font), a new font family for Vercel.

---

## 2. Directory Layout

```
ui/
├── next.config.ts              # Rewrites /api/* → backend services; next-intl plugin
├── src/
│   ├── app/
│   │   ├── layout.tsx          # Root layout: html/body, fonts, lang attribute
│   │   ├── globals.css         # @theme inline (Tailwind token map) + focus ring + shimmer keyframe
│   │   ├── favicon.ico
│   │   ├── api/
│   │   │   └── feedback/route.ts  # POST /api/feedback → MongoDB jain_kb.feedback
│   │   └── [locale]/
│   │       ├── layout.tsx      # Locale shell: validates locale, NextIntlClientProvider, TopBar
│   │       ├── dev/page.tsx    # Component gallery at /dev
│   │       ├── graph/          # Shell A — full-bleed graph (see §10)
│   │       └── (content)/      # Shell B — centered content pages
│   │           ├── layout.tsx
│   │           ├── page.tsx                   # Home /
│   │           ├── about/page.tsx
│   │           ├── feedback/page.tsx
│   │           ├── search/page.tsx
│   │           ├── shastras/
│   │           │   ├── page.tsx               # Shastra list
│   │           │   └── [nk]/page.tsx          # Shastra detail
│   │           ├── dictionary/
│   │           │   ├── page.tsx               # Letter index
│   │           │   ├── letters/[letter]/page.tsx
│   │           │   └── [nk]/page.tsx          # Keyword detail
│   │           └── topics/
│   │               ├── page.tsx               # Topic browser
│   │               └── [nk]/page.tsx          # Topic detail
│   │   └── (reading)/          # Shell C — split reading layout
│   │       ├── layout.tsx
│   │       └── shastras/[nk]/gathas/[number]/page.tsx
│   ├── components/
│   │   ├── ui/                 # shadcn primitives (do not edit directly)
│   │   └── *.tsx               # Project components (see §8)
│   ├── i18n/
│   │   ├── routing.ts          # next-intl routing config
│   │   ├── request.ts          # getRequestConfig
│   │   └── navigation.ts       # Locale-aware Link, usePathname, useRouter, redirect
│   ├── lib/
│   │   ├── config.ts           # Runtime config — reads NEXT_PUBLIC_* env vars (e.g. DEFAULT_GRAPH_DEPTH)
│   │   ├── types.ts            # All shared TypeScript types
│   │   ├── icons.ts            # Reserved lucide-react icon re-exports
│   │   ├── nav.ts              # isNavActive, truncateLabel, nav item arrays
│   │   ├── content-listing.ts  # getHindiText, buildPageHref, paginatedMeta
│   │   ├── gatha-content.ts    # Bracket-tagged teeka term extraction helpers
│   │   ├── feedback-validation.ts  # Pure validation: validateFeedback, EMAIL_REGEX
│   │   ├── format/
│   │   │   └── devanagari.ts   # toDevanagariNumerals, normalizeNFC, minGraphemeLength
│   │   ├── api/
│   │   │   ├── _fetch.ts       # apiFetch<T> base wrapper + ApiError
│   │   │   ├── metadata.ts     # metadata-service client (port 8001)
│   │   │   ├── data.ts         # data-service client (port 8002)
│   │   │   ├── navigation.ts   # navigation-service client (port 8003)
│   │   │   └── query.ts        # query-service client (port 8004)
│   │   └── store/
│   │       ├── graphStore.ts   # Zustand store for graph state
│   │       └── graphUrlState.ts # URL ↔ store serialisation helpers
│   ├── proxy.ts                # next-intl middleware (note: named proxy.ts not middleware.ts — Next.js 16)
│   └── styles/
│       └── theme.css           # All 30+ CSS custom properties
└── messages/
    ├── hi.json                 # All Hindi chrome strings (nav labels, buttons, section headings)
    └── en.json                 # English transliterations and tooltips (must mirror hi.json leaf-key set)
```

---

## 3. Tech Stack & Dependencies

| Package | Purpose |
|---|---|
| `next` (v16) | App Router, ISR, rewrites, API routes |
| `next-intl` | Locale routing (hi/en), translations, locale-aware navigation |
| `tailwindcss` (v4) | Utility CSS — token mapping via `@theme inline` in `globals.css` (no `tailwind.config.ts`) |
| `zustand` | Graph page state store |
| `d3-force` | Force simulation for graph layout |
| `@base-ui/react` | Dialog primitive for `DefinitionModal` |
| `shadcn` (components) | Button, Card, Switch, Tabs, Tooltip, Pagination, Sheet, Popover, Separator, Badge |
| `lucide-react` | Icons (stroke 1.5; reserved set in `lib/icons.ts`) |
| `mongodb` | Feedback API route writes to `jain_kb.feedback` collection |
| `clsx` + `tailwind-merge` | Class composition |
| `vitest` | Unit test runner (`pnpm test`) |

**Tailwind 4 note:** There is no `tailwind.config.ts`. All token-to-utility mapping lives in the `@theme inline` block inside `src/app/globals.css`. The `src/styles/theme.css` declares the CSS custom properties; `globals.css` imports it and maps every token to a Tailwind class.

**Next.js 16 note:** Middleware is named `src/proxy.ts` (not `middleware.ts` as in Next.js 14). This is transparent to the rest of the codebase.

---

## 4. Local Development

```bash
cd ui
pnpm install
pnpm dev          # http://localhost:3000
pnpm build        # production build (must pass with 0 errors)
pnpm test         # vitest single pass
pnpm test:watch   # vitest interactive
```

**Backend services** must be running for real data. The Next.js dev server proxies API calls via rewrites in `next.config.ts`:

| Proxy path | Backend | Env var override |
|---|---|---|
| `/api/metadata/*` | `http://localhost:8001` | `METADATA_SVC_URL` |
| `/api/data/*` | `http://localhost:8002` | `DATA_SVC_URL` |
| `/api/navigation/*` | `http://localhost:8003` | `NAV_SVC_URL` |
| `/api/query/*` | `http://localhost:8004` | `QUERY_SVC_URL` |

The UI never calls backend ports directly from the browser — always through these same-origin proxy paths. (Direct port calls caused CORS failures; fixed in Phase 5 bug fix.)

**Locale URLs:**
- `localhost:3000/` → Hindi (default, no prefix)
- `localhost:3000/en` → English

Component gallery: `localhost:3000/dev` (or `/en/dev`).

### Environment variables (graph)

Create `ui/.env.local` to override defaults without touching committed code:

| Variable | Default | Description |
|---|---|---|
| `NEXT_PUBLIC_DEFAULT_GRAPH_DEPTH` | `1` | Initial traversal depth when no `?depth=` URL param is present. Valid values: `1`, `2`, `3`, `4`. Invalid values silently fall back to `1`. |

Example `.env.local`:

```env
NEXT_PUBLIC_DEFAULT_GRAPH_DEPTH=2
```

The value is read once at module load time by `src/lib/config.ts` and consumed by the graph store initial state, the URL parser fallback, and the `getNavLandingRandom` default parameter.

---

## 5. Design System

### Color tokens (`src/styles/theme.css`)

All components must consume CSS variables. Never hardcode hex values.

| Token | Value | Semantic use |
|---|---|---|
| `--background` | `#F7F7F8` | Body background |
| `--surface` | `#FFFFFF` | Cards, panels, nav |
| `--surface-muted` | `#FAFAFB` | Hover rows, wells |
| `--foreground` | `#1A1A1A` | Primary text |
| `--foreground-muted` | `#6B7280` | Captions, English subtitles |
| `--foreground-subtle` | `#9CA3AF` | Hints, placeholders |
| `--border` | `#E5E7EB` | All borders (always 1 px) |
| `--border-strong` | `#D1D5DB` | Input borders, dividers |
| `--accent` | `#E63946` | CTAs, selected fill, active state |
| `--accent-hover` | `#D62839` | CTA hover |
| `--accent-soft` | `#FDECEE` | Accent-tinted backgrounds |
| `--ring` | `#E63946` | Focus ring (30% alpha, 2 px) |
| `--danger` | `#DC2626` | Error states only |
| `--graph-grid-dot` | `#D9DBE0` | Graph canvas dot grid |
| `--graph-edge` | `#1F3A8A` | Edge line (deep indigo) |
| `--graph-edge-muted` | `#C7CCE0` | Inactive edge |
| `--node-bg` | `#FFFFFF` | Node card resting fill |
| `--node-bg-selected` | `#E63946` | Selected node fill |

**Category colors** (used only for node card top stripe and filter swatches):

| Token | Value | Entity |
|---|---|---|
| `--cat-shastra` | `#E63946` | शास्त्र |
| `--cat-gatha` | `#F4A261` | गाथा |
| `--cat-topic` | `#2A9D8F` | विषय |
| `--cat-keyword` | `#264653` | शब्द |

### Typography

- **`font-serif-hindi`** (`Noto Serif Devanagari`) — all Hindi/Sanskrit/Prakrit text, body default.
- **`font-sans`** (`Inter`) — English chrome, badges, buttons, code, IDs.

Type scale: `text-display` (32/40px) → `text-h1` (24/32) → `text-h2` (20/28) → `text-h3` (16/24) → `text-body` (15/24) → `text-sm` (13/20) → `text-xs` (11/16).

### Radii

`--radius-sm` (6px) · `--radius-md` (10px) · `--radius-lg` (14px) · `--radius-pill` (9999px)

### Icons

All icons from `lucide-react`, stroke `1.5`. Import only from `src/lib/icons.ts` (which re-exports the reserved set). Key mappings:

| Concept | Icon |
|---|---|
| Graph | `Network` |
| Dictionary | `BookOpen` |
| Topic | `Tag` |
| Shastra | `ScrollText` |
| Gatha | `BookMarked` |
| Keyword | `Sparkles` |
| Filter | `LayoutList` |
| Zoom in/out/reset | `Plus`, `Minus`, `Maximize2` |

---

## 6. Page Shells (Layouts)

Three distinct layout shells, all under `src/app/[locale]/`:

### Shell A — Graph (`graph/layout.tsx`)
Full-bleed three-pane grid. No footer.
- Left pane: 280px, `--surface`, `CategoryFilterList`. Hidden below `xl` (1280px).
- Center: `flex-1`, `GraphCanvas`.
- Right pane: 380px, `--surface`, `DetailsPanel`. Slides in on node selection. Below 1100px: bottom sheet (75vh).

### Shell B — Centered content (`(content)/layout.tsx`)
- `max-w-[1200px]` centered, 24px horizontal padding.
- `TopBar` + content + `Footer`.

### Shell C — Split reading (`(reading)/layout.tsx`)
- 65% reader column + 35% sticky sidebar.
- Stacks at < 1024px.
- Used for gatha detail pages.

### Root layout (`app/layout.tsx`)
Pure html/body shell. Sets fonts and `lang` attribute via `getLocale()`.

### Locale layout (`app/[locale]/layout.tsx`)
Validates locale via `hasLocale()`. Mounts `NextIntlClientProvider` and `TopBar`. Calls `notFound()` for unrecognised locales.

---

## 7. Routing & i18n

### Locale strategy
- `next-intl` with `localePrefix: "as-needed"`.
- Default locale: `hi`. Hindi URLs have no prefix (`/`); English adds `/en` prefix.
- Locale stored in a cookie.

### Critical: always import navigation from `@/i18n/navigation`

`src/i18n/navigation.ts` exports locale-aware `Link`, `redirect`, `usePathname`, `useRouter` created via `createNavigation(routing)`. These automatically strip/prepend the locale segment. **Never import `Link` or `usePathname` from `next/navigation`** — those are not locale-aware and will break active-state detection and link hrefs.

### Nav route → page file mapping

Every item in the nav item arrays in `src/lib/nav.ts` must have a matching `page.tsx` under `[locale]/`. The test `src/lib/locale-pages.test.ts` enforces this as a manifest check.

### `src/lib/nav.ts`

Exports `isNavActive(pathname, route)`, `truncateLabel(label, max?)`, and the three nav item arrays. `isNavActive` requires the locale-stripped pathname (which `@/i18n/navigation`'s `usePathname` provides automatically).

**Nav labels are always Devanagari** regardless of locale — by design for a Jain scripture application.

---

## 8. Component Catalogue

### Shared / atomic

| Component | File | Purpose |
|---|---|---|
| `BadgeChip` | `components/BadgeChip.tsx` | Entity pill. 4 kinds × 2 sizes (sm/md). Exports `BADGE_DEFAULT_LABELS`, `BADGE_CAT_CLASSES`. |
| `StatTile` | `components/StatTile.tsx` | Stat card — Devanagari numeral `text-h1`, muted uppercase label. |
| `StatTileRow` | `components/StatTileRow.tsx` | 3-up flex row of `StatTile`s. |
| `ConnectedItemRow` | `components/ConnectedItemRow.tsx` | Badge + title + chevron. Renders as `<a>` with href, `<button>` otherwise. Hover: `--surface-muted` bg, `--accent` chevron. |
| `PrimaryCTA` | `components/PrimaryCTA.tsx` | 44px CTA button. `variant`: `'primary'` (default, red) or `'soft'` (pale red, used for "पूरा वर्णन पढ़ें" in DetailsPanel). |
| `ListCards` | `components/ListCards.tsx` | `KeywordCard`, `TopicCard`, `GathaTile`. White surface, hover lift. |
| `Skeleton` | `components/Skeleton.tsx` | `Skeleton.Card`, `Skeleton.Row`, `Skeleton.Title`. Shimmer animation. No spinners. |
| `BreadcrumbBar` | `components/BreadcrumbBar.tsx` | Segments separated by `›`. Last segment unlinked. Titles truncated at 32 chars. |
| `TopBar` | `components/TopBar.tsx` | 64px desktop / 56px mobile nav bar. `'use client'`. Derives active route from `usePathname()` (locale-aware). Collapses to sheet drawer at < 768px. |
| `Footer` | `components/Footer.tsx` | 56px, copyright + version + locale switch + about/source links. |
| `LocaleSwitch` | `components/LocaleSwitch.tsx` | `हिन्दी / English` toggle in footer. Sets locale cookie. |

### Graph-specific

| Component | File | Purpose |
|---|---|---|
| `NodeCard` | `components/NodeCard.tsx` | 220px wide graph node. 5 states: resting/hover/selected/faded/pinned. Top 4px category stripe. Exports `NODE_KIND_META`. Used in `<foreignObject>`. |
| `RelationConnector` | `components/RelationConnector.tsx` | Static cubic Bézier SVG connector. Endpoint circles + midpoint pill label. Pill rotates with path tangent clamped ±20°. Exports `EDGE_LABELS`, `EDGE_TOOLTIPS`. |
| `CategoryFilterList` | `components/CategoryFilterList.tsx` | 4 category toggles, layout radio (Force and Hierarchical functional; Radial placeholder), depth stepper 1–4. Fully controlled; wired to graph store. Exports `CATEGORY_DATA`. |
| `DetailsPanel` | `components/DetailsPanel.tsx` | Right panel (380px desktop, 75vh bottom sheet mobile). Node mode: badge + title + stats + vivaran + connected rows + CTA. Edge mode: relation pill + src→dst + description. Fetches entity detail on selection. |
| `DefinitionModal` | `components/DefinitionModal.tsx` | Full-screen `@base-ui/react` dialog. Keyword path: all sections → `ModalBlock` per block. Topic path: extracts list. Closes on node selection change. |
| `MiniGraphPreview` | `components/MiniGraphPreview.tsx` | Server component. Static SVG of 1-hop neighborhood. Hover overlay links to `/graph?node={nk}`. |

### Detail page components

| Component | File | Purpose |
|---|---|---|
| `GathaPanel` | `components/GathaPanel.tsx` | Gatha text with preserved line breaks. `lang` prop → left border accent: prakrit = `--cat-shastra` 40%, hindi-harigeet = `--accent` 40%, sanskrit = no border. |
| `TaggedTermPopover` | `components/TaggedTermPopover.tsx` | `<span>` with `--accent` underline. On click: 320px `Popover` with meaning blocks. `aria-haspopup="dialog"`. |

---

## 9. API Client Layer

### Architecture

All API calls go through `src/lib/api/`. The base wrapper is `_fetch.ts`:

```typescript
apiFetch<T>(baseUrl: string, path: string, init?: RequestInit): Promise<T>
```

- Throws `ApiError` (extends `Error`, has `.status: number`) on 4xx/5xx.
- Encodes path segments safely for Devanagari — splits on `?` before encoding so query strings are never double-encoded.
- From the browser, calls always go to same-origin proxy paths (`/api/metadata/...` etc.), not backend ports directly.

### Service clients

| File | Service | Base path | Key functions |
|---|---|---|---|
| `api/metadata.ts` | metadata-service | `/api/metadata` | `getShastras`, `getShastra`, `getShastraTeekas`, `getShastraGathas` |
| `api/data.ts` | data-service | `/api/data` | `getStatsCounts`, `getActivityRecent`, `getKeywordsLetters`, `getKeywordsRecent`, `getKeywords`, `getKeyword`, `getTopics`, `getTopic`, `getGatha`, `getGathaRelatedTopics`, `getGathaRelatedKeywords`, `getEntityDetail` |
| `api/navigation.ts` | navigation-service | `/api/navigation` | `getNavLanding`, `expandNode`, `getPreview`, `getTopicNeighbors` |
| `api/query.ts` | query-service | `/api/query` | `searchTopics` (POST, `caller: 'public-ui'`) |

### `getEntityDetail` — per-kind routing

**Important:** the composite `/v1/entity/{kind}/{nk}/detail` endpoint does not exist in the backend. `getEntityDetail` dispatches to per-entity endpoints:

| Kind | Endpoint |
|---|---|
| `keyword` | `data:/v1/keywords/{nk}` |
| `topic` | `data:/v1/topics/{nk}` |
| `gatha` | `data:/v1/gathas/{nk}` |
| `shastra` | `metadata:/v1/shastras/{nk}` |

Response is normalised into the `EntityDetail` shape consumed by `DetailsPanel`. For topics, `extractBlocks()` flatmaps `blocks[]` from extract objects — an earlier bug returned the topic title instead of content because the code fell through to `heading[lang=hin].text`.

### Shared types (`src/lib/types.ts`)

Key interfaces:
- `EntityKind` — `'shastra' | 'gatha' | 'topic' | 'keyword'`
- `EdgeKind` — 11 variants (e.g. `'HAS_TOPIC'`, `'MENTIONS_KEYWORD'`, `'IS_A'`, `'PART_OF'`, `'RELATED_TO'`, ...)
- `GraphNode` — `{ nk, kind, title_hi, title_en?, meta?, degree }`
- `GraphEdge` — `{ id, src, dst, kind, weight }`
- `GraphPayload` — `{ nodes, edges, focus_nk, depth }`
- `EntityDetail` — `{ nk, kind, title_hi, description?, stats, connected[], definitionSections?, topicExtracts? }`
- `KeywordDefinitionData` / `KeywordPageSection` / `DefinitionBlock` / `DefinitionEntry` / `DefinitionReference` — full keyword definition tree

---

## 10. Graph Page — Deep Dive

Files: `src/app/[locale]/graph/`

### Boot sequence (`page.tsx`)
1. Read URL params: `?node`, `?edge`, `?depth`, `?cat`. Depth falls back to `DEFAULT_GRAPH_DEPTH` (from `lib/config.ts`) when absent.
2. Apply depth and category visibility to store.
3. If `?node` → `expandFromNode(nk, depth)`. Otherwise → `getNavLandingRandom(depth)` → `seedFromPayload()`. On first random landing the chosen `focus_nk` is immediately written to `?node=` via `history.replaceState` so refresh is deterministic.
4. Force simulation starts and settles automatically.
5. URL sync: 500ms debounce, `history.replaceState`.

### Graph edge types traversed

The navigation service expand/preview queries traverse these Neo4j relationship types to build the graph payload:

| Edge type | Direction | Connects |
|---|---|---|
| `IS_A` / `PART_OF` / `RELATED_TO` | any | Topic ↔ Topic |
| `HAS_TOPIC` | Keyword → Topic | Keyword to its sub-topics |
| `MENTIONS_KEYWORD` | Topic → Keyword | Topic to keywords it mentions |
| `MENTIONS_TOPIC` | Gatha → Topic | **Gatha to topics it discusses** |
| `IN_SHASTRA` | Gatha → Shastra | **Gatha to its parent Shastra** |

`MENTIONS_TOPIC` and `IN_SHASTRA` are required for gatha and shastra nodes to appear in the graph. Without them, expanding from a topic yields only topic/keyword nodes.

### Canvas (`GraphCanvas.tsx`)
- Full-size `<svg>` with a dotted 24×24px tile grid (dot radius clamped `[0.75, 1.5]`).
- Single `<g>` wrapper with camera transform (translate + scale) applied for pan/zoom.
- Layering: dot grid → edges `<g>` → nodes `<g>` (nodes on top).
- `React.memo` boundary (`EdgesAndNodes`) isolates camera React state from D3-managed DOM — camera changes only re-render transform wrappers, not the node/edge subtree.
- Node cards rendered as `<foreignObject>` wrapping `NodeCard` HTML components.
- Accepts `layout` and `focusNk` props. Restart effect deps are `[nodes.length, layout]` — switches layout to trigger position recompute. `focusNkRef` is a stable ref so node selection does not re-trigger the layout.
- Callbacks: `onEdgeClick`, `onCanvasClick`, `onNodePinToggle`.

### Force simulation (`useForceSimulation.ts`)
- D3 force simulation updating SVG/foreignObject refs directly **without React re-renders** (direct DOM mutation via `requestAnimationFrame`).
- Parameters: `forceLink` (distance 140, strength 0.6), `forceManyBody` (strength −500), `forceCenter`, `forceCollide`, `forceX`/`forceY` (strength 0.07 toward center — prevents disconnected node drift).
- Simulation lifecycle: two separate effects — (a) sim creation on mount, (b) resize-only nudge for forceCenter target. **No sim teardown on canvas resize** (this fixed the graph-shift-on-panel-open bug).
- `restart(nodes, edges, mode?)` — stable identity via `useRef`. `mode: 'force'` (default) runs the animation loop; `mode: 'static'` uses `sim.alpha(0.001).restart()` rather than `sim.tick()` — because `tick()` updates internal coordinates but never emits the `"tick"` event (only the internal `step()` does), so direct DOM handlers would never fire. Setting alpha=alphaMin causes the timer to fire one `step()` async, emit `"tick"`, apply positions, then auto-stop. The async firing also guarantees React has committed the DOM and `registerNode` refs are populated before the tick runs.
- `prefers-reduced-motion`: if active, sim is ticked synchronously to `alpha < REDUCED_MOTION_ALPHA_THRESHOLD (0.05)` then stopped.
- `buildBezierPath` — pure exported helper for Bézier path string generation.
- `accumulateEdgeRef` registers all 4 edge parts (path + 2 circles + foreignObject) before calling `registerEdge`.

### Graph view helpers (`graphViewHelpers.ts`)
Pure functions, no React:
- `buildCanvasNodes` — slices to `MAX_GRAPH_NODES = 20`, applies category visibility, sets active/selected/pinned flags.
- `buildCanvasEdges` — filters to edges whose both endpoints exist in the sliced node set (prevents dangling lines). Also deduplicates bidirectional edges (the backend returns both A→B and B→A as separate IDs) via a canonical key `min(src,dst) + '\x00' + max(src,dst) + '\x00' + kind`; first-seen edge wins, but is promoted to `active: true` if the other direction's ID is the selected one.
- `computeHierarchicalPositions(nodeNks, edges, focusNk, canvasW, canvasH)` — BFS from focusNk to assign depth levels; nodes in each level are chunked into rows of `HIER_MAX_PER_ROW = 4` (prevents sprawling single rows for wide levels); places unreachable nodes one row past the deepest reachable level. Returns `Map<nk, {x, y}>`. Exported constants: `HIER_PADDING_TOP` (120 px), `HIER_LEVEL_HEIGHT` (240 px), `HIER_NODE_SPACING` (320 px).

### URL state (`graphUrlState.ts`)
- `parseGraphQuery(params)` — parses `node`, `edge`, `depth` (clamped 1–4), `cat` (CSV of hidden kinds) from URL.
- `buildGraphQuery(state)` — serialises store state back to query string.

### 300-node guard
`expandFromNode` in `graphStore.ts` checks if the expanded node count would exceed 300. If so, shows a confirmation dialog before proceeding.

### Keyboard shortcuts (partial — Phase 5)
Currently wired: `Esc` → `clearSelection()`. Remaining shortcuts (`f`, `+/-`, `0`, arrows, `/`, `Cmd+K`, `Space+drag`) are specified but not yet fully wired end-to-end.

### Accessibility
SR-only linear nav tree inside graph page: `<nav aria-label="ग्राफ लीनियर दृश्य">` with all visible nodes as nested `<ul>/<li>` linking to entity detail URLs.

---

## 11. State Management

### Zustand graph store (`src/lib/store/graphStore.ts`)

`useGraphStore` — single store for all graph state:

```typescript
type GraphState = {
  nodes: Record<string, GraphNode>;      // keyed by nk
  edges: Record<string, GraphEdge>;      // keyed by id
  pinned: Set<string>;
  selected: { kind: 'node'; id: string } | { kind: 'edge'; id: string } | null;
  categoryVisibility: Record<EntityKind, boolean>;
  depth: 1 | 2 | 3 | 4;          // initial value = DEFAULT_GRAPH_DEPTH (env-configurable, default 1)
  layout: 'force' | 'radial' | 'hierarchical';
  camera: { x: number; y: number; k: number };
  loading: boolean;
  lastError: string | null;
};
```

Actions: `selectNode`, `selectEdge`, `clearSelection`, `togglePin`, `expandFromNode`, `setCategoryVisibility`, `setDepth`, `setLayout`, `setCamera`, `reset`, `seedFromPayload`.

`expandFromNode` de-dupes by `nk`/`id` on merge; seeds new node positions at focus node's position.

---

## 12. Content Pages

All content pages are server components (ISR unless noted).

| Route | Shell | Revalidate | Key data calls |
|---|---|---|---|
| `/` | B | 60s | `getStatsCounts`, `getActivityRecent` |
| `/shastras` | B | 60s | `getShastras` |
| `/shastras/[nk]` | B | 60s | `getShastra`, `getShastraTeekas`, `getPreview` |
| `/shastras/[nk]/gathas/[number]` | C | 60s | `getGatha`, `getGathaRelatedTopics`, `getGathaRelatedKeywords` |
| `/dictionary` | B | 60s | `getKeywordsLetters`, `getKeywordsRecent` |
| `/dictionary/letters/[letter]` | B | 60s | `getKeywords` |
| `/dictionary/[nk]` | B | 60s | `getKeyword`, `getPreview` |
| `/topics` | B | 60s | `getTopics` |
| `/topics/[nk]` | B | 60s | `getTopic`, `getTopicNeighbors` |
| `/search` | B | 0 (dynamic) | `searchTopics` (POST) |
| `/about` | B | static | none |
| `/feedback` | B | `'use client'` | POST `/api/feedback` |

### Feedback form
- `feedback/page.tsx`: `'use client'`, POSTs to `/api/feedback`.
- `api/feedback/route.ts`: validates input (type required, message ≥ 200 chars), writes to MongoDB `jain_kb.feedback` collection. Uses `MONGODB_URI` env var (default `mongodb://localhost:27017`), `MONGODB_DB` (default `jain_kb`). New `MongoClient` per request.

### Content listing utilities (`lib/content-listing.ts`)
- `getHindiText(item)` — picks Hindi text from multilingual display_text arrays, with fallback.
- `buildPageHref(base, offset)` — generates pagination URL.
- `paginatedMeta(total, limit, offset)` — returns `{ page, totalPages, hasNext, hasPrev }`.

---

## 13. Testing

Run: `pnpm test` (single pass) or `pnpm test:watch` (interactive) from `ui/`.

All tests are pure logic tests — no JSX rendering, no component mounting. This is intentional. Each component exports testable data constants alongside its component code.

### Test location

All 27 test files live in a single consolidated suite under `src/__tests__/`, mirroring the source tree:

```
src/__tests__/
├── components/        # BadgeChip, CategoryFilterList, GathaPanel, MiniGraphPreview, NodeCard, RelationConnector
├── graph/             # graphViewHelpers, useForceSimulation
├── i18n/              # navigation, routing
├── lib/
│   ├── api/           # _fetch, data, metadata, metadata.phase7, navigation, query
│   ├── format/        # devanagari, messages
│   └── store/         # graphStore, graphUrlState
│   # content-listing, feedback-validation, gatha-content, icons, locale-pages, nav
└── styles/            # theme
```

The vitest config (`vitest.config.ts`) targets `src/__tests__/**/*.test.ts` and resolves the `@/` alias to `src/`.

### Test files and what they cover

| File | Tests |
|---|---|
| `lib/format/devanagari.test.ts` | `toDevanagariNumerals`, `normalizeNFC`, `minGraphemeLength` |
| `lib/format/messages.test.ts` | hi.json and en.json have identical leaf-key sets; neither is empty |
| `styles/theme.test.ts` | All required CSS tokens declared; hex values match spec |
| `lib/nav.test.ts` | `isNavActive` (exact, prefix, false-positive prevention), `truncateLabel`, nav item data invariants, locale-prefix contract |
| `i18n/routing.test.ts` | Locks `locales`, `defaultLocale`, `localePrefix`, `localeCookie` config |
| `i18n/navigation.test.ts` | All 4 exports exist and are functions (next-intl mocked) |
| `lib/locale-pages.test.ts` | Every nav route has a page file on disk |
| `components/BadgeChip.test.ts` | `BADGE_DEFAULT_LABELS`, `BADGE_CAT_CLASSES` — all 4 kinds, classes, Devanagari script |
| `lib/icons.test.ts` | All 20 reserved icons exported; each is a renderable React component; no extras |
| `lib/api/_fetch.test.ts` | `ApiError` instanceof/status checks; DetailsPanel 404 guard pattern |
| `lib/api/metadata.test.ts` | Success/error paths, URL construction |
| `lib/api/metadata.phase7.test.ts` | `getShastraGathas` endpoint and querystring |
| `lib/api/data.test.ts` | Per-kind endpoint mapping; keyword `definitionSections` normalisation; topic `topicExtracts` normalisation |
| `lib/api/navigation.test.ts` | Endpoint mapping, Devanagari encoding |
| `lib/api/query.test.ts` | POST endpoint, caller default |
| `components/NodeCard.test.ts` | `NODE_KIND_META` — 4 kinds, catVar prefix, icon, labels |
| `components/RelationConnector.test.ts` | `EDGE_LABELS`/`EDGE_TOOLTIPS` — 11 EdgeKinds, non-empty, key parity |
| `components/CategoryFilterList.test.ts` | `CATEGORY_DATA` — 4 items, required fields, no duplicates |
| `graph/useForceSimulation.test.ts` | `buildBezierPath` shape, `GRAVITY_STRENGTH`, `CHARGE_STRENGTH`, `LINK_DISTANCE`, `REDUCED_MOTION_ALPHA_THRESHOLD` |
| `graph/graphViewHelpers.test.ts` | Node limit, slicing, category filter, active/selected/pinned flags, dangling-edge exclusion |
| `lib/store/graphStore.test.ts` | Seed merge, pin toggling, `expandFromNode` de-dupe, 300-node guard cancel |
| `lib/store/graphUrlState.test.ts` | URL parse/serialise, depth clamp, invalid cat filtering |
| `components/GathaPanel.test.ts` | Language-to-accent class mapping |
| `components/MiniGraphPreview.test.ts` | SVG coordinate projection bounds |
| `lib/gatha-content.test.ts` | Bracket-tagged teeka term extraction and splitting |
| `lib/feedback-validation.test.ts` | Valid data passes, type required, message length bounds, email regex |

---

## 14. Implementation Phase Log

| Phase | Status | What was built |
|---|---|---|
| 0 | ✅ | Next.js + Tailwind 4, CSS token layer, fonts, next-intl, Devanagari utils |
| 1 | ✅ | TopBar, BreadcrumbBar, Footer, 3 page shells, Skeleton, locale routing fix |
| 2 | ✅ | BadgeChip, StatTile, ConnectedItemRow, PrimaryCTA, ListCards, icons |
| 3 | ✅ | API clients for all 4 services, shared types, same-origin proxy fix |
| 4 | ✅ | NodeCard, RelationConnector, CategoryFilterList, GraphCanvas, ZoomControls, useForceSimulation |
| 5 | ✅ | Zustand graph store, URL sync, DetailsPanel, interaction handlers, SR-only nav tree |
| 6 | ✅ | Home, Shastras list, Dictionary index/letter listing, Topics browser, Search page |
| 7 | ✅ | GathaPanel, TaggedTermPopover, MiniGraphPreview, all 4 detail routes, gatha-content helpers |
| 8 | ✅ | About page, Feedback form + API route, ARIA pass, focus ring, prefers-reduced-motion |
| Vivaran fix | ✅ | Keyword definition rendering, topic extracts, DefinitionModal, CTA soft variant, footer clip fix |
| Bugfixes | ✅ | Node limit (MAX=20), graph stability on panel open, 404 handling, disconnected node gravity |
| Hierarchical layout | ✅ | BFS-depth hierarchical layout mode; made default; Force and Hierarchical both functional |
| Gatha/Shastra graph fix | ✅ | Added `MENTIONS_TOPIC` and `IN_SHASTRA` to expand/landing Cypher; fixed isolated focus-node kind fallback; added gatha/shastra UI tests |

---

## 15. Design Docs Index

All design documents are in `docs/design/ui/`. Read them for pixel-level specifications.

| File | Covers |
|---|---|
| `00_overview.md` | Reading order, brand identity, canonical reference images |
| `01_design_system.md` | All color tokens, typography scale, spacing, radii, shadow, badge/icon/stat specs |
| `02_layout_and_navigation.md` | TopBar, page shells, responsive breakpoints, footer |
| `03_graph_traversal_page.md` | Three-pane layout, NodeCard anatomy, connectors, filter panel, DetailsPanel, zoom/pan, state machine |
| `04_content_pages.md` | Spec for every content page (Home, Shastras, Gatha, Dictionary, Topics, Search, About, Feedback) |
| `05_components.md` | All component props and visual specs |
| `06_interaction_and_state.md` | Click/hover/drag, keyboard shortcuts, URL state, loading/empty/error states, animations |
| `07_api_integration.md` | Page → endpoint mapping, response shapes, caching headers, error handling |
| `08_accessibility_and_i18n.md` | Hindi-first defaults, Devanagari normalisation, ARIA table, keyboard, font loading |
| `implementation_notes.md` | Phase-by-phase implementation log with all bugs fixed and key decisions |
| `implementation_phases.md` | Step-by-step build plan for all 8 phases |
| `updates/01_side_panel_vivaran.md` | Spec for keyword definition rendering, topic extracts, DefinitionModal (implemented 2026-05-15) |
| `implementation_notes/graph_changes_implementation_nodes.md` | Hierarchical layout implementation details — design decisions, files changed, constants, known limitations |
| `manual_verification_checklist.md` | Manual testing steps that cannot be automated (Lighthouse, cross-browser Devanagari, locale switch) |
