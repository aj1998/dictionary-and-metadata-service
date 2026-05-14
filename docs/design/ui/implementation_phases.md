# UI Implementation Phases

Step-by-step build plan for the Jain Knowledge Base public UI. Each phase
produces a shippable increment; every later phase depends on the ones before
it. Spec references in parentheses point to the eight design documents in
this folder.

---

## Phase 0 — Project Bootstrap & Design System

**Goal**: empty repo → runnable Next.js app with the complete token layer,
fonts, and shadcn primitives wired in. No pages, no data.

### 0.1 — Next.js + Tailwind scaffold

- Create the Next.js 14 (App Router) project at `ui/`.
- Install: `tailwindcss`, `postcss`, `autoprefixer`, `clsx`,
  `lucide-react`, `zustand`, `d3-force`, `@types/d3-force`,
  `next-intl`, `@radix-ui/*` (via shadcn CLI).
- Add `shadcn` and run `init`. Accept defaults.
- Install shadcn components needed across all phases:
  `Button`, `Card`, `Switch`, `Tabs`, `Tooltip`, `Pagination`,
  `Sheet`, `Popover`, `Separator`, `Badge`.

### 0.2 — CSS token layer

Create `ui/src/styles/theme.css`. Declare every CSS variable listed in
`01_design_system.md §1` under `:root`:

```
--background, --surface, --surface-muted
--foreground, --foreground-muted, --foreground-subtle
--border, --border-strong
--accent, --accent-hover, --accent-foreground, --accent-soft
--ring
--success, --warning, --danger
--graph-grid-dot, --graph-edge, --graph-edge-muted
--node-bg, --node-bg-selected, --node-border
--node-shadow, --node-shadow-hover
--cat-shastra, --cat-gatha, --cat-topic, --cat-keyword
--radius-sm, --radius-md, --radius-lg, --radius-pill
```

Use exact values from `01_design_system.md §1` and `§4`.

### 0.3 — Tailwind config

In `tailwind.config.ts`:
- Map every `--*` token to a Tailwind utility via `@theme inline`.
  E.g. `colors.accent = 'var(--accent)'`.
- Add `fontFamily.serif-hindi` and `fontFamily.sans` (see §0.4).
- Add `fontSize` entries for `text-display`, `text-h1` … `text-xs`
  using the scale in `01_design_system.md §2`.
- Add `borderRadius` entries (`sm`, `md`, `lg`, `pill`).
- Add `boxShadow` entries (`node`, `node-hover`, `modal`).

### 0.4 — Fonts

In `ui/src/app/layout.tsx` (root layout):
- Load `Noto_Serif_Devanagari` with weights `400,500,600,700` via
  `next/font/google`. Assign CSS variable `--font-serif-hindi`.
  Map to Tailwind class `font-serif-hindi`.
- Load `Inter` with the same weights. Assign `--font-sans`.
  Map to `font-sans`.
- Set `font-display: swap` on both.
- Add a fallback stack `'Mangal', 'Devanagari MT', serif` for Noto.
- Preload only 500+600 weights of Noto on initial HTML; rest async.
  (See `08_accessibility_and_i18n.md §2`.)

### 0.5 — Global CSS

In `ui/src/styles/globals.css`:
- Import `theme.css`.
- Set `body` background to `var(--background)`, color to
  `var(--foreground)`, font to `font-serif-hindi`.
- Add `@keyframes shimmer` (1.4 s infinite gradient sweep over
  `--surface-muted`) for skeleton blocks.

### 0.6 — next-intl setup

- Create `ui/messages/hi.json` and `ui/messages/en.json`.
  Populate with all Hindi chrome strings that will appear across
  the app (nav labels, button labels, error messages, section
  headings). English file carries transliterations and tooltips.
- Wire up `next-intl` middleware and root layout provider.
- Default locale `hi`. Locale stored in a cookie.
  (See `08_accessibility_and_i18n.md §1`.)

### 0.7 — Devanagari utilities

Create `ui/src/lib/format/devanagari.ts`:
- `toDevanagariNumerals(n: number): string` — maps ASCII digits
  0–9 to ०–९.
- `normalizeNFC(s: string): string` — wraps `s.normalize('NFC')`.
- `minGraphemeLength(s: string): number` — uses `Intl.Segmenter`
  to count grapheme clusters.

### Checkpoint 0

Run `pnpm dev`. The app loads at `localhost:3000` with the correct
background colour (`#F7F7F8`), no font flash (FOUC), and Tailwind
utilities resolve token values.

---

## Phase 1 — Global Shell & Navigation

**Goal**: every page can be wrapped in one of the three page shells;
the TopBar renders on all routes.

### 1.1 — `TopBar` component

File: `ui/src/components/TopBar.tsx`

Implement exactly as specified in `02_layout_and_navigation.md §1`:
- 64 px desktop / 56 px mobile height.
- Left: `BookOpen` icon 24 px in `--accent` + two-line brand block
  linking to `/`.
- Center: 480 → 360 → 240 px pill search input, `Search` icon,
  placeholder from `hi.json`, routes to `/search?q=…` on submit.
- Right: horizontal flex of nav items; active state derived from
  `activeRoute` prop (pill bg `--accent-soft`, `--accent` outline
  30% alpha).
- Nav items and routes per the table in §1.
- At `< 1200 px`: collapse `शास्त्र`, `विषय`, `प्रतिक्रिया` into
  a "More ▾" dropdown.
- At `< 768 px`: search collapses to icon-only `Search` button;
  nav items collapse behind `Menu` icon → off-canvas `Sheet` drawer.
- Props: `{ activeRoute: string; locale: 'hi' | 'en' }`.
- Wrap in `<nav aria-label="मुख्य">` (see `08_accessibility_and_i18n.md §5`).

### 1.2 — `BreadcrumbBar` component

File: `ui/src/components/BreadcrumbBar.tsx`

- Segments separated by `›`.
- Last segment unlinked, bold.
- Titles truncated with ellipsis beyond 32 chars.
- Accepts `segments: Array<{ label: string; href?: string }>`.
  (See `05_components.md §13`.)

### 1.3 — `Footer` component

File: `ui/src/components/Footer.tsx`

- 56 px bar. `text-xs --foreground-muted` centered.
- Left: `© जैन ज्ञान कोष` + version tag.
- Right: `/about`, source attribution links, `LocaleSwitch`.
  (See `02_layout_and_navigation.md §3`.)

### 1.4 — Shell layouts

#### Shell A — Graph shell
File: `ui/src/app/graph/layout.tsx`

Full-bleed three-pane grid:
- `TopBar` full-width at top.
- Below: `flex-row` full height.
  - Left pane: 280 px, `--surface`, right border `1 px --border`.
    Collapses to 56 px icon-rail at `< 1100 px`; rail has `LayoutList`
    toggle opening an overlay drawer.
  - Center: `flex-1`, no margin.
  - Right pane: 380 px, `--surface`, left border `1 px --border`.
    Hidden until a node is selected. At `< 1100 px`: becomes a
    bottom sheet (75 vh). Slides in 200 ms `ease-out`.
- No footer on this shell.
  (See `02_layout_and_navigation.md §2 Shell A`.)

#### Shell B — Centered content shell
File: `ui/src/app/(content)/layout.tsx`

- `max-w-[1200px]` centered, 24 px horizontal padding, 32 px top
  padding under nav.
- `TopBar` + content area + `Footer`.
- Content sections wrapped in white surface cards (`--surface`,
  `--radius-md`, `--node-shadow`).
  (See `02_layout_and_navigation.md §2 Shell B`.)

#### Shell C — Split-reading shell
File: `ui/src/app/(reading)/layout.tsx`

- `TopBar` full-width.
- Below: 65% reader column + 35% sticky sidebar.
- Stacks to single column at `< 1024 px`.
  (See `02_layout_and_navigation.md §2 Shell C`.)

### 1.5 — Skeleton primitives

File: `ui/src/components/Skeleton.tsx`

Export `Skeleton.Card`, `Skeleton.Row`, `Skeleton.Title`.
All use `--surface-muted` fill + the shimmer keyframe from `globals.css`.
No spinners anywhere.
(See `02_layout_and_navigation.md §5` and `05_components.md §17`.)

### 1.6 — Root layout

`ui/src/app/layout.tsx`:
- Mount `TopBar` with `activeRoute` derived from `usePathname()`.
- Wrap in `next-intl` provider.
- Set `<html lang="hi">`.

### Checkpoint 1

Navigate to any stub route. TopBar renders with correct palette,
active-state pill, responsive collapse. Shell A is full-bleed.
Shell B shows centered max-width. Shell C shows two columns.

---

## Phase 2 — Atomic & Shared Components

**Goal**: all reusable leaf components exist and are visually correct
against `01_design_system.md`. The graph page and all content pages
will compose these.

### 2.1 — `BadgeChip`

File: `ui/src/components/BadgeChip.tsx`

Per `05_components.md §5`:
- Props: `{ kind: EntityKind; size?: 'sm' | 'md'; labelHi?: string; labelEn?: string }`.
- Pill radius, 22 px (`md`) or 18 px (`sm`) tall, 10 px H padding.
- Background `--cat-<kind>`, text white, `text-xs` 600.
- Default Hindi+English labels per entity kind.

### 2.2 — `StatTile` & `StatTileRow`

Files: `ui/src/components/StatTile.tsx`,
`ui/src/components/StatTileRow.tsx`

Per `05_components.md §6–7` and `01_design_system.md §7`:
- `StatTile`: white card, `--radius-md`, `--border`, 16 px padding.
  Count rendered with `toDevanagariNumerals()` at `text-h1` 600.
  Label `text-xs` muted uppercase.
- `StatTileRow`: renders exactly 3 `StatTile`s in a flex row with
  12 px gap.

### 2.3 — `ConnectedItemRow`

File: `ui/src/components/ConnectedItemRow.tsx`

Per `05_components.md §8`:
- Props: `{ kind; titleHi; titleEn?; href?; onClick? }`.
- 1 px `--border`, `--radius-md`, 12 px padding.
- Left badge (`BadgeChip` sm) + title stack + `ChevronRight` 18 px.
- Hover: row bg `--surface-muted`, chevron `--accent`.
- When `href` is present, render as `<a>`; otherwise `<button>`.

### 2.4 — `PrimaryCTA`

File: `ui/src/components/PrimaryCTA.tsx`

Per `05_components.md §10` and `01_design_system.md §8`:
- 44 px tall, full width minus 24 px inset each side.
- `--accent` bg, white text, `--radius-md` (12 px).
- Left: bold Hindi label + English subtitle.
- Right: `Bookmark` icon 18 px white 90% opacity.
- Hover: `--accent-hover`, `--node-shadow-hover`.
- Props: `{ labelHi; labelEn?; icon?; href?; onClick? }`.

### 2.5 — `KeywordCard` / `TopicCard` / `GathaTile`

File: `ui/src/components/ListCards.tsx`

Per `05_components.md §14`. Shared `ListCardProps`:
`{ kind; titleHi; titleEn?; meta?; count?; href }`.
- White surface, `--radius-md`, hover lift to `--node-shadow-hover`.
- Devanagari numeral for `count`.

### 2.6 — `LocaleSwitch`

File: `ui/src/components/LocaleSwitch.tsx`

Per `05_components.md §16`. Small `हिन्दी / English` toggle in the
footer. On click, sets locale cookie consumed by `next-intl`.

### 2.7 — Iconography constants

File: `ui/src/lib/icons.ts`

Export the reserved icon map from `01_design_system.md §6` as typed
constants so components never import the wrong icon:
```ts
export { Search, Home, Network, BookOpen, ... } from 'lucide-react';
```
Stroke width 1.5 for all icons is set by a global Lucide provider or
a thin wrapper component.

### Checkpoint 2

Storybook (or a simple `/dev` route) renders every atomic component
in all states: `BadgeChip` × 4 kinds × 2 sizes, `StatTile`,
`PrimaryCTA` resting+hover, `ConnectedItemRow` link+button modes.
All colours match the palette tokens.

---

## Phase 3 — API Client Layer

**Goal**: thin, typed fetch clients for all four backend services.
No UI yet; just the data layer.

### 3.1 — Base fetch wrapper

File: `ui/src/lib/api/_fetch.ts`

```ts
async function apiFetch<T>(baseUrl: string, path: string,
  init?: RequestInit): Promise<T>
```
- Reads `baseUrl` from env vars (`METADATA_SVC_URL` etc., see
  `07_api_integration.md §1`).
- URL-encodes path segments via `encodeURIComponent` (Devanagari-safe,
  see `07_api_integration.md §8`).
- Throws typed `ApiError` on `4xx` / `5xx`.

### 3.2 — Service clients

Files: `ui/src/lib/api/metadata.ts`,
`ui/src/lib/api/data.ts`,
`ui/src/lib/api/navigation.ts`,
`ui/src/lib/api/query.ts`

Implement each function listed in `07_api_integration.md §2–5`.
Type all request and response shapes with TypeScript interfaces.
Export named functions only (no default exports).

Examples:
```ts
// navigation.ts
getNavLanding(): Promise<GraphPayload>
expandNode(nk: string, depth: 1|2|3|4): Promise<GraphPayload>

// data.ts
getActivityRecent(): Promise<ActivityRow[]>
getStatsCounts(): Promise<EntityCounts>
getEntityDetail(kind: EntityKind, nk: string): Promise<EntityDetail>
```

### 3.3 — Shared types

File: `ui/src/lib/types.ts`

Central type definitions reused by all clients and components:
```ts
type EntityKind = 'shastra' | 'gatha' | 'topic' | 'keyword';
type EdgeKind = 'HAS_TOPIC' | 'MENTIONS_KEYWORD' | ... (all 11 kinds);
interface GraphNode { nk, kind, title_hi, title_en?, meta?, degree }
interface GraphEdge { id, src, dst, kind, weight }
interface GraphPayload { nodes, edges, focus_nk, depth }
```
(Complete list from `07_api_integration.md §3`.)

### Checkpoint 3

Unit tests for all API clients using `msw` (mock service worker).
Each client function returns the expected typed shape. Error cases
throw `ApiError` with the right status.

---

## Phase 4 — Graph Page: Canvas Foundation

**Goal**: `/graph` renders a pannable, zoomable SVG canvas with the
dotted-grid background and can display static `NodeCard` elements with
`RelationConnector` edges. No interactivity yet.

### 4.1 — `NodeCard` component

File: `ui/src/components/NodeCard.tsx`

Per `03_graph_traversal_page.md §4` and `05_components.md §2`.

Structure (exact as specced):
```
4 px top stripe (--cat-* color, top corners rounded)
Header row (40 px): icon box + type labels (Hi + En) + ChevronRight
Separator (1 px --border)
Body row: Hindi name (text-h3 600, line-clamp-2) + En transliteration (text-xs muted)
```

States:
- **Resting**: `--node-bg`, `--node-border`, `--node-shadow`.
- **Hover**: `--node-shadow-hover`, border → `--accent` 40% alpha.
  Transition 120 ms `ease-out`. No transform.
- **Selected**: fill `--accent`, all text white, no cat-stripe
  (merged into fill), border `--accent`, shadow stays at hover level.
  Fill transition 160 ms `ease-in-out`.
- **Faded**: `opacity: 0.25`, `pointer-events: none`.
- **Pinned**: `Pin` icon 12 px top-right opposite the chevron.

Dimensions: 220 px wide, height auto (min 64 px), `--radius-md`.

Props match `05_components.md §2 NodeCardProps`.

When used inside SVG: rendered inside `<foreignObject>`.

### 4.2 — `RelationConnector` component

File: `ui/src/components/RelationConnector.tsx`

Per `03_graph_traversal_page.md §5` and `05_components.md §3`.

Pure SVG. Renders:
1. Cubic Bézier `<path>`: stroke `--graph-edge`, 1.5 px,
   `stroke-linecap: round`.
2. Two 6 px filled `--graph-edge` `<circle>` endpoints.
3. `<foreignObject>` at path midpoint holding the pill label.
   - Pill: `--surface`, `--border`, `--radius-pill`, 6/2 px padding.
   - Text: `text-xs` 500, `--foreground-muted`, Hindi label from
     the `EdgeKind → pill label` table in §5.
   - Pill rotates with path tangent only between −20° and +20°;
     flat outside that range.
4. States: inactive → stroke `--graph-edge-muted`, pill 50% opacity.
   Active (incident to hovered/selected) → stroke `--accent`,
   pill border `--accent`.
   Active edge draw-in animation: 300 ms path `stroke-dasharray` trick.

Control points for the Bézier: offset 80 px from each anchor along
the card's outward normal. Anchors attach to the center of the nearest
card side per `03_graph_traversal_page.md §4.4`.

Props: `RelationConnectorProps` from `05_components.md §3`.

### 4.3 — SVG canvas + dotted grid

File: `ui/src/app/graph/GraphCanvas.tsx`

- Full-size `<svg>` filling the center pane.
- Background `<rect>` in `--background`.
- Dotted grid as a tiled `<pattern>`:
  - 24×24 px tile, single `<circle r="0.5">` centered, `--graph-grid-dot`.
  - Grid element `<rect width="100%" height="100%" fill="url(#grid)">`.
  - Pattern's `patternTransform` is updated on every camera change so
    grid pans with the canvas.
  - Clamp rendered dot size to [0.75 px, 1.5 px] as zoom changes (scale
    `r` proportionally).
- **Layering** (bottom to top):
  1. Dot grid rect.
  2. `<g class="edges">` — `RelationConnector`s.
  3. `<g class="nodes">` — `<foreignObject>` NodeCards.
- Coordinate system: uses a `camera` transform (translate + scale)
  applied to a single wrapper `<g>`. All node positions are in
  graph-space; the camera transform maps to screen-space.

### 4.4 — Pan & zoom controls

In `GraphCanvas.tsx`:
- **Mouse wheel**: update `camera.k` (clamped `[0.4, 2.5]`), anchor to
  cursor position.
- **Click + drag empty canvas**: update `camera.x`, `camera.y`.
  Cursor `grab` → `grabbing`.
- **Pinch (touch)**: same as wheel.
- **Drag node**: sets `fx, fy` in the force sim for that node.
  Renders `Pin` indicator on the node.

File: `ui/src/app/graph/ZoomControls.tsx`

Bottom-left vertical stack of three 36 px square buttons
(`Plus`, `Minus`, `Maximize2`). `--surface`, `--border`,
`--node-shadow`, 8 px radius, 16 px from canvas edges.
`Maximize2` = fit-to-content: runs a 600 ms `ease-in-out` camera
interpolation to bring all nodes into view with 80 px padding.

### 4.5 — Force simulation

File: `ui/src/app/graph/useForceSimulation.ts`

Custom hook:
- Creates `d3-force` simulation with exact parameters from
  `03_graph_traversal_page.md §3.3`:
  - `forceLink` distance 180, strength 0.6.
  - `forceManyBody` strength −1200.
  - `forceCenter` at canvas center.
  - `forceCollide` radius = `nodeCardHalfDiag + 12`.
- Runs a `requestAnimationFrame` loop that updates raw SVG attributes
  on node `<foreignObject>` elements and edge `<path>` elements
  **without** triggering React re-renders.
- Stops simulation when `alpha < 0.001` (idle for > 5 s) to prevent
  CPU drift.
- Re-seeds at `alpha = 0.3` on every `expandFromNode` call.
- Exposes `{ restart(nodes, edges) }`.

### 4.6 — `CategoryFilterList`

File: `ui/src/components/CategoryFilterList.tsx`

Per `03_graph_traversal_page.md §2` and `05_components.md §4`:
- Title row: `विषय` h2 600 + `(CATEGORIES)` text-xs muted uppercase.
- 4 rows, 12 px vertical gap each:
  `[14×14 px swatch]  Hindi label  (English)  [Switch 28×16]`.
  Swatch: `--cat-*` bg, 14×14 px, `border-radius: var(--radius-sm)`.
  Switch default ON.
- Horizontal `Separator` after the rows.
- Layout section: 3 radio options (`Force` / `Radial` / `Hierarchical`).
  Only Force is functional in v1; others are disabled placeholders.
- Depth stepper: integer 1–4, default 2. `+` / `−` buttons.
- Bottom: "Reset graph" link `text-sm --accent` 500.
- Wrap in `<fieldset><legend>विषय</legend>` for accessibility.

### Checkpoint 4

Visit `/graph`. The dotted grid fills the canvas. Pan with drag;
zoom with wheel. A handful of hard-coded `NodeCard` elements render
in correct visual styles (all four entity kinds, selected state,
faded state). `RelationConnector` draws Bézier curves with pill
labels. `CategoryFilterList` renders in the left pane. Zoom controls
work. Force sim runs and settles.

---

## Phase 5 — Graph Page: State, Interactivity & Details Panel

**Goal**: the graph page is fully interactive. Clicking nodes fetches
and expands data. The details panel opens. URL syncs.

### 5.1 — `useGraphState` Zustand store

File: `ui/src/lib/store/graphStore.ts`

State shape exactly from `06_interaction_and_state.md §2`:
```ts
type GraphState = {
  nodes: Record<string, GraphNode>;
  edges: Record<string, GraphEdge>;
  pinned: Set<string>;
  selected: { kind: 'node'; id: string } | { kind: 'edge'; id: string } | null;
  categoryVisibility: Record<EntityKind, boolean>;
  depth: 1 | 2 | 3 | 4;
  layout: 'force' | 'radial' | 'hierarchical';
  camera: { x: number; y: number; k: number };
};
```

Reducer-style actions: `selectNode`, `selectEdge`, `clearSelection`,
`togglePin`, `expandFromNode(nk, depth)`, `setCategoryVisibility`,
`setDepth`, `setLayout`, `setCamera`, `reset`.

`expandFromNode` calls `navigation.expandNode(nk, depth)` and merges
the response: de-dupe by `nk` / `id`; seed new node positions at the
focus node's current position so they "burst out".

### 5.2 — URL ↔ store sync

In `ui/src/app/graph/page.tsx`:
- On mount: read `?node`, `?edge`, `?depth`, `?cat` params; initialise
  store accordingly. `?node` → call `expandFromNode`.
- Subscribe to store changes; debounce 500 ms; write `pushState` back
  to URL for `node`, `edge`, `depth`, `cat` (CSV of hidden kinds).
  (See `06_interaction_and_state.md §3`.)

### 5.3 — Interaction handlers

Wire in `GraphCanvas.tsx`:
- **Click node**: `selectNode(nk)`; if not yet expanded →
  `expandFromNode(nk, depth)`.
- **Double-click node**: `focusNode(nk)` — collapse graph to this node
  + 1-hop neighborhood; fade others then remove from sim.
- **Click edge pill**: `selectEdge(id)`.
- **Click empty canvas**: `clearSelection()`.
- **Drag node**: `togglePin(nk)` after drag end; freeze `fx, fy`.
- **Click pin dot**: `togglePin(nk)` to unpin; clear `fx, fy`.
- **Category toggle off**: set `opacity: 0` + `pointer-events: none`
  on matching nodes+edges. Layout does NOT re-simulate.

Keyboard handlers at page root (ignored when `input`/`textarea`/
`contenteditable` is focused):

| Key | Action |
|-----|--------|
| `Esc` | `clearSelection()` |
| `f` | Fit to content |
| `+` / `−` | Zoom |
| `0` | Reset zoom 1× |
| `/` or `Cmd+K` | Focus global search |
| `←` / `→` | Move selection to geometrically nearest adjacent node |
| `Space + drag` | Pan |

(See `06_interaction_and_state.md §5`.)

### 5.4 — `DetailsPanel`

File: `ui/src/components/DetailsPanel.tsx`

Per `03_graph_traversal_page.md §7` and `05_components.md §9`.

**Shell**: slides in from right 200 ms `ease-out`, slides out 160 ms
`ease-in`. On `< 1100 px`: renders as a `Sheet` (bottom, 75 vh).
Top bar: sticky, 1 px `--border` bottom, `BadgeChip` + meta caption
(date, 6 px `--accent` dot) + `X` close button.

**Node mode** (`DetailsPanelMode.mode === 'node'`):
1. Title block: `text-h1` 600 Hindi + `text-sm` muted subtitle.
2. `StatTileRow` — tile content by node type per the table in
   `03_graph_traversal_page.md §7.1`.
3. `विवरण` section: `text-h2` heading + body in `font-serif-hindi`.
4. `संबंधित` section: heading + count pill + up to 5 `ConnectedItemRow`s
   + "View All Connections →" link.
   Clicking a row → `selectNode(rowNk)` + pan camera to that node.
   "View All Connections →" → `expandFromNode(selectedNk, depth + 1)`.
5. `PrimaryCTA` pinned to panel bottom (not in scroll).
   `href` = canonical detail URL for the entity.

Details data fetch: when `selected.kind === 'node'` changes, call
`data.getEntityDetail(kind, nk)` to fill description, stats, and
connected list.

**Relation mode** (`DetailsPanelMode.mode === 'edge'`):
1. Badge shows relation pill on `--accent-soft`.
2. Title: source → target with inline `ArrowRight`.
3. Subtitle: edge kind in English.
4. Body: static description of this edge kind (small `edgeDescriptions`
   dictionary in the component, keyed by `EdgeKind`).
5. Two `ConnectedItemRow`s: source node and target node.
6. No stat tiles, no CTA.
(See `03_graph_traversal_page.md §7.2`.)

### 5.5 — Initial graph seed

In `ui/src/app/graph/page.tsx`:
- If no `?node` in URL: call `navigation.getNavLanding()`.
- Seed the store with the response; center layout; run sim 1.5 s;
  camera fit-to-content with 80 px padding.
  (See `03_graph_traversal_page.md §6`.)

### 5.6 — Performance guard

In `useGraphState`: if node count would exceed 300 after an expand,
show a confirmation dialog — "यह X और नोड्स लोड करेगा — जारी रखें?"
Do not render beyond 300 without confirmation.
(See `03_graph_traversal_page.md §9`.)

### 5.7 — Loading, empty, error states on graph

Per `06_interaction_and_state.md §6`:
- **First paint**: dotted grid immediately; nodes fade in 150 ms once
  data arrives.
- **Expand loading**: existing nodes stay; new nodes fade in 200 ms
  (staggered 30 ms per node).
- **Expand error**: shake the clicked node 300 ms + toast top-right
  8 s (`role="alert"`).
- **Empty DB**: centered card on canvas ("अभी कोई डेटा नहीं है /
  No graph data yet").
- **API error**: toast; previous graph stays interactive.

### 5.8 — SR-only linear navigation tree

Per `08_accessibility_and_i18n.md §8`.

Add inside the graph page:
```html
<nav class="sr-only" aria-label="ग्राफ लीनियर दृश्य">
  <ul>…</ul>
</nav>
```
Mirrors the current store's visible nodes as a nested `<ul>/<li>` tree.
Each node is an `<a href="/[entity]/[nk]">`. Subscribes to store;
updates as graph changes.

### Checkpoint 5

Full interactive graph: landing seed loads, nodes render as cards,
edges as Bézier connectors. Clicking a node expands, details panel
slides in, stat tiles and connected rows render, "Read More" CTA
navigates. Category toggles fade nodes. URL syncs. Keyboard shortcuts
work. Accessibility tree renders in DOM (verify with screen reader or
DevTools accessibility panel).

---

## Phase 6 — Content Pages: List & Index Views

**Goal**: all list and index routes render with correct data fetching
and layout. No detail views yet.

### 6.1 — Home (`/`)

File: `ui/src/app/(content)/page.tsx`

Per `04_content_pages.md §1` and `07_api_integration.md §2`.

Server component (ISR 60 s). Fetches:
- `data.getStatsCounts()` for entity counts.
- `data.getActivityRecent()` for last 10 ingestion runs.

Layout:
- Hero: `text-display` Hindi + `text-h2` English subtitle.
- Duplicate of the global search bar + `विषय खोज` outline button.
- 4 entry-cards in responsive grid (4/2/1 cols). Each 200 px tall,
  white surface, `--radius-md`, `--node-shadow`. Entity icon, Hindi
  title, English subtitle, Devanagari entity count. Arrow on hover.
- `जारी प्रवृत्ति` section: `--surface` card with table of last 10
  ingestion runs (timestamp, source, entities touched).

### 6.2 — Shastras list (`/shastras`)

File: `ui/src/app/(content)/shastras/page.tsx`

Per `04_content_pages.md §2`. ISR 60 s.

- Sticky filter row: multi-select `अनुयोग` chips, author dropdown,
  sort menu, search-within. Active chips use `--accent-soft`.
- Card grid 3/2/1 cols. Each `ShastraCard`: Hindi title h3, author
  muted sm, anuyoga pills, Devanagari gatha count, `खोलें →` button.
- `Pagination` at bottom, Hindi labels from `hi.json`.

### 6.3 — Dictionary letters index (`/dictionary`)

File: `ui/src/app/(content)/dictionary/page.tsx`

Per `04_content_pages.md §5`. ISR 60 s. Fetches:
- `data.getKeywordsLetters()` for the letter grid.
- `data.getKeywordsRecent()` for the side panel.

Layout:
- Letter grid: Devanagari letters in an 8-col grid (4 on mobile).
  Each cell 96×96 px, white surface, `--radius-md`, hover `--accent-soft`.
  Letter at `text-display` 600 centered. Small Devanagari count below.
- Right panel (≥ xl): "हाल ही में जोड़े गए शब्द" — 10 `KeywordRow`s.
  Below mobile: same list stacked.

### 6.4 — Dictionary letter listing (`/dictionary/letters/[letter]`)

File: `ui/src/app/(content)/dictionary/letters/[letter]/page.tsx`

Per `04_content_pages.md §6`. ISR 60 s.

- Big letter h1, count caption, search-within, alphabetical jumper.
- `KeywordRow` list: Hindi name + transliteration + topic chips +
  `ChevronRight`. 12 px gap, hover bg.
- `Pagination`.

### 6.5 — Topics browser (`/topics`)

File: `ui/src/app/(content)/topics/page.tsx`

Per `04_content_pages.md §8`. ISR 60 s.

- Filter row: source segmented control, parent keyword autocomplete,
  search.
- Card grid 3/2/1 cols. Each `TopicCard`: heading, parent keyword
  chip, Devanagari mention count, `विषय खोलें →`.

### 6.6 — Search (`/search`)

File: `ui/src/app/(content)/search/page.tsx`

Per `04_content_pages.md §10`. Dynamic (`revalidate=0`). Calls:
`query.searchTopics({ q, caller: "public-ui" })`.

Layout:
- Big centered pill search input 56 px, auto-focused, `खोजें` in
  `--accent`.
- Result cards numbered. Per card: Hindi title, matched tokens
  highlighted in `--accent-soft`, overlap pill, score caption,
  excerpt, mention chips. `विषय खोलें →` and `ग्राफ में खोलें →` CTAs.
- Loading state: `Loader2` 16 px inside the search button.
- Empty: `कोई परिणाम नहीं मिला` centered.
- Error: inline `--danger` block under the search.

### Checkpoint 6

All six routes load with real data. Pagination works. Filters narrow
the list. Search returns ranked results with highlighted tokens.
Responsive layouts verified at 375 px, 768 px, 1280 px, 1440 px.

---

## Phase 7 — Content Pages: Detail Views

**Goal**: all detail routes render using Shell B or C, with the rich
content panels, reader columns, and popovers.

### 7.1 — `GathaPanel` component

File: `ui/src/components/GathaPanel.tsx`

Per `05_components.md §11`:
- Props: `{ lang: 'prakrit' | 'sanskrit' | 'hindi-harigeet'; text; accent? }`.
- White card with preserved line breaks.
- `font-serif-hindi`, `text-h2`, line-height 1.7.
- Left border 3 px:
  - `lang: 'prakrit'` → `--cat-shastra` at 40%.
  - `lang: 'hindi-harigeet'` → `--accent` at 40%.
  - `lang: 'sanskrit'` → no border.

### 7.2 — `TaggedTermPopover` component

File: `ui/src/components/TaggedTermPopover.tsx`

Per `05_components.md §12`:
- Renders a `<span>` with `--accent` underline.
- On click: shadcn `Popover` 320 px wide containing meaning blocks.
  If `topicNk` present: show `विषय खोलें →` link to `/topics/[topicNk]`.
- `aria-haspopup="dialog"` on trigger; popover `role="dialog"
  aria-modal="false"`.

### 7.3 — `MiniGraphPreview` component

File: `ui/src/components/MiniGraphPreview.tsx`

Per `05_components.md §15`. Server component.
- Calls `nav:/v1/preview/{nk}?hops=1` server-side.
- Renders a static non-interactive SVG of the 1-hop neighborhood.
- On hover: thin overlay "ग्राफ में खोलें" links to `/graph?node={nk}`.

### 7.4 — Shastra detail (`/shastras/[nk]`)

File: `ui/src/app/(content)/shastras/[nk]/page.tsx`

Per `04_content_pages.md §3`. ISR 60 s. Shell B. Fetches:
`metadata.getShastra(nk)`, `data.getShastraTeekas(nk)`,
`nav.getPreview(nk, 1)`.

Layout:
- `BreadcrumbBar`.
- Hero card: left (title h1, author linked, anuyoga pills, source
  URL pill) + right (`StatTileRow` for gathas / teekas / pages).
- `Tabs` (underline variant, `--accent`):
  - `विषयानुक्रमणिका`: collapsible adhikaar tree → gatha rows.
  - `टीकाएँ`: table (teekakar, publisher, year, language).
  - `गाथाएँ`: paginated grid of `GathaTile`s.
- Right rail (≥ xl, sticky): "ग्राफ में खोलें" CTA + `MiniGraphPreview`.

### 7.5 — Gatha detail (`/shastras/[nk]/gathas/[number]`)

File: `ui/src/app/(reading)/shastras/[nk]/gathas/[number]/page.tsx`

Per `04_content_pages.md §4`. ISR 60 s. Shell C. Fetches:
`data.getGatha(nk)`, `data.getGathaRelatedTopics(nk)`,
`data.getGathaRelatedKeywords(nk)`.

**Reader column** (top → bottom, each a white card):
1. `BreadcrumbBar`.
2. `GathaPanel lang="prakrit"`.
3. `GathaPanel lang="sanskrit"` (if present).
4. `GathaPanel lang="hindi-harigeet"`.
5. शब्दार्थ panel: each Prakrit token a `TaggedTermPopover`. Hovered
   tokens highlight `--accent-soft`.
6. टीका panel: long Hindi anvayartha; bracketed `[…]` terms rendered
   as `TaggedTermPopover` triggers, `--accent` underlined.

**Sidebar column** (sticky, scroll-isolated):
- `संबंधित विषय` card: topic chips.
- `संबंधित कीवर्ड` card: keyword chips.
- `ग्राफ में खोलें` CTA → `/graph?node=gatha:{nk}`.
- `अन्य टीकाएँ` card: list of other teekas for this gatha.

### 7.6 — Keyword detail (`/dictionary/[nk]`)

File: `ui/src/app/(content)/dictionary/[nk]/page.tsx`

Per `04_content_pages.md §7`. ISR 60 s. Fetches:
`data.getKeyword(nk)`, `nav.getPreview(nk, 1)`.

Layout per the ASCII art spec:
- Title h1, aliases, source + graph CTAs.
- Collapsible `सिद्धांतकोष से` section: subsection headings,
  reference row, triple-panel (Sanskrit / Prakrit / Hindi blocks).
- `संबंधित विषय` card.
- `ग्राफ संबंध` card: `IS_A`, `PART_OF`, `RELATED_TO` rows each
  clickable → `/graph?node={nk}`.

### 7.7 — Topic detail (`/topics/[nk]`)

File: `ui/src/app/(content)/topics/[nk]/page.tsx`

Per `04_content_pages.md §9`. ISR 60 s. Fetches:
`data.getTopic(nk)`, `nav.getTopicNeighbors(nk)`.

Layout:
- Hero card: title h1, parent keyword chip, source pill, mention count.
- `विषय अंश (Extracts)` card: Hindi blocks with accent border.
- `उल्लेख (Mentions)` card: gatha mention rows (link to gatha page)
  and chat-candidate rows (open new tab).
- `ग्राफ पड़ोसी` card: three columns IS_A / PART_OF / RELATED.
- Sticky right rail (≥ xl): `ग्राफ में खोलें` + `MiniGraphPreview`.

### Checkpoint 7

Navigate shastra → gatha. Reader column shows all language panels.
Word-by-word tokens open popovers. Sidebar related topics/keywords
are correct. Keyword detail shows collapsible sections and graph
relation rows. Topic detail shows extracts and neighbor grid.
`MiniGraphPreview` renders a valid static SVG on detail right rails.

---

## Phase 8 — Remaining Pages & Accessibility Polish

**Goal**: about, feedback, and all a11y requirements from
`08_accessibility_and_i18n.md §9` are satisfied.

### 8.1 — About page (`/about`)

File: `ui/src/app/(content)/about/page.tsx`

Per `04_content_pages.md §11`. Static.

- 720 px-wide centered single column.
- Hindi-first mission paragraphs.
- Sources & acknowledgments section: each source a white card with
  name, link, license note.
- Tech-stack section in English (small).

### 8.2 — Feedback page + API route (`/feedback`)

File: `ui/src/app/(content)/feedback/page.tsx`,
`ui/src/app/api/feedback/route.ts`

Per `04_content_pages.md §12`.

Form (640 px wide centered):
- Name, email (validated on blur with regex when present).
- Type radio: "बग रिपोर्ट / सुझाव / सामग्री त्रुटि".
- Message textarea (200 char min, 4000 max). Char counter.
- Route auto-populated from `referrer`.
- Submit `भेजें (Submit)` in `--accent`.

`POST /api/feedback` route handler: writes to MongoDB
`feedback` collection. On success: green inline confirmation card
(NOT a toast). On error: inline `--danger` block.

### 8.3 — ARIA completeness pass

Walk every component against the ARIA table in
`08_accessibility_and_i18n.md §5`. Verify:
- `TopBar`: `<nav aria-label="मुख्य">`.
- `CategoryFilterList`: `<fieldset>/<legend>`.
- `NodeCard`: `role="button" aria-pressed={selected}
  aria-label="<type>: <hindi> (<english>)"`.
- `RelationConnector`: `role="button" aria-label="..."`.
- `DetailsPanel`: `<aside role="complementary" aria-label="विवरण">`.
- `TaggedTermPopover`: `aria-haspopup="dialog"` + popover
  `role="dialog" aria-modal="false"`.
- Toasts: info → `role="status"`, error → `role="alert"`.

### 8.4 — Focus ring everywhere

Audit every focusable element. Ensure none has `outline: none`
without the `--ring` replacement (2 px solid, 30% alpha, 2 px offset).
Verify tab order matches DOM order on each page.

### 8.5 — `prefers-reduced-motion` pass

In `globals.css`:
```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0ms !important;
    transition-duration: 80ms !important;
  }
}
```

In `useForceSimulation`: detect the media query; if active, run the
sim to alpha 0.05 instantly (no progressive animation).
Shimmer skeleton becomes a static `--surface-muted` block.
(See `06_interaction_and_state.md §7` and `08_accessibility_and_i18n.md §7`.)

### 8.6 — Devanagari rendering verification

Check in Chrome latest / Safari latest / Firefox latest on macOS,
Windows, Android:
- No missing-glyph squares on any Devanagari text.
- Font loads without FOUC (swap fallback kicks in if Noto is slow).

### 8.7 — Locale switch end-to-end

Toggle to English in the footer. Verify:
- Chrome labels, button labels, captions translate.
- Devanagari titles (gatha text, shastra names, keyword headings)
  remain in Devanagari.
- Locale persists across navigation (cookie round-trip).

### 8.8 — Lighthouse a11y

Run `pnpm lighthouse` against each route. Target ≥ 95 a11y score on:
`/`, `/graph`, `/shastras`, `/shastras/[nk]`,
`/shastras/[nk]/gathas/[number]`, `/dictionary`, `/dictionary/[nk]`,
`/topics`, `/topics/[nk]`, `/search`, `/about`, `/feedback`.

### 8.9 — Final visual review

Open `ux_template_images/overall_theme_and_panels.png` and
`ux_template_images/navigation_and_graph_look.png` side by side with
the running app. Check:
- Red-on-white palette, generous whitespace, slim borders.
- Graph canvas dotted grid and card nodes match the reference exactly.
- `NodeCard` selected state fills red, text turns white.
- `DetailsPanel` matches the panel in `overall_theme_and_panels.png`.
- Nav-bar active pill shape and colour match.

### Checkpoint 8 (Final)

- Lighthouse a11y ≥ 95 on all routes.
- Tab-only walkthrough of `/graph` completes: node select → details
  panel → "Read More" CTA → detail page.
- Devanagari renders correctly on all three browsers.
- `prefers-reduced-motion` disables force-sim animation.
- Locale switch persists.

---

## Summary table

| Phase | Scope | Key deliverable |
|-------|-------|-----------------|
| 0 | Bootstrap + design tokens | Running Next.js with correct palette, fonts, shimmer |
| 1 | Global shell + navigation | TopBar, 3 page shells, footer, skeletons |
| 2 | Atomic components | BadgeChip, StatTile, ConnectedItemRow, PrimaryCTA, ListCards |
| 3 | API client layer | Typed fetch clients for all 4 services |
| 4 | Graph canvas foundation | NodeCard, RelationConnector, dotted grid, pan/zoom, force sim |
| 5 | Graph interactivity + details | useGraphState, URL sync, DetailsPanel, SR tree |
| 6 | Content list pages | Home, Shastras list, Dictionary index, Topics, Search |
| 7 | Content detail pages | Shastra, Gatha, Keyword, Topic detail; MiniGraphPreview |
| 8 | Remaining pages + a11y | About, Feedback, full ARIA pass, Lighthouse ≥ 95 |
