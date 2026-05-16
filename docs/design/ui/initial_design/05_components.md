# 05 — Reusable Components

Every component below lives under `ui/components/`. Names are normative —
implementations may not rename without updating this spec. Every component
accepts a `className` override (concatenated last via `clsx`) and forwards
refs.

Shadcn primitives (`Button`, `Card`, `Switch`, `Tabs`, `Tooltip`,
`Pagination`, `Sheet`, `Popover`, `Separator`, `Badge`) come from the
existing `ui_template/src/app/components/ui/*` scaffold and should NOT be
re-implemented. Wrap them when project styling requires it.

## 1. `TopBar`

Global nav. See `02_layout_and_navigation.md` §1.

Props: `{ activeRoute: string; locale: 'hi' | 'en' }`. The brand and
search are stateless; nav-item active state is derived from
`activeRoute` (passed via the App-Router layout).

## 2. `NodeCard`

The canonical graph node visual. See `03_graph_traversal_page.md` §4.

```ts
type EntityKind = 'shastra' | 'gatha' | 'topic' | 'keyword';

interface NodeCardProps {
  id: string;                  // natural key
  kind: EntityKind;
  titleHi: string;
  titleEn?: string;
  selected?: boolean;
  pinned?: boolean;
  faded?: boolean;
  onClick?(): void;
  onDoubleClick?(): void;
  onPinToggle?(): void;
}
```

Reused both inside the graph (positioned in SVG `foreignObject`) and as a
static preview in shastra/topic detail right-rails (no positioning).

## 3. `RelationConnector`

SVG path + label pill for an edge. Pure SVG; no DOM.

```ts
interface RelationConnectorProps {
  from: { x: number; y: number; side: 'top' | 'right' | 'bottom' | 'left' };
  to:   { x: number; y: number; side: 'top' | 'right' | 'bottom' | 'left' };
  kind: EdgeKind;
  active?: boolean;
  onClick?(): void;
}
```

Renders:
1. Cubic Bézier path.
2. Two 6 px endpoint dots.
3. A `<foreignObject>` at the midpoint holding the pill label.

## 4. `CategoryFilterList`

Left pane filter list (graph page).

```ts
interface CategoryFilterListProps {
  visibility: Record<EntityKind, boolean>;
  onToggle(kind: EntityKind): void;
}
```

Renders 4 swatch + label + Switch rows. Header `विषय (CATEGORIES)`.

## 5. `BadgeChip`

Entity-type pill.

```ts
interface BadgeChipProps {
  kind: EntityKind;
  size?: 'sm' | 'md';                 // 18px / 22px tall
  labelHi?: string;                   // override; defaults to type label
  labelEn?: string;
}
```

Defaults map: `shastra → शास्त्र / Shastra`, etc. Background is
`--cat-<kind>`, text white. Pill radius.

## 6. `StatTile`

```ts
interface StatTileProps {
  count: number;          // rendered in Devanagari numerals
  label: string;          // Hindi caption
}
```

White surface card, `--radius-md`, padding 16. Big number `text-h1` 600,
small label `text-xs` muted uppercase. Used 3-up in details panel.

## 7. `StatTileRow`

Convenience wrapper rendering 3 tiles in a 12-px-gap flex row.

## 8. `ConnectedItemRow`

Used in the right details panel and across detail pages wherever a row of
"related entity" appears.

```ts
interface ConnectedItemRowProps {
  kind: EntityKind;
  titleHi: string;
  titleEn?: string;
  href?: string;          // when present, row becomes a link
  onClick?(): void;       // when graph mode (no nav)
}
```

Layout: badge + name stack + `ChevronRight`. Hover row bg
`--surface-muted`, chevron `--accent`.

## 9. `DetailsPanel`

The right pane on the graph page. Composes the above building blocks.

```ts
type DetailsPanelMode =
  | { mode: 'node'; node: GraphNodeDetail }
  | { mode: 'edge'; edge: GraphEdgeDetail }
  | null;

interface DetailsPanelProps {
  state: DetailsPanelMode;
  onClose(): void;
  onSelectNode(nk: string): void;
  onOpenReadMore(href: string): void;
}
```

Inner sections (top to bottom): `BadgeRow`, `TitleBlock`, `StatTileRow`,
`Section "विवरण"`, `Section "संबंधित"` with `ConnectedItemRow` list and
"View All Connections →" link, `PrimaryCTA` pinned to bottom.

## 10. `PrimaryCTA`

The red bottom button. See `01_design_system.md` §8.

```ts
interface PrimaryCTAProps {
  labelHi: string;        // "विस्तार से पढ़ें"
  labelEn?: string;       // "Read More"
  icon?: LucideIcon;      // default Bookmark
  href?: string;
  onClick?(): void;
}
```

## 11. `GathaPanel`

A single language panel inside the gatha detail reader column.

```ts
interface GathaPanelProps {
  lang: 'prakrit' | 'sanskrit' | 'hindi-harigeet';
  text: string;
  accent?: 'shastra' | 'accent' | 'none';   // controls left border color
}
```

## 12. `TaggedTermPopover`

Inline clickable Devanagari term (used in word-by-word and teeka prose).

```ts
interface TaggedTermPopoverProps {
  termHi: string;
  meaningHi?: string;
  meaningEn?: string;
  topicNk?: string;       // if present, "विषय खोलें →" link inside popover
}
```

Renders a span with `--accent` underline; on click, opens a 320 px wide
shadcn `Popover` containing meaning blocks and an optional topic link.

## 13. `BreadcrumbBar`

Re-used on every content page. Hindi-first segments separated by `›`.
Last segment is unlinked and bold. Long titles truncate with ellipsis
beyond 32 chars.

## 14. `KeywordCard` / `TopicCard` / `GathaTile`

Mid-density cards for list grids.

```ts
interface ListCardProps {
  kind: EntityKind;
  titleHi: string;
  titleEn?: string;
  meta?: string;          // e.g. parent keyword, mention count
  count?: number;         // big Devanagari numeral
  href: string;
}
```

White surface, `--radius-md`, hover lift to `--node-shadow-hover`.

## 15. `MiniGraphPreview`

Server-rendered SVG showing 1-hop neighborhood. Used on detail pages'
right rail. Non-interactive (a thin "ग्राफ में खोलें" overlay on hover).

## 16. `LocaleSwitch`

A small toggle in the footer: `हिन्दी / English`. Persists choice in a
cookie consumed by `next-intl` on the next request.

## 17. Shimmer / skeleton primitives

`Skeleton.Card`, `Skeleton.Row`, `Skeleton.Title` — all consume the
same shimmer keyframes. Standard fill `--surface-muted`. No spinners
anywhere in the public app.

## 18. State containers (not components, but normative)

- `useGraphState()` — Zustand store keyed by route, holding
  `nodes`, `edges`, `selected`, `pinned`, `categoryVisibility`,
  `depth`, `layout`. Survives navigation within the graph page; resets
  on leaving `/graph`.
- `useLocale()` — wrapped `next-intl` hook.
- All other pages are server components; no client store.
