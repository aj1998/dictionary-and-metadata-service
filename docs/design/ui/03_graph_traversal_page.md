# 03 — Graph Traversal Page (`/graph`)

This is the centerpiece of the website. Two canonical references:

- **Page chrome, palette, panel layouts**:
  `ux_template_images/overall_theme_and_panels.png`
- **Canvas, node visuals, connectors**:
  `ux_template_images/navigation_and_graph_look.png`

If anything in this document conflicts with those images, the images win.

## 1. Layout (Graph shell)

```
┌─ TopBar (global) ─────────────────────────────────────────────────────────┐
├──────────────┬──────────────────────────────────────────────┬─────────────┤
│  LEFT        │              GRAPH CANVAS                    │  RIGHT      │
│  CATEGORIES  │              (dotted grid, pan + zoom)       │  DETAILS    │
│  280 px      │              flex-1, full-bleed              │  380 px     │
│              │                                              │             │
│              │   ┌──────┐                                   │             │
│              │   │ Node │───────────╮                       │             │
│              │   └──────┘           ╰──┌──────┐             │             │
│              │                         │ Node │             │             │
│              │   ┌──────┐──────────────└──────┘             │             │
│              │   │ Node │             ╭                     │             │
│              │   └──────┘─────────────╯                     │             │
│              │                                              │             │
│              │  [+]  [−]  [⛶]                              │             │
└──────────────┴──────────────────────────────────────────────┴─────────────┘
```

Canvas fills 100% of the center pane height (viewport minus 64 px nav
bar). No internal margin around the canvas — the dotted grid runs edge
to edge. The center pane's outer borders are 1 px `--border` against
the adjacent panes; no border between the canvas and the nav bar (the
nav bar's own bottom border separates them).

## 2. Left pane — Categories filter

Title row at 16 px inset: `विषय` (h2 600) + `(CATEGORIES)` in
`text-xs` `--foreground-muted` uppercase with 0.04em letter spacing,
inline.

Below the title, a vertical stack of 4 rows (one per entity type), 12 px
vertical gap, each row:

```
[■]  शास्त्र   (Shastra)                       [— ●]
```

- Left swatch: 14×14 px rounded-sm fill of the `--cat-*` color.
- Hindi label: `text-body` 500.
- English label in parentheses: `text-sm` `--foreground-muted` 400.
- Right toggle: shadcn `Switch` (28×16), default ON. Toggling OFF hides
  every node of that type plus every edge incident to such a node. The
  layout does not re-simulate — hidden nodes stay positioned, just fade
  to `opacity 0` and become non-interactive.

Below the four rows, a horizontal `Separator`, then a **"Layout"**
section with three radio options (only one is needed v1; the others
are placeholders the spec calls out so we don't redesign later):

- `बल / Force` (default)
- `रेडियल / Radial` (center = currently selected node)
- `पदानुक्रम / Hierarchical` (top→down by edge kind)

Below that, a **"Depth"** stepper (1–4, default 2): how many hops to
expand on node-click. Each click on a node fetches +N hops around it.

Bottom of the left pane: a faint "Reset graph" link (`text-sm`
`--accent` 500) that clears the canvas and reseeds it with the
default landing set (see §6).

## 3. Center pane — Canvas

### 3.1 Background

- Fill: `--background`.
- Dotted grid: 1 px circles, `--graph-grid-dot`, 24 px on-center
  spacing. Implement as a tiled SVG pattern, NOT individual elements.
- The grid pans with the camera, scales with zoom (clamp dot size to
  `[0.75 px, 1.5 px]` so it never disappears or fattens).

### 3.2 Pan / zoom / drag

- Pan: click-and-drag empty canvas. Cursor `grab` → `grabbing`.
- Zoom: mouse wheel + pinch. Range `0.4×–2.5×`. Anchor zoom to cursor.
- Drag node: click-and-drag a node card → pins it to that position
  (`fx, fy` set in the force simulation). A small pin-dot appears on
  the top-right corner of the card; clicking the pin-dot unpins.
- Bottom-left zoom controls: vertical stack of three 36 px square
  buttons (`Plus`, `Minus`, `Maximize2` = fit-to-content), `--surface`
  with `--border` and `--node-shadow`, 8 px radius. 16 px from canvas
  edges.

### 3.3 Force layout

Use `d3-force` with:

- `forceLink` distance 180 (default), strength 0.6.
- `forceManyBody` strength −1200.
- `forceCenter` at the visible canvas center.
- `forceCollide` radius = `nodeCardHalfDiag + 12`.
- Alpha decays standard; restart at α=0.3 on every node-expand.

Stop the simulation completely after 5 s of inactivity (α < 0.001) to
avoid CPU drift when the tab idles.

## 4. NodeCard (the canonical node visual)

Each node is a **rounded white card**, NOT a circle or square dot —
this is the key visual borrowed from
`navigation_and_graph_look.png`.

### 4.1 Dimensions

- Width: **220 px** (fixed). Height: **auto**, content-driven, min 64 px.
- Radius: `--radius-md` (10 px).
- Background: `--node-bg`. Border: 1 px `--node-border`.
- Shadow: `--node-shadow` (resting), `--node-shadow-hover` (hover).
- A 4 px **top stripe** (full width, top corners only rounded) tinted in
  the entity's `--cat-*` color. The stripe is the only place the
  category color appears on the card; everything else is neutral.

### 4.2 Structure

```
┌────────────────────────────┐   <- 4 px cat-stripe on top edge
│ [icon]  शास्त्र            │   <- header row, 12 px padding
│         Shastra            │
├────────────────────────────┤   <- 1 px --border separator
│ तत्त्वार्थसूत्र              │   <- title row
│ Tattvartha Sutra            │
└────────────────────────────┘
```

- **Header row** (height 40 px, padding 12 px H / 10 px V):
  - 24×24 rounded-sm box `--surface-muted` containing the entity's
    lucide icon at 16 px, `--foreground-muted`.
  - Next to it, 2-line stack: Hindi type label (`text-sm` 600), English
    type label (`text-xs` `--foreground-muted`).
  - Top-right: a small `Play`-like chevron `ChevronRight` 16 px,
    `--foreground-subtle`, hinting "expand". (Matches the small
    triangle on every card in `navigation_and_graph_look.png`.)
- **Separator**: full-width 1 px `--border`.
- **Body row** (padding 12 px H / 10 px V):
  - Hindi name in `font-serif-hindi` `text-h3` 600,
    line-clamp-2.
  - English transliteration in `text-xs` `--foreground-muted`, single
    line, truncated. Hidden if absent.

### 4.3 States

| State | Visual |
|---|---|
| Resting | as above |
| Hover | shadow → `--node-shadow-hover`, border → `--accent` at 40% alpha |
| Selected (clicked) | fill → `--accent`; **all text on card becomes white**; cat-stripe hidden (merged into solid fill); border `--accent`; shadow stays at hover level |
| Faded (category off, or graph search filter no-match) | opacity 0.25, no pointer events |
| Pinned (user dragged) | small `Pin` icon 12 px top-right, opposite the chevron |

The selected red fill exactly matches the central "Tattvartha Sutra"
node in `overall_theme_and_panels.png`.

### 4.4 Anchor points for edges

Edge endpoints attach to the **center of the nearest card side** (top /
right / bottom / left), chosen by minimal-distance from the other end.
Use SVG `path` with a cubic Bézier — control points offset 80 px from
each anchor along the card's outward normal. This produces the smooth
S-curves shown in `navigation_and_graph_look.png`.

## 5. Edges (RelationConnector)

- Stroke: `--graph-edge`, 1.5 px, `stroke-linecap: round`.
- Drawn as an SVG `<path>` below the node `<foreignObject>` elements,
  but above the dot grid.
- Each endpoint terminates in a 6 px filled `--graph-edge` circle
  (matches the small dots at each connector's end in
  `navigation_and_graph_look.png`).
- A relation label sits at the midpoint of the curve, on a pill
  background:
  - Pill: `--surface`, 1 px `--border`, `--radius-pill`, padding
    6 px H / 2 px V.
  - Text: `text-xs` 500, color `--foreground-muted`, Hindi label of
    the relation (e.g., `संबंधित`, `गाथा का भाग`, `विषय`).
  - The pill rotates with the path tangent **only between −20° and
    +20°**; beyond that, render flat (rotation 0) to keep labels
    readable.
- States: inactive → stroke `--graph-edge-muted`, label pill 50%
  opacity. Active (incident to a hovered or selected node) → stroke
  `--accent`, label pill border `--accent`.
- Click on edge → opens the details panel in **relation mode** (see §7.2).

### Edge kinds & labels

Sourced from the Neo4j schema in `../04_data_model_graph.md`. Label
each edge in Hindi with English subtitle on hover-tooltip:

| Cypher type | Pill label (Hindi) | Tooltip (English) |
|---|---|---|
| `HAS_TOPIC` | विषय | Has topic |
| `MENTIONS_KEYWORD` | कीवर्ड | Mentions keyword |
| `MENTIONS_TOPIC` | विषय उल्लेख | Mentions topic |
| `IS_A` | है का प्रकार | Is a |
| `PART_OF` | भाग | Part of |
| `RELATED_TO` | संबंधित | Related to |
| `ALIAS_OF` | पर्याय | Alias of |
| `IN_SHASTRA` | शास्त्र में | In shastra |
| `IN_TEEKA` | टीका में | In teeka |
| `IN_PUBLICATION` | प्रकाशन | In publication |
| `CONTAINS_DEFINITION` | परिभाषा | Contains definition |

## 6. Initial graph seed

When the user lands on `/graph` with no query string:

1. Call `GET /v1/navigation/landing` (navigation-service). Spec for this
   endpoint already exists; if a default seed isn't yet defined, use
   the 5 most-connected Topic nodes plus their 1-hop neighbors.
2. Center the layout, run the force sim for 1.5 s, then ease the
   camera to fit-to-content with 80 px padding.

Deep links:

- `/graph?node=<nk>` — pre-select the node with that natural key, fetch
  its 2-hop neighborhood, and open the details panel.
- `/graph?relation=<id>` — pre-select that edge.

URL state is kept in sync as the user expands / collapses (debounced
500 ms).

## 7. Right pane — Details

Slides in from the right edge of the viewport whenever a node or an
edge is selected. Match `overall_theme_and_panels.png` precisely.

### 7.1 Node mode

```
┌──────────────────────────────────────────────┐
│ [विषय / Topic]                      • 14 May │   <- entity badge + meta
│                                              │
│ तत्त्वार्थसूत्र                                │   <- big Hindi title
│ आचार्य उमास्वामी                              │   <- subtitle (author/source)
│                                              │
│ ┌──────┐ ┌──────┐ ┌──────┐                  │
│ │  १०  │ │ ३५७  │ │   २  │                  │   <- 3-up stat tiles
│ │संबंध │ │उल्लेख│ │टीकाएँ│                   │
│ └──────┘ └──────┘ └──────┘                  │
│                                              │
│ विवरण                                        │   <- section: description
│ तत्त्वार्थसूत्र जैन दर्शन का प्रमुख ग्रंथ है …  │
│                                              │
│ संबंधित विषय (Connected)         32 Nodes   │   <- section: connections
│ ┌──────────────────────────────────────┐    │
│ │  शास्त्र  आचारंगसूत्र            ›    │    │
│ │           Acharanga Sutra            │    │
│ └──────────────────────────────────────┘    │
│ ┌──────────────────────────────────────┐    │
│ │  शास्त्र  समयसार                 ›    │    │
│ │           Samayasara                 │    │
│ └──────────────────────────────────────┘    │
│ View All Connections →                       │
│                                              │
├──────────────────────────────────────────────┤
│ ╭──────────────────────────────────────────╮ │
│ │ विस्तार से पढ़ें (Read More)        🔖   │ │   <- primary CTA
│ ╰──────────────────────────────────────────╯ │
└──────────────────────────────────────────────┘
```

**Top bar** (sticky inside the panel, 1 px `--border` bottom):

- Entity badge (`BadgeChip` in `--cat-*` color).
- Right: meta caption — last-updated date in `text-xs`
  `--foreground-muted`, with a leading 6 px filled dot in `--accent`.
- Top-right `X` close button (also unselects the node in graph).

**Title block**: title `text-h1` 600, subtitle `text-sm`
`--foreground-muted` directly under.

**Stat tiles**: see `01_design_system.md` §7. Always exactly 3:
node-type dictates which:

| Node type | Tile 1 | Tile 2 | Tile 3 |
|---|---|---|---|
| Shastra | गाथाएँ (gathas) | टीकाएँ (teekas) | संबंध (degree) |
| Gatha | टीकाएँ | विषय | कीवर्ड |
| Topic | संबंध | उल्लेख | टीकाएँ |
| Keyword | परिभाषाएँ | विषय | संबंध |

Devanagari numerals.

**विवरण (Description)**: section heading `text-h2`, body `text-body`
`font-serif-hindi`. For Keyword/Topic nodes, render the first
definition; for Shastra/Gatha, render the author's bio / gatha's
hindi-chhand snippet (3 lines max with `…` truncation).

**संबंधित (Connected)**: section heading + small counter pill on the
right showing total connections. Below: up to **5** `ConnectedItemRow`
cards (see `05_components.md`), then a `View All Connections →` link
that, when clicked, expands the graph by N more hops AND scrolls this
list to full length.

Each `ConnectedItemRow`:

- 1 px `--border`, `--radius-md`, 12 px padding, 12 px vertical gap.
- Left: entity badge (`--cat-*` color, small variant 18 px tall).
- Center: title (Hindi 500) over transliteration (`text-xs` muted).
- Right: `ChevronRight` 18 px `--foreground-subtle`. Hover → row bg
  `--surface-muted`, chevron `--accent`.
- Clicking the row pans the graph to that node and re-opens the
  details panel for it (graph stays the source of truth).

**Primary CTA** (fixed to the bottom of the panel, never scrolls):
red `Read More` button as specified in `01_design_system.md` §8. It
deep-links to the canonical detail page for the entity
(`/dictionary/[nk]`, `/topics/[nk]`, `/shastras/[nk]`, or
`/shastras/[nk]/gathas/[number]`).

### 7.2 Relation mode (edge clicked)

Same panel shell, but content swaps to:

- Badge text becomes the relation pill (e.g. "संबंधित / Related to") on
  `--accent-soft`.
- Title: source node Hindi name → target node Hindi name (with an
  inline `ArrowRight` between them).
- Subtitle: relation kind in English.
- Body section: brief explanation of what this edge kind means (pulled
  from a small static dictionary; same content as the tooltips on the
  edge labels).
- Two `ConnectedItemRow`s: source node, target node. Clicking either
  refocuses the panel on that node.
- No stat tiles, no CTA. (Or: a single secondary CTA "इस संबंध को
  देखें / Open both in graph" that re-fits the camera to just those
  two nodes.)

## 8. Interaction summary

| Trigger | Effect |
|---|---|
| Click node | Select node → open details panel. Fetch +D hops (D = current depth). Animate new nodes in from selected node's position. |
| Double-click node | "Focus" — collapse the graph to only this node + its 1-hop neighborhood. Other nodes fade and are removed from sim. |
| Click edge | Select edge → open relation-mode panel. |
| Click empty canvas | Deselect; close details panel. |
| Drag node | Pin node. |
| Click pin-dot | Unpin. |
| Wheel / pinch | Zoom (clamped). |
| Space + drag, or two-finger drag | Pan. |
| `Esc` | Deselect / close panel. |
| `/` or `Cmd+K` | Focus the top-bar global search. |
| `f` | Fit-to-content (same as `Maximize2`). |
| Category toggle off | Fade out matching nodes + edges. |

## 9. Performance budget

- Cap rendered nodes at **300**. Beyond that, an "expanding will load X
  more — continue?" confirmation appears (avoid layout meltdown).
- Use `<foreignObject>` SVG hosting React node cards so we get the dotted
  grid and edges in SVG without paying for per-node React+DOM re-layout
  during the force sim. Re-render node cards only when their data or
  state changes; transform updates happen on raw SVG attributes via a
  `requestAnimationFrame` loop.
- Lazy-load `d3-force` from the client bundle only on this route.

## 10. Empty / error states

- **No data** (cold DB): show a centered card on the canvas — "अभी कोई
  डेटा नहीं है / No graph data yet" with a link to the admin docs.
- **API error**: a toast (top-right, 8 s) — "नेटवर्क त्रुटि / Network
  error". The previous graph stays interactive.
- **Loading on first paint**: dotted grid renders immediately; nodes
  fade in over 150 ms once data arrives. No spinner overlay.
