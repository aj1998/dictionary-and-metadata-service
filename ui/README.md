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
13. [Matching Engine Integration](#13-matching-engine-integration)
14. [Testing](#14-testing)
15. [Implementation Phase Log](#15-implementation-phase-log)
16. [Design Docs Index](#16-design-docs-index)

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
│   │               └── page.tsx               # Topic browser (no [nk] page — TopicNavAction routes leaves to the DefinitionModal and non-leaves to /dictionary/<parent_kw>?topic=<nk>)
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
│   │   │   ├── metadata.ts     # metadata-domain client via core-service (port 8001)
│   │   │   ├── data.ts         # data-domain client via core-service (port 8001)
│   │   │   ├── navigation.ts   # navigation-domain client via core-service (port 8001)
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
| `/api/data/*` | `http://localhost:8001` | `DATA_SVC_URL` |
| `/api/navigation/*` | `http://localhost:8001` | `NAV_SVC_URL` |
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
| `--cat-gatha-teeka` | `#E8B931` | गाथा टीका |
| `--cat-teeka` | `#C27B00` | टीका |
| `--cat-bhaavarth` | `#7C5CB8` | भावार्थ |
| `--cat-kalash` | `#5E8A4A` | कलश |
| `--cat-page` | `#B5645A` | पृष्ठ |
| `--cat-topic` | `#2A9D8F` | विषय |
| `--cat-keyword` | `#264653` | शब्द |
| `--cat-publication` | `#4A90A4` | प्रकाशन |
| `--cat-table` | `#6B7280` | तालिका (node stripe + filter swatch) |
| `--cat-table-soft` | `#E5E7EB` | तालिका background / alternating table rows |
| `--cat-table-fg` | `#374151` | तालिका foreground text |

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
| Table | `Table` (`IconTable`) |

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

### Shell C — Reading (`(reading)/layout.tsx`)
- Centered `max-w-[1440px]` shell. Pages own their column layout — the shell does not impose a left/right column. (Previous version split children into a 65/35 reader + sidebar slot; that was removed when the gatha page took over its own 2-/3-column grid via `GathaReaderLayout`.)
- Stacks at `< lg` (1024px).
- Used for gatha and kalasha detail pages.

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
| `CategoryFilterList` | `components/CategoryFilterList.tsx` | 4 category toggles, layout radio (Force, Radial, and Hierarchical all functional), depth stepper 1–4. Fully controlled; wired to graph store. Exports `CATEGORY_DATA`. |
| `DetailsPanel` | `components/DetailsPanel.tsx` | Right panel (380px desktop, 75vh bottom sheet mobile). Node mode: badge + title + stats + vivaran + connected rows + CTA ("पूरा वर्णन पढ़ें"). The node body div uses `flex flex-1 min-h-0 flex-col` so the inner content area scrolls independently while the CTA stays pinned at the bottom. Edge mode: relation pill + src→dst + description. Fetches entity detail on selection via `getEntityDetail`. **Stub-topic fallback:** stub-seed topics only exist in Neo4j (not Postgres), so the API returns 404 and `detail` stays `null`. In this case the exported `deriveStubTopicKeyword(topicNk, nodes)` utility extracts the parent keyword nk from the topic's natural key (everything before the first `:`), looks it up in the graph nodes map for its display title, and synthesises a single `HAS_TOPIC` connected row so the parent keyword badge always appears in the "संबंधित" section. |
| `TableModal` | `components/TableModal.tsx` | Full-screen `@base-ui/react` dialog. Props: `naturalKey: string \| null` (null = closed), `onClose`. Fetches via `getTable()` with an in-memory per-nk `useRef<Map>` cache; shows shimmer skeleton while loading and a retry button on error. Body: caption (`<h2>`, falls back to "तालिका"), optional source link, cells-rendered table (first `headerRows` rows as `<th>`, alternating-row bg, horizontally scrollable wrapper), mentioned-keyword and mentioned-topic badge chips as locale-aware `Link`s. Dev-only: collapsible `<details>` with `rawHtml` in a sandboxed `<iframe srcDoc>`. Opened by graph node click when `kind === 'table'`; state lives in `graphStore.tableModalNk`. |
| `DefinitionModal` | `components/DefinitionModal.tsx` | Optional `navigateHref` + `navigateLabel` render an accent link bar between the header and the body (target=_blank). Full-screen `@base-ui/react` dialog. **Two view modes** switchable via a `ViewToggle` pill in the modal header (top-right, left of the close button); toggle styled with `bg-accent-soft` / `border-accent/30` background, active tab filled `bg-accent text-accent-foreground`. **क्रमानुसार (sequential — default):** blocks shown flat in original document order. For topic extracts, consecutive blocks sharing the same `list_number` (see `DefinitionBlock.list_number`) are grouped under a leading number badge (`1.`, `7.`, …); blocks without `list_number` are shown without a badge. For keyword definitions, each `DefinitionEntry` is numbered by its parser-assigned `definition_index` within the section. All `RefBadge` instances in this mode use `showShastra={true}` so the shastra name (and teeka name when applicable) appears in each ref badge. **शास्त्रानुसार (by shastra):** existing accordion grouping — `groupTopicExtractsByShastra` → each group rendered as a collapsible `ShastraAccordion`; keyword path uses 3-level hierarchy `KeywordSectionAccordion` → `KeywordDefinitionBlocks` → `ShastraAccordion`. **Reference display per block:** all non-inline refs (`inline_reference: false`) with resolved fields shown as badges; inline fallback = first qualifying only. Hidden refs surfaced via **`समान संदर्भ`** button (accent red, bold) → 480px `Popover`. Left border: teal for Sanskrit/Prakrit, amber for teeka, sky-blue for shastra refs. `ModalBlock` accepts `showShastra?: boolean` to show/hide shastra name on `RefBadge`. Exports `getBlockBorderClass`, `formatRefSourceLabel`, `pickRefsToShow`, `pickHiddenRefs`, `groupTopicExtractsByShastra`, `ShastraGroup` (all pure / typed, tested). Closes on node selection change. |
| `MiniGraphPreview` | `components/MiniGraphPreview.tsx` | Server component. Static SVG of 1-hop neighborhood. Hover overlay links to `/graph?node={nk}`. |

### Detail page components

| Component | File | Purpose |
|---|---|---|
| `GathaPanel` | `components/GathaPanel.tsx` | Gatha text with preserved line breaks. `lang` prop → left border accent: prakrit = `--cat-shastra` 40%, hindi-harigeet = `--accent` 40%, sanskrit = no border. Parser guarantees no `(N)` mid-verse labels or `॥N॥` markers appear in the text. |
| `BhaavarthPanel` | `components/BhaavarthPanel.tsx` | Bordered surface panel with an optional label and text body. Two rendering variants controlled by the `variant` prop: `'prose'` (default) and `'verse'`. `'verse'` uses `whitespace-pre-wrap` directly, keeping doha/gatha line breaks tight without extra paragraph margins; use it for kalash Sanskrit/Hindi and secondary-gatha Prakrit content. `'prose'` is split by `parseBhaavarthSegments()` (`src/lib/format/bhaavarth-segments.ts`) into alternating `chips` and `html` segments. Compact bracket runs are rendered inline as a mini शब्दार्थ-style block: `ShabdaArthSection` chip row on top, then `अन्वयार्थ` below (space-joined Hindi meanings); clicking a chip highlights its meaning in the अन्वयार्थ. Remaining prose still renders through `teekaMarkdownToHtml`. **Important parser behaviour:** real source bhaavarth is line-oriented (`**[term]**` on one line, Hindi meaning on the following line), so the parser works by header-led blocks rather than blank-line paragraphs; it also supports single-line `[term] meaning` rows. A run collapses only when the bhaavarth contains at least 3 compact bracket items in total. Each meaning is truncated at the first Devanagari full stop `।` so that the transition prose that typically follows (`इसके आगे…`, `सार यह है कि…`) does not get pulled into a chip's अन्वयार्थ — earlier behaviour absorbed entire trailing paragraphs and even verse-end markers like `॥७॥` into the last chip's meaning. Meaning-line collection also stops at: bullet lines (`- …`), the `अब …` paragraph-transition marker, italic `*((…))*` emphasis blocks, non-bracket bold conclusion lines (e.g. blue summary lines), full-line verse markers `॥३॥`, and lines whose trailing token is a verse marker. There is no longer a `MAX_MEANING_LEN` cap — long but legitimately single-sentence meanings (e.g. `[वन्दित्तु]`) stay compact and join their neighbouring chip group. Highlighted prose is still segmented first, then the active highlight is applied only to the overlapping prose segment so chip blocks remain visible in the reader. |
| `ShabdaArthSection` | `components/ShabdaArthSection.tsx` | `'use client'`. Interactive शब्दार्थ block. Renders term chips + `अन्वयार्थ` in one unit. Clicking a chip selects it (click again to deselect); the active chip gets `bg-accent-soft text-accent` styling and its meaning is highlighted inline inside the अन्वयार्थ text via a `<mark>` element. Falls back gracefully when the meaning string is not found as a substring of the anvayarth. Used in: `BhaavarthPanel` chips segments, gatha-page शब्दार्थ section, kalash word-meanings in the संबंधित panel, and the kalasha detail page. Replaces the old `TaggedTermPopover` popover pattern. |
| `TaggedTermPopover` | `components/TaggedTermPopover.tsx` | `<span>` with `--accent` underline. On click: 320px `Popover` with meaning blocks. `aria-haspopup="dialog"`. **No longer used for शब्दार्थ sections** — superseded by `ShabdaArthSection`. |
| `TopicTreeBrowser` | `components/TopicTreeBrowser.tsx` | `'use client'`. Horizontal multi-column topic navigator used on the dictionary keyword detail page (`/dictionary/[nk]`). Column 0 is seeded server-side via `getKeywordTopics`. Clicking a row's label expands its inbound-`PART_OF` children into the next column via `getTopicNeighbors`. Each row shows an ASCII dotted path (e.g. `1`, `1.1`, `1.1.1`). On render, every visible item is probed once via `getEntityDetail('topic', nk)` + `getTopicRelated` + `getTopicMentionedKeywords` (in-memory cache + in-flight dedupe); the probe drives these affordances: (1) a small bordered-accent `BookOpen` pill that opens `DefinitionModal` with the topic's extracts when `topicExtracts` is non-empty; (2) a muted `›` `ChevronRight` when `stats.is_leaf === 0`; (3) disabling of the label-button expand action for confirmed leaves; (4) **label-seed segregation** — items whose `topicPath` is null are split into a separate "अन्य विषय" sub-block at the bottom of the column (with a top border), keeping the numbered path list contiguous; (5) a bordered-teal `Link2` toggle (on **both** numbered path items and अन्य विषय items) that expands inline to show merged related topics + mentioned keywords. **Related-target guards (applied pre-emptively during the probe, so the `Link2` icon never appears when nothing valid would show):** (a) drop self-references (target nk === source nk); (b) drop topic targets that are themselves anya-vishay (no `topicPath` and no `topicExtracts`, verified via `getEntityDetail` cached lookup); items left with zero surviving targets are excluded from `hasRelated`. Clicking a related keyword opens `/dictionary/<nk>` in a new tab; clicking a related topic fetches its detail and either opens the `DefinitionModal` (when it has extracts) or opens `/dictionary/<parent_kw>?topic=<nk>` in a new tab — the new-tab navigation **does not** apply the current-keyword self-suppression that the modal's `navigateHref` does, so a related-target link whose parent keyword matches the current page still navigates. **Selection highlight** — auto-expand from URL highlights the matched item with `bg-accent-soft` whether it lands in the numbered path list or in the अन्य विषय sub-block. **Modal navigate link** — every modal open from this component sets `DefinitionModal.navigateHref` to the parent-keyword shabdkosh URL with `?topic=<nk>`, **unless** that parent keyword equals `currentKeywordNk` (self-link suppression). **Auto-expand from URL** — accepts a `targetTopicNk` prop (sourced from `?topic=` on the dictionary keyword page) and on mount calls `getTopicAncestors` to fetch the ordered ancestor chain, then walks columns down to and selects the target. |
| `TopicNavAction` | `components/TopicNavAction.tsx` | `'use client'`. Single button that replaces the old "विषय खोलें" link across the app. On click it lazily fetches the topic's `EntityDetail` (one-shot per instance via `useRef` cache) and decides: if `topicExtracts` are non-empty → opens `DefinitionModal` in place with a `navigateHref` to `/dictionary/<parent_kw>?topic=<nk>` (link suppressed only when callers pass a matching `parentKeywordNk`); otherwise opens that URL directly in a new tab. Accepts optional `isLeaf` + `parentKeywordNk` to short-circuit the detail fetch when known (used by the topics listing). Icon switches between `BookOpen` ("पढ़ें") for leaves and `ExternalLink` ("शब्दकोश में देखें") for non-leaves. Two visual variants — `'button'` (bordered accent pill, default) and `'inline'` (text link). Used in: `/topics` list cards, `/search` result rows, and gatha-reading "संबंधित विषय" pills. |

### Gatha reader — panel actions ("उल्लिखित विषय" / "परिभाषित शब्द")

Each of the four gatha-page panels (शब्दार्थ, कलश, टीका, हिन्दी भावार्थ) renders a top-right `⋯` menu with two actions: **विषय देखें** (mentioned topics via `MENTIONS_TOPIC`) and **शब्द देखें** (defining keywords via `CONTAINS_DEFINITION`). Clicking either fetches results and shows them in a third right-most column that appears only on demand.

| Component | File | Purpose |
|---|---|---|
| `GathaReaderLayout` | `components/GathaReaderLayout.tsx` | `'use client'`. Wraps the gatha page in `ReaderActionsProvider` and renders the responsive grid: `lg:grid-cols-[40fr_60fr]` by default, switching to `lg:grid-cols-[40fr_30fr_30fr]` when the right column is open. Receives `main` / `sidebar` as `ReactNode` props from the server-rendered page so all data fetching stays on the server. |
| `ReaderActionsContext` | `components/ReaderActionsContext.tsx` | `'use client'`. Provides `{request, open, close}` where `request: {kind: 'topics' \| 'keywords', sourceNk, sourceLabel} \| null`. Single open request at a time — opening a new action replaces the previous. |
| `PanelActionsMenu` | `components/PanelActionsMenu.tsx` | `'use client'`. `MoreHorizontal` (⋯) `Popover` trigger placed in each panel header. Three list items: `Tag` → topics, `Sparkles` → keywords (both call `useReaderActions().open()`), and `Network` → **ग्राफ में खोलें** (locale-aware `Link` to `/graph?node={encodeURIComponent(sourceNk)}`, `target="_blank"`). **Embedded in panels, not passed as a callback** — function props can't cross the server→client boundary, so `TabbedPanel` / `TeekaPanel` accept serialisable `showActions: boolean` + per-item `actionsSourceNk` / `actionsSourceLabel` fields and render the menu themselves from the currently-active tab item. Both components also accept an optional `notice?: ReactNode` prop rendered inline beside the panel title (used for the combined-gatha chip — see §Combined-gatha notice below). **Critical:** `actionsSourceNk` must be the canonical Neo4j node key — see `data_model_graph.md § Natural-key format conventions` for the reconstruction each panel type applies. |
| `MentionedRightColumn` | `components/MentionedRightColumn.tsx` | `'use client'`. The right-column slot. Reads the open request from context, calls `getNodeMentionedTopics` / `getNodeMentionedKeywords` (cancellation-safe), and renders the result list with new-tab links: topics → `/dictionary/<parent_keyword_natural_key>?topic=<nk>` (so `TopicTreeBrowser` auto-expands to the target on the dictionary page); keywords → `/dictionary/<nk>`. Header shows the source label and a `X` close button. |

**Canonical source-nk reconstruction (important).** The Mongo text-doc `natural_key` stored on `gatha.teeka_sanskrit[*].natural_key` and `gatha.teeka_bhaavarth[*].natural_key` is **not** the same string as the canonical Neo4j `GathaTeeka` / `GathaTeekaBhaavarth` node `natural_key` that carries the `MENTIONS_TOPIC` / `CONTAINS_DEFINITION` outbound edges. The gatha page (`shastras/[nk]/gathas/[number]/page.tsx`) holds two derive helpers — `gathaTeekaNeo4jNk(teeka_nk)` → `{shastra}:{teeka}:गाथा:टीका:{g}` and `gathaTeekaBhaavarthNeo4jNk(bh)` → `{shastra}:{teeka}:{publisher_id}:गाथा:टीका:भावार्थ:{g}` — that reconstruct the canonical Neo4j nk from the available metadata and assign it to a separate `actionsSourceNk` field on the panel item (the original `naturalKey` continues to drive the highlight/scroll logic, which is keyed by the Mongo doc nk). Kalash and Gatha already use canonical nks — no reconstruction needed. The Gatha Neo4j key is always `${shastraPrefix}:गाथा:${gathaNumStr}` (never the Postgres `natural_key` directly). See `docs/design/data_model/data_model_graph.md § Natural-key format conventions` for the full mismatch table and rationale.

**संबंधित panel (formerly "कलश").** The `TabbedPanel` titled "संबंधित" in the left column shows all kalashas linked to the current gatha. Each `GathaKalash` in the API response now includes `teeka_natural_key` and `is_secondary` (derived from `teekas.role` via JOIN — business logic lives in the API, not the UI). Tab labels follow this convention:
- Primary kalash (`is_secondary: false`): `कलश:{teeka_short}:{N}` e.g. `कलश:आत्मख्याति:1`
- Secondary kalash (`is_secondary: true`, Jaysenacharya's standalone gathas): `गाथा:{teeka_short}:{N}` e.g. `गाथा:तात्पर्यवृत्ति:11`

The `teeka_short` is extracted from `teeka_natural_key.split(':')[1]`. Content rendering differs by kind: primary kalashas show "कलश संस्कृत" + "कलश हिन्दी" + "शब्दार्थ" (word meanings from `kalash_word_meanings` Mongo collection); secondary kalashas show "गाथा प्राकृत" + "टीका संस्कृत" (both fetched from `gatha_prakrit` / `gatha_teeka_sanskrit`). All verse text panels pass `variant="verse"` to `BhaavarthPanel` to suppress the extra blank lines that `teekaMarkdownToHtml` would introduce between doha/gatha lines.

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
| `api/metadata.ts` | core-service metadata domain | `/api/metadata` | `getShastras`, `getShastra`, `getShastraTeekas`, `getShastraGathas` |
| `api/data.ts` | core-service data domain | `/api/data` | `getStatsCounts`, `getActivityRecent`, `getKeywordsLetters`, `getKeywordsRecent`, `getKeywords`, `getKeyword`, `getTopics`, `getTopic`, `getGatha`, `getExtractMatch`, `getGathaRelatedTopics`, `getGathaRelatedKeywords`, `getEntityDetail`, `getTable`, `listTablesForParent` |
| `api/navigation.ts` | core-service navigation domain | `/api/navigation` | `getNavLanding`, `expandNode`, `getPreview`, `getTopicNeighbors`, `getTopicAncestors`, `getTopicRelated`, `getTopicMentionedKeywords`, `getNodeMentionedTopics`, `getNodeMentionedKeywords` |
| `api/query.ts` | query-service | `/api/query` | `searchTopics` (POST, `caller: 'public-ui'`) |

### `getEntityDetail` — per-kind routing

**Important:** the composite `/v1/entity/{kind}/{nk}/detail` endpoint does not exist in the backend. `getEntityDetail` dispatches to per-entity endpoints:

| Kind | Endpoint |
|---|---|
| `keyword` | `data:/v1/keywords/{nk}` |
| `topic` | `data:/v1/topics/{nk}` |
| `gatha` | `data:/v1/gathas/{nk}` |
| `shastra` | `metadata:/v1/shastras/{nk}` |

Response is normalised into the `EntityDetail` shape consumed by `DetailsPanel`. For topics, `extractBlocks()` flatmaps `blocks[]` from extract objects — an earlier bug returned the topic title instead of content because the code fell through to `heading[lang=hin].text`. **Stub topics** (only in Neo4j, not Postgres) return 404 here; `DetailsPanel` handles this by falling back to `deriveStubTopicKeyword` — it splits the topic nk on the first `:` to recover the parent keyword nk.

### Shared types (`src/lib/types.ts`)

Key interfaces:
- `EntityKind` — `'shastra' | 'gatha' | 'gatha_teeka' | 'teeka' | 'bhaavarth' | 'kalash' | 'page' | 'topic' | 'keyword' | 'publication' | 'table'`
- `GathaKalash` — `{ natural_key, kalash_number, teeka_natural_key, is_secondary, prakrit, sanskrit, hindi, bhaavarth, word_meanings }`. `is_secondary` drives the "संबंधित" panel label and content layout. `word_meanings` (primary kalashas only) holds `{ entries: [{source_word, meaning, position}] }` from the `kalash_word_meanings` Mongo collection, rendered as a "शब्दार्थ" panel.
- `EdgeKind` — 12 variants (e.g. `'HAS_TOPIC'`, `'MENTIONS_KEYWORD'`, `'IS_A'`, `'PART_OF'`, `'RELATED_TO'`, `'CONTAINS_TABLE'`, ...)
- `GraphNode` — `{ nk, kind, title_hi, title_en?, meta?, degree }`
- `GraphEdge` — `{ id, src, dst, kind, weight }`
- `GraphPayload` — `{ nodes, edges, focus_nk, depth }`
- `EntityDetail` — `{ nk, kind, title_hi, description?, stats, connected[], definitionSections?, topicExtracts? }`
- `KeywordDefinitionData` / `KeywordPageSection` / `DefinitionBlock` / `DefinitionEntry` / `DefinitionReference` — full keyword definition tree. `DefinitionBlock.text_devanagari` is `string | null` (backend may omit it for non-text block kinds). `DefinitionBlock.list_number?: number | null` — the rendered `<ol>/<li>` sequence number as captured by the parser from the source HTML (respects `<ol start="N">`); `null` when the block does not originate from a list item. Stored in MongoDB `topic_extracts` and flows through the topic API.

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
| `MENTIONS_TOPIC` | Gatha/GathaTeeka/GathaTeekaBhaavarth/Kalash/KalashBhaavarth/Page → Topic | Source node cites a topic |
| `CONTAINS_DEFINITION` | Gatha/GathaTeeka/GathaTeekaBhaavarth/Kalash/KalashBhaavarth/Page → Keyword | Source node appears inside a keyword's JainKosh definition body |
| `CONTAINS_TABLE` | Topic/Keyword/Gatha/GathaTeeka/GathaTeekaBhaavarth/Kalash/KalashBhaavarth/Page → Table | Source node contains an embedded table |
| `IN_SHASTRA` | Gatha → Shastra | **Gatha to its parent Shastra** |
| `HAS_TEEKA` | Shastra → Teeka | **Shastra to its Teeka** |
| `HAS_PUBLICATION` | Teeka → Publication | **Teeka to its Publication** |
| `IN_TEEKA` | GathaTeeka/Kalash → Teeka | **GathaTeeka or Kalash to parent Teeka** |
| `IN_PUBLICATION` | GathaTeekaBhaavarth/KalashBhaavarth/Page → Publication | **Bhaavarth/Page to parent Publication** |

`MENTIONS_TOPIC`, `CONTAINS_DEFINITION`, `IN_SHASTRA`, `HAS_TEEKA`, `HAS_PUBLICATION`, `IN_TEEKA`, and `IN_PUBLICATION` are required for gatha-family stub nodes (Gatha, GathaTeeka, GathaTeekaBhaavarth, Kalash, KalashBhaavarth, Page) to appear in the graph. Each Neo4j label maps to its own UI `EntityKind` with its own filter swatch, node colour, and icon:

| Neo4j label | UI `EntityKind` | Hindi label | Colour token | Icon |
|---|---|---|---|---|
| `Shastra` | `shastra` | शास्त्र | `--cat-shastra` | `BookOpen` |
| `Gatha` | `gatha` | गाथा | `--cat-gatha` | `ScrollText` |
| `GathaTeeka` | `gatha_teeka` | गाथा टीका | `--cat-gatha-teeka` | `BookText` |
| `Teeka` | `teeka` | टीका | `--cat-teeka` | `BookMarked` |
| `GathaTeekaBhaavarth`, `KalashBhaavarth` | `bhaavarth` | भावार्थ | `--cat-bhaavarth` | `NotebookText` |
| `Kalash` | `kalash` | कलश | `--cat-kalash` | `Flower2` |
| `Page` | `page` | पृष्ठ | `--cat-page` | `FileText` |
| `Topic` | `topic` | विषय | `--cat-topic` | `Tag` |
| `Keyword` | `keyword` | कीवर्ड | `--cat-keyword` | `Sparkles` |
| `Publication` | `publication` | प्रकाशन | `--cat-publication` | `Building2` |
| `Table` | `table` | तालिकाएँ | `--cat-table` | `Table` (`IconTable`) |

Stub nodes (placeholders seeded by JainKosh ingestion before NJ ingestion fills them in) are **included by default**; set `NEXT_PUBLIC_GRAPH_EXCLUDE_STUBS=true` to hide them. All eleven kinds (including `table`) appear as toggles in the left filter panel and are persisted via the `?cat=` URL param. `table` nodes are leaf nodes with a smaller visual diameter; clicking one opens `TableModal` via `openTableModal(nk)` rather than selecting it for the DetailsPanel.

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
- `computeHierarchicalPositions(nodeNks, edges, focusNk, canvasW, canvasH)` — BFS from focusNk to assign depth levels; **every node at the same BFS depth is placed on a single horizontal row at the same y**, even when the row extends beyond the visible canvas (pan/zoom expected). Rows are centered on `canvasW/2`. **Nodes unreachable from focusNk are not flattened**: each disconnected component is grouped, a local root chosen by highest degree, BFS run within the component, and that subtree stacked below the main one with a one-row gap so it retains its shape. Returns `Map<nk, {x, y}>`. Exported constants: `HIER_PADDING_TOP` (120 px), `HIER_LEVEL_HEIGHT` (240 px), `HIER_NODE_SPACING` (320 px).
- `computeRadialPositions(nodeNks, edges, focusNk, canvasW, canvasH)` — BFS from focusNk; focus node is placed at the canvas centre and each BFS ring is a concentric circle at `RADIAL_FIRST_RING + (level-1) * RADIAL_RING_SPACING`. Ring radius is clamped upward when `2π·r / n < RADIAL_MIN_ARC` to prevent cards from visually touching. Disconnected components are laid out the same way as in `computeHierarchicalPositions`: highest-degree local root, BFS within the component, stacked as additional outer rings. Returns `Map<nk, {x, y}>`. Exported constants: `RADIAL_FIRST_RING` (220 px), `RADIAL_RING_SPACING` (220 px), `RADIAL_MIN_ARC` (96 px). Wide fan-outs (many same-depth nodes) expand the ring rather than going off-screen horizontally — the radial advantage over hierarchical for large neighbourhoods.

### Per-node expand/collapse layout (GraphCanvas.tsx)

The `useEffect` that recomputes positions on `[nodes.length, layout]` change is split into four explicit paths for **both** `hierarchical` and `radial` modes. State is kept in two refs:

- `lastPositionsRef: Map<nk, {x, y}>` — the most recently committed canvas position of every rendered node.
- `expandSnapshotsRef: Map<expanderNk, Map<nk, {x, y}>>` — copy of `lastPositionsRef` taken right before an incremental expand mutates positions, keyed by the expanding node.
- `expanderNkRef` is set in `handleNodeExpand` for both layouts so the effect knows which node triggered the change.

Branches (evaluated in order):

1. **Snapshot collapse** — `expanderNk` is set, no new nodes arrived, total count dropped, snapshot exists. The snapshot is restored (and consumed) so the user gets back the exact pre-expand view.
2. **Pure collapse** — same shape as (1) but no snapshot. Survivors are pinned at their `prevPos` values; nothing is re-laid-out. Prevents the "ghost nodes scattered across the canvas" symptom when collapsing after a state restored from URL.
3. **Incremental expand** — `expanderPos` known, existing nodes remain, new children arrived. A snapshot is saved, then:
   - **Hierarchical** — new children are placed in a single row at `expanderPos.y + HIER_LEVEL_HEIGHT`, centred on `expanderPos.x` with `HIER_NODE_SPACING` between siblings.
   - **Radial** — the expander is pushed outward along the focus→expander direction by `fanR + RADIAL_FAN_RADIUS * 0.4`, then children are placed on a full **360°** circle around the expander's new position. Ring radius grows when `n * RADIAL_MIN_ARC` exceeds the circumference.
4. **External addition** — new nodes arrived with no expander (e.g. boot-time `expandFromNode` from a dictionary navigation). Existing nodes are pinned at `prevPos`; the new subtree's own BFS layout is run separately and placed to the right of the existing tree via bbox math (`xOffset = (exMaxX + HIER_NODE_SPACING) - subMinX`, `yOffset = exMinY - subMinY`). Previously expanded trees stay exactly where the user put them.
5. **Full BFS** — first load, reset, or layout switch. Clears `lastPositionsRef` and runs `computeHierarchicalPositions` / `computeRadialPositions` from scratch.

After every branch, the committed positions of all `simNodes` are written back into `lastPositionsRef` for the next incremental step **and** mirrored into the zustand store via `setPositions`. The store-backed positions are read on `GraphCanvas` mount to seed `lastPositionsRef`, so the canvas can survive remounts (e.g. when the user navigates to `/dictionary` and back to `/graph`) without losing per-node positions — preventing a full BFS re-layout that would otherwise re-center the existing tree on `canvasW/2`.

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
  tableModalNk: string | null;   // nk of the table whose modal is open; null = closed
};
```

Actions: `selectNode`, `selectEdge`, `clearSelection`, `togglePin`, `expandFromNode`, `setCategoryVisibility`, `setDepth`, `setLayout`, `setCamera`, `reset`, `seedFromPayload`, `openTableModal(nk)`, `closeTableModal()`.

`expandFromNode` de-dupes by `nk`/`id` on merge; seeds new node positions at focus node's position.

---

## 12. Content Pages

All content pages are server components (ISR unless noted).

| Route | Shell | Revalidate | Key data calls |
|---|---|---|---|
| `/` | B | 60s | `getStatsCounts`, `getActivityRecent` |
| `/shastras` | B | 60s | `getShastras` |
| `/shastras/[nk]` | B | 60s | `getShastra`, `getShastraTeekas`, `getPreview` |
| `/shastras/[nk]/gathas/[number]` | C | 60s | `getGatha`, `getKeywordTopics`, optional `getExtractMatch` |
| `/dictionary` | B | 60s | `getKeywordsLetters`, `getKeywordsRecent` |
| `/dictionary/letters/[letter]` | B | 60s | `getKeywords` |
| `/dictionary/[nk]` | B | 60s | `getKeyword`, `getKeywordTopics`. Accepts `?topic=<nk>` — passed to `TopicTreeBrowser` as `targetTopicNk` to trigger ancestor-walk auto-expand. |
| `/topics` | B | 60s | `getTopics` (cards route via `TopicNavAction` — no longer linking to `/topics/[nk]`) |
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

## 13. Matching Engine Integration

The UI consumes matching-engine output from `services/core_service` and turns it into shastra deep-links plus in-page highlights.

### Block hydration

Keyword-definition blocks and topic-extract blocks may include:

```ts
match_natural_keys?: string[];
```

Those keys are injected by the backend and point to `GET /v1/extract-matches/{natural_key}`. They are block-level identifiers, not guaranteed one-to-one with visible references.

### Definition modal flow

Relevant files:

- `src/components/DefinitionModal.tsx`
- `src/components/ViewInShastraButton.tsx`

Flow:

1. `DefinitionModal` renders blocks and references.
2. For each block, `useMatchEntries(match_natural_keys)` fetches full extract-match docs.
3. `findMatchForRef` correlates a visible ref to a fetched match entry primarily by `ref.shastra_name`, then by resolved `गाथा` field when present.
4. Matching links render as:
   - blue when `match.status === 'matched'`
   - muted grey when `match.status === 'unmatched'`
   - muted grey **fallback** when the matcher returned no response AND **all** of the following hold: (a) `ref.shastra_name` is non-null; (b) the shastra natural key is in the **ingested-shastras registry** — i.e. it appears in `GET /v1/shastras` and therefore resolves to a real `/shastras/<nk>` page (no 404); (c) one of `ref.resolved_fields` names a gatha entity keyword — see `GATHA_ENTITY_KEYWORDS` in `src/lib/gatha-content.ts`, which mirrors `reference.entity_keywords.gatha` in `parser_configs/jainkosh.yaml` (`गाथा`, `श्लोक`, `सूत्र`, `दोहक`, `वार्तिक`). The fallback href is `/shastras/<shastra>/gathas/<shastra>:<field>:<value>` (e.g. `/shastras/समयसार/gathas/समयसार:गाथा:1`, URL-encoded). The fallback is suppressed (i) while the matcher request is still in-flight to avoid flicker and (ii) while the registry is still loading. The registry is a module-level cache (`src/lib/shastra-registry.ts` — `loadIngestedShastras` / `useIngestedShastras`) so every consumer in the page shares one round-trip. The fetch paginates in 200-item pages (server caps `/v1/shastras?limit` at 200 in `core_service _limit_offset`) until the total is drained. Natural keys are NFC-normalized on both the registry-write and the lookup side so a parsed Devanagari `ref.shastra_name` matches the DB-side key regardless of combining-mark ordering.
   - hidden when `match.status === 'target_missing'`

The decision is centralised in `planRefLink(ref, matchEntry)` in `src/components/ViewInShastraButton.tsx`; `RefMatchLink` renders the chosen link. `DefinitionModal` consumes `RefMatchLink` from both the visible `RefBadge` and the `समान संदर्भ` popover `RefListItem` paths.

Important invariant:

- UI `pickRefsToShow` behavior must stay aligned with the Python port in `jain_kb_common.matching.ref_selection`, because worker eligibility uses the same logic.

### Reading-page highlight flow

Relevant files:

- `src/lib/gatha-content.ts`
- `src/app/[locale]/(reading)/shastras/[nk]/gathas/[number]/page.tsx`

Flow:

1. `buildGathaHref` creates `/shastras/<shastra>/gathas/<number>?match=<match_natural_key>`.
2. The reading page fetches the extract-match doc when `searchParams.match` is present.
3. Highlighting is applied only when:
   - `match.status === 'matched'`
   - the current panel `naturalKey` equals `match.target.natural_key`
   - `char_start` and `char_end` are valid in NFC-normalized text

Supported highlighted targets today:

- prakrit gatha
- sanskrit gatha
- sanskrit teeka
- hindi bhaavarth
- kalash sanskrit
- kalash hindi
- kalash bhaavarth

---

## 14. Testing

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
| `lib/gatha-content.test.ts` | Bracket-tagged teeka term extraction and splitting; `GATHA_ENTITY_KEYWORDS` mirrors `parser_configs/jainkosh.yaml`; `getRefGathaEntity` field detection; `buildShastraGathaHref` natural-key gatha segment + URL encoding |
| `components/ViewInShastraButton.test.ts` | `planRefLink` — matched / unmatched / fallback-grey (shastra in ingested set + gatha-entity field) / none decisions; suppression when shastra is not in the registry or while the registry is loading |
| `lib/shastra-registry.test.ts` | `loadIngestedShastras` returns the set of natural keys; single-flight cache; skips empty natural_keys; resets the cache on rejection so the next call retries |
| `lib/feedback-validation.test.ts` | Valid data passes, type required, message length bounds, email regex |
| `components/DefinitionModal.test.ts` | `getBlockBorderClass`, `formatRefSourceLabel`, `parseMarkdownSegments` (including null-input guards), `pickRefsToShow`, `pickHiddenRefs`, `groupTopicExtractsByShastra` |

---

## 15. Implementation Phase Log

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
| Hierarchical same-level-y fix | ✅ | Removed `HIER_MAX_PER_ROW` row wrapping in `computeHierarchicalPositions`; all nodes at the same BFS depth now share a single y, extending horizontally off-screen when needed (relies on pan/zoom) |
| Gatha/Shastra graph fix | ✅ | Added `MENTIONS_TOPIC` and `IN_SHASTRA` to expand/landing Cypher; fixed isolated focus-node kind fallback; added gatha/shastra UI tests |
| DefinitionModal polish | ✅ | Dividers between sections/definitions; left border on blocks with references (amber=teeka, sky=shastra); all non-inline qualifying references shown per block (inline fallback capped at 1); teeka badge now shows `shastra_name, teeka_name`; DetailsPanel body fixed with `flex-1 min-h-0` so panel scrolls and CTA stays visible |
| DefinitionModal ref expansion | ✅ | `pickRefsToShow` now returns all non-inline refs (was capped at 1); `pickHiddenRefs` computes the remaining matched refs not surfaced by `pickRefsToShow`; **`समान संदर्भ`** button (accent red, bold, `ml-auto`) opens a 480px `Popover` (column layout, `align="end"`) showing hidden refs — no modal state pollution |
| Null text_devanagari fix | ✅ | `DefinitionBlock.text_devanagari` typed as `string \| null`; `parseMarkdownSegments` / `renderInlineMarkdown` accept null (return empty); `BlockPreview` guards null before `.length` check — prevents runtime TypeError on nodes whose blocks have no Devanagari text |
| Topic extract shastra grouping | ✅ | `groupTopicExtractsByShastra` groups `topicExtracts` by `shastra_name` (from primary shown ref); each group rendered as a collapsible `ShastraAccordion` with chevron toggle, count badge, and indented block list. Blocks with no resolvable ref → `अन्य` group. `see_also` blocks excluded. Order of first occurrence preserved. |
| Radial layout | ✅ | `computeRadialPositions` in `graphViewHelpers.ts`; BFS-concentric rings, `RADIAL_MIN_ARC` clamp prevents overlap; `GraphCanvas` static-layout branch extended to cover both `hierarchical` and `radial`; radial radio enabled in `CategoryFilterList` |
| Expand/collapse UX pass | ✅ | Connected-component fallback in `computeHierarchicalPositions` / `computeRadialPositions` (was flattening unreachable nodes into one row); radial incremental expand rewritten Neo4j-style (expander pushed outward, children placed in a 360° ring); hierarchical incremental expand keeps existing nodes pinned and drops new children in a single row at `HIER_LEVEL_HEIGHT` below the parent, centred on `expanderPos.x`; **snapshot-restore on collapse** via `expandSnapshotsRef`; **pure-collapse fallback** preserves surviving positions when no snapshot exists; **external addition** path keeps existing tree pinned and places new subtree to the right via bbox math; `handleNodeExpand` now captures expander for hierarchical too |
| Samaan sandarbh grey fallback link | ✅ | Refs whose `shastra_name` is present in the ingested-shastras registry (from `GET /v1/shastras` — meaning `/shastras/<nk>` resolves to a real page) AND whose `resolved_fields` include an entry whose field is in `GATHA_ENTITY_KEYWORDS` (`गाथा`, `श्लोक`, `सूत्र`, `दोहक`, `वार्तिक` — mirrors `parser_configs/jainkosh.yaml` `reference.entity_keywords.gatha`) now render a muted-grey fallback link in the समान संदर्भ popover (and the inline `RefBadge`) when the matcher produced no response. Href format: `/shastras/<shastra>/gathas/<shastra>:<field>:<value>` (e.g. `/shastras/समयसार/gathas/समयसार:गाथा:1`). Decision lives in `planRefLink` (`src/components/ViewInShastraButton.tsx`); ingested set comes from `useIngestedShastras` (`src/lib/shastra-registry.ts`, module-cached single-flight). Fallback is suppressed both while the matcher request is in-flight and while the registry is loading. |
| Keyword modal shastra grouping | ✅ | `KeywordDefinitionBlocks` groups all blocks across definitions in a section by shastra via `groupTopicExtractsByShastra`, rendered as `ShastraAccordion`. `KeywordSectionAccordion` wraps each section (h2_text) in a top-level collapsible matching the विषय अंश pattern — giving keywords a 3-level hierarchy: section → shastra → block. |
| Keyword & topic detail — column navigator | ✅ | Both pages now use the new `TopicTreeBrowser` to render a horizontal column-based topic navigator (column 0 seeded server-side; further columns lazily fetched). Keyword page seeds from `getKeywordTopics`; topic page seeds from `getTopicNeighbors` filtered to inbound `PART_OF` (the edge type the navigation service uses for parent→subtopic). ASCII dotted numbering `1`, `1.1`, … per the graph details-panel convention. Per-row `BookOpen` pill opens `DefinitionModal` only when `getEntityDetail('topic', nk)` confirms non-empty `topicExtracts`; `›` chevron shows whenever `stats.is_leaf === 0`; both render together when both apply. Label-button expand is disabled for confirmed leaves. The `IS_A` and `PART_OF` "ग्राफ संबंध/पड़ोसी" sections were removed (data shown was incorrect); `RELATED_TO` retained. Topic-page right-rail "ग्राफ में खोलें" CTA standardised to the keyword-page bordered-accent style. `getKeywordTopics` response type in `src/lib/api/navigation.ts` corrected from `display_text`/`topic_path` to the actual backend shape (`display_text_hi`, `edge_type`, `is_stub`). `DefinitionModal` gained a fallback empty-state line ("कोई परिभाषा/अंश उपलब्ध नहीं") when neither `definitionSections` nor non-empty `topicExtracts` are supplied. |
| Label-seeds + topic-page consolidation | ✅ | `TopicTreeBrowser` now segregates label-seed children (topics with null `topic_path`) into a bottom "संबंधित विषय" sub-block per column, keeping numbered paths contiguous. Each seed row has a `Link2` toggle that lazily fetches `getTopicRelated` + `getTopicMentionedKeywords` and shows the merged related-topics/keywords inline. Related-topic clicks resolve via cached `EntityDetail`: extracts present → `DefinitionModal`; otherwise open `/dictionary/<parent_kw>?topic=<nk>` in a new tab. New backend endpoints `GET /v1/topics/{nk}/ancestors` (used for auto-expand from `?topic=`) and `GET /v1/topics/{nk}/related` (returns Topic+Keyword RELATED_TO neighbours including stubs — `/neighbors` cannot, since its RELATED_TO clause is Topic-only). `DefinitionModal` gained optional `navigateHref`/`navigateLabel` props for the top "शब्द पृष्ठ पर इस विषय पर जाएँ" link (suppressed when target keyword equals the page's `currentKeywordNk`). New `TopicNavAction` client component replaces all `<Link href="/topics/${nk}">` call sites (topics list, search results, gatha reading, `TaggedTermPopover`); the standalone `/topics/[nk]` page has been removed. |
| Phase 9 — Tables modal + graph integration | ✅ | Added `table` to `EntityKind`, `CONTAINS_TABLE` to `EdgeKind`, `TableSummary`/`TableFull` types. New `--cat-table*` design tokens. `IconTable` reserved. `NodeCard`, `CategoryFilterList` (filter chip "तालिकाएँ", default ON), `BadgeChip`, `RelationConnector` updated for table kind. `getTable()`/`listTablesForParent()` API fetchers. `TableModal` component (cells-rendered table, caption, source link, mentioned-keyword/topic chips, dev-only raw HTML pane, per-nk cache). `graphStore` extended with `tableModalNk`, `openTableModal`, `closeTableModal`. Graph page intercepts table node clicks to open modal. i18n `tables.*` keys in both locales. All 467 tests pass. **Deferred**: "तालिकाएँ" sections on topic/keyword/gatha detail pages, reader-page chips, dedicated `TableModal.test.tsx` rendering test. |
| संबंधित panel + graph links + verse rendering | ✅ | **Graph link fix**: `PanelActionsMenu` gains a third "ग्राफ में खोलें" action (`Network` icon, new tab). Gatha panel's `actionsSourceNk` corrected from the broken `gatha:{postgres_nk}` format to the canonical Neo4j key `${shastraPrefix}:गाथा:${gathaNumStr}`. Standalone bottom "ग्राफ में खोलें" button removed. **संबंधित panel** (renamed from "कलश"): `teekas.role` column added (migration 0021, propagated from NJ parser config); `_get_kalashas_for_gatha` JOINs `Teeka` and returns `teeka_natural_key` + `is_secondary`; secondary kalashas (Jaysenacharya's standalone gathas) fetch from `gatha_prakrit`/`gatha_teeka_*` Mongo collections; tab labels use `कलश:` prefix for primary and `गाथा:` prefix for secondary; sorted ascending by numeric `kalash_number`. **Word meanings**: `kalash_word_meanings` fetched and returned as `word_meanings` in `GathaKalash`; rendered as "शब्दार्थ" panel. **`BhaavarthPanel` verse variant**: `variant="verse"` prop uses `whitespace-pre-wrap` instead of `teekaMarkdownToHtml` to avoid inter-line paragraph margins in doha/gatha text. |
| Bhaavarth inline shabdaarth/anvayarth extraction | ✅ | `BhaavarthPanel` prose mode now segments bhaavarth into inline `chips` + `html` runs via `parseBhaavarthSegments`. Final approach is line-oriented, not paragraph-oriented: it recognizes both `**[term]**` followed by Hindi meaning lines and single-line `[term] meaning` rows. When at least 3 compact bracket items are present in the bhaavarth, contiguous compact runs are replaced inline with a lightweight शब्दार्थ-style block: `ShabdaArthSection` term row plus derived `अन्वयार्थ` (space-joined meanings); clicking a chip highlights its meaning in the अन्वयार्थ below. The panel intentionally does **not** render a separate `शब्दार्थ` heading for these inline replacements. Highlighted prose still shows the chip/anvayarth block because segmentation happens before local highlight rendering. Parser guardrails after iteration: each meaning is truncated at the first Devanagari full stop `।` so the chip's अन्वयार्थ contains only the meaning sentence, not the transition prose that introduces the next mapping (this also prevents the last `[term]`'s meaning from absorbing trailing verse markers like `॥७॥` or closing paragraphs). Meaning-line collection stops at: bullet lines (`- …`), `अब …` paragraph transitions, italic `*((…))*` blocks, non-bracket bold conclusion lines (e.g. blue takeaway lines), full-line verse markers `॥३॥`, and lines whose trailing token is a verse marker. The earlier `MAX_MEANING_LEN = 260` cap was removed — it was excluding legitimate long-but-single-sentence meanings (`[वन्दित्तु]`, `[समयपाहुडं]`) and stranding the trailing bracket entries as lonely 1-item chip blocks. Regression coverage lives in `src/__tests__/components/BhaavarthPanel.test.ts`. |
| ShabdaArthSection — inline अन्वयार्थ highlight | ✅ | Replaced `TaggedTermPopover` (floating popover on click) with `ShabdaArthSection` (`'use client'`, `useState`) across all शब्दार्थ usage sites. Clicking a term chip highlights its meaning inline inside the अन्वयार्थ text via `<mark>`; clicking again deselects. Falls back gracefully when the meaning is not a substring of the anvayarth. Sites updated: `BhaavarthPanel` chips segments, gatha-page शब्दार्थ section (uses `full_anyavaarth` from API, falls back to joined meanings), kalash word-meanings in the संबंधित panel, and the kalasha detail page (अन्वयार्थ now rendered here too). `TaggedTermPopover` kept but is no longer used for शब्दार्थ. All 471 tests pass. |
| Combined-gatha notice + parser cleanup | ✅ | **Parser (`parse_page.py`)**: `_clean_verse_text` helper strips `(N)` mid-verse line-number labels (ASCII + Devanagari) and trailing `॥N॥`/`||N||` markers from every gatha's prakrit/sanskrit text — single and combined alike. Multi-gatha splitting (`_split_combined_text_by_markers`) is now positional: finds the first N−1 verse-end markers of any number M rather than requiring M to match the gatha number; split markers are excluded from chunks. `_clean_gatha_chunk` strips residual `(N)` and verse markers from each split chunk. **UI (`page.tsx`)**: `combinedGathaNotice` is derived from `primaryMapping?.is_related`; when non-empty it renders a muted pill "गाथा X, Y, Z का/की संयुक्त" (feminine "की" for टीका, masculine "का" for शब्दार्थ and हिन्दी भावार्थ) placed inline beside the panel heading. **`TeekaPanel` / `TabbedPanel`**: both accept an optional `notice?: ReactNode` prop rendered in a `flex-wrap items-center gap-2` wrapper alongside the heading. |
| DefinitionModal view toggle + list_number | ✅ | **Parser**: added `Block.list_number: Optional[int]` to `workers/ingestion/jainkosh/models.py`. `parse_blocks._get_ol_list_number(li_node)` computes the rendered `<ol>/<li>` sequence number (respects `<ol start="N">`). Called from `make_block` when `node.tag == "li"`. Computed on the original DOM element before `split_element_at_inline_refs` to avoid the synthetic-node parent-detachment bug (synthetic nodes have `parent.tag == "body"`, not `"ol"`); passed as explicit `list_number` kwarg to `make_block` so all split sub-blocks inherit the correct value. All 6 golden JSONs regenerated. **UI — `DefinitionBlock`**: `list_number?: number | null` added to type. **UI — `DefinitionModal`**: `ViewToggle` pill (accent-themed: `bg-accent-soft` wrapper, `bg-accent` active tab) placed in the modal header. Default view is **क्रमानुसार** (sequential): topic extracts grouped by consecutive `list_number` with a leading number badge; keyword definitions numbered by `definition_index`. `ModalBlock` gained `showShastra?: boolean`; sequential views pass `showShastra={true}` so shastra + teeka name appear in ref badges. **शास्त्रानुसार** (by shastra) view is the prior accordion behaviour, unchanged. All 467 UI tests pass. |

---

## 16. Design Docs Index

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

---

## Special Notes

### Combined-gatha notice (2026-06-09)

When a gatha page was parsed from a multi-gatha HTML file (e.g. `020-021-022.html`), teeka/bhaavarth/shabdaarth content is shared across all the individual gathas expanded from that page. A small muted pill is shown **inline beside the panel heading** in the शब्दार्थ, टीका, and हिन्दी भावार्थ panels to communicate this.

**Data source**: `TeekaGathaMapping.is_related` (Mongo field, populated by the NJ parser's `envelope.py` `_related()` helper). Accessed in the page as `primaryMapping?.is_related`.

**Text format**: "गाथा २०, २१, २२ का संयुक्त" (शब्दार्थ / हिन्दी भावार्थ) · "गाथा २०, २१, २२ की संयुक्त" (टीका — feminine). Gatha numbers are sorted and converted to Devanagari via `toDevanagariNumerals`. Renders `null` for single gathas (`is_related` is empty).

**Files touched**: `page.tsx`, `TeekaPanel.tsx` (`notice?: ReactNode` prop), `TabbedPanel.tsx` (`notice?: ReactNode` prop).

---

### Gatha reader page — संबंधित panel & sidebar (2026-06-08)

**Files touched**
- `src/app/[locale]/(reading)/shastras/[nk]/gathas/[number]/page.tsx`
- `src/components/GathaReaderLayout.tsx`
- `src/lib/format/teeka-markdown.ts`
- `src/app/globals.css` (`.teeka-content p`)
- Backend: `services/core_service/domains/data/services/gathas.py`

**1. Primary kalash शब्दार्थ rendering (संबंधित panel)**
Primary kalash `word_meanings.entries` now render as `TaggedTermPopover` chips in the same format as the gatha's own शब्दार्थ. The अन्वयार्थ is computed client-side by joining `entry.meaning` values in `position` order (NOT `kalash.hindi`). Backend `GathaKalash.word_meanings` has no `full_anyavaarth` field — derive it on the client.

**2. Secondary-kalash bhaavarth duplication (server-side filter)**
NJ ingestion writes secondary-kalash extra-gatha bhaavarths to `gatha_teeka_bhaavarth_hindi` with `gatha_teeka_natural_key = {teeka_j_nk}:कलश:{N}` and `gatha_number = N` (envelope.py:476-485). The backend's `_get_gatha` query (`gatha_number = N` + shastra-prefix regex) used to pick these up as if they were the real gatha's bhaavarths. Fix: added `$not: {$regex: ":कलश:"}` to the teeka_* query in `services/core_service/domains/data/services/gathas.py`. The UI no longer needs to filter.

Secondary kalashas (Jaysenacharya's "extra gathas") still appear in the संबंधित panel of the **preceding primary gatha** (via the `kalashes` payload). The deduplication only suppresses them as a duplicate tab in the **same gatha's** right-panel हिन्दी भावार्थ.

When rendering a secondary-kalash's bhaavarth in the संबंधित panel, skip it iff `kalash.is_secondary && kalash.kalash_number === gathaNumStr` (i.e., the kalash IS the current gatha's own extra entry — its bhaavarth will be a tab on its own future gatha page).

**3. React key warnings — `Inner` / `<aside>`**
Next.js 16 + React 19 (Turbopack) reconciles `createElement` varargs as a children array and trips `warnOnInvalidKey` on positional children when sibling counts are conditional. Symptoms: warning at `<aside>` inside `Inner` (in `GathaReaderLayout`) on gatha 12 (and similar shapes).

Mitigations applied:
- Added explicit `key="main"` on `mainColumn`'s root `<div>` and `key="sidebar"` on the sidebar `<aside>` in `page.tsx`.
- Added `key="right"` on `<MentionedRightColumn />` in `GathaReaderLayout.tsx`.
- Added `key="teeka"`, `key="bhaavarth"`, `key="topics"` on the three direct children of `<aside>`.
- Removed JSX `{/* comments */}` from the sidebar — Turbopack-compiled comments can manifest as additional array slots in some configurations.

**Rule of thumb**: in this codebase, any JSX element passed as a `ReactNode` *prop* to a sibling-rendering wrapper (like `GathaReaderLayout`) should carry an explicit stable `key` if the wrapper renders conditional siblings.

**4. Backend data-model reference for "extra gathas" (secondary kalashes)**
See `docs/design/data_sources/nikkyjain/nj_ingestion.md` and `nj_parser.md`.
- Parser classifies HTML pages not in `primary_index` but in `secondary_index` as `secondary_kalash` → emitted as `KalashExtract` (separate from `GathaExtract`).
- Ingestion (`workers/ingestion/nj/envelope.py::_build_mongo_for_secondary_kalash`) emits:
  - `gatha_prakrit` with `gatha_natural_key = {teeka_j_nk}:कलश:{N}`
  - `gatha_teeka_sanskrit` with `gatha_teeka_natural_key = {teeka_j_nk}:कलश:{N}`
  - `gatha_teeka_bhaavarth_hindi` with the same `:कलश:` marker and `gatha_number = norm_kalash_num`
- The `:कलश:` substring is the canonical discriminator between a real gatha's teeka content and a secondary-kalash extra-gatha's content sharing the same `gatha_number`.
