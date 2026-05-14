# 06 — Interaction & State

## 1. Global state philosophy

The public site is overwhelmingly server-rendered. **The only page with
non-trivial client state is `/graph`.** Everything else uses URL params
+ server-fetched data + small local `useState`s for popovers and tab
selection.

## 2. Graph page state (`useGraphState`)

```ts
type GraphState = {
  nodes: Record<string, GraphNode>;   // by natural key
  edges: Record<string, GraphEdge>;
  pinned: Set<string>;
  selected:
    | { kind: 'node'; id: string }
    | { kind: 'edge'; id: string }
    | null;
  categoryVisibility: Record<EntityKind, boolean>;  // default all true
  depth: 1 | 2 | 3 | 4;                              // default 2
  layout: 'force' | 'radial' | 'hierarchical';       // default 'force'
  camera: { x: number; y: number; k: number };       // pan + zoom
};
```

Mutations are all reducer-style actions:
`selectNode`, `selectEdge`, `clearSelection`, `togglePin`,
`expandFromNode(nk, depth)`, `setCategoryVisibility`, `setDepth`,
`setLayout`, `setCamera`, `reset`.

## 3. URL state ↔ store sync

The URL is the user-shareable view. The store is the working canvas.

| URL key | Store field |
|---|---|
| `node=<nk>` | `selected = { kind: 'node', id: nk }` and auto-expand |
| `edge=<id>` | `selected = { kind: 'edge', id }` |
| `depth=2` | `depth` |
| `cat=topic,keyword` (CSV of hidden kinds) | `categoryVisibility` |

A debounced `pushState` (500 ms) writes back to the URL whenever any of
these fields change. Direct nav (back/forward) re-reads the URL and
resets the store.

## 4. Click rules

| Target | Action |
|---|---|
| Empty canvas | `clearSelection()` + close panel |
| Node card | `selectNode(nk)`; if not already expanded, call `expandFromNode(nk, depth)` |
| Node card (double-click) | `focusNode(nk)` → collapse graph to only this node + neighborhood |
| Edge midpoint pill | `selectEdge(id)` |
| Pin dot | `togglePin(nk)` |
| Connected-item row in panel | `selectNode(rowNk)`; pan camera so node is in viewport |
| `View All Connections` link | call `expandFromNode(selectedNk, depth + 1)` |
| Read More CTA | `router.push(canonicalDetailHref(node))` |

## 5. Keyboard

| Key | Action |
|---|---|
| `Esc` | `clearSelection()` |
| `f` | Fit to content |
| `+` / `−` | Zoom |
| `0` | Reset zoom to 1× |
| `/` or `Cmd+K` | Focus global search |
| `←` / `→` (when panel open) | Move selection to prev/next adjacent node |
| `Space + drag` | Pan |

All keyboard handlers are attached at the page root and ignored if the
focused element is `input`, `textarea`, or `[contenteditable]`.

## 6. Loading / empty / error

| Layer | Loading | Empty | Error |
|---|---|---|---|
| Page (initial) | Skeleton blocks in place of cards | "अभी कुछ नहीं मिला" centered card | Inline `--danger` banner above the content section, with "पुनः प्रयास" retry button |
| Graph fetch | Dotted grid stays; nodes fade in as data arrives | Centered "अभी कोई डेटा नहीं" card on canvas | Toast top-right, 8 s; previous nodes remain |
| Expand-from-node | Existing nodes stay; new nodes fade in over 200 ms | (n/a) | Inline 300 ms shake of clicked node + toast |
| Search | Disable submit, show 16 px `Loader2` inside the button | Result block reads `कोई परिणाम नहीं मिला` | Inline `--danger` block under the search |

## 7. Animations

| What | Duration | Easing |
|---|---|---|
| Side-panel slide-in | 200 ms | `ease-out` |
| Side-panel slide-out | 160 ms | `ease-in` |
| Node fade-in (new from expand) | 200 ms | `ease-out`, staggered 30 ms per node |
| Edge stroke draw-in | 300 ms (path `stroke-dasharray` trick) | `ease-out` |
| Hover shadow | 120 ms | `ease-out` |
| Selected fill color change | 160 ms | `ease-in-out` |
| Camera pan-to-node | 400 ms | `ease-in-out` cubic |
| Camera fit-to-content | 600 ms | `ease-in-out` cubic |

Respect `prefers-reduced-motion`: drop all duration-> 0 except shadow
and selected-fill (those are < 200 ms and acceptable).

## 8. Devanagari input gotchas

- Normalize all string inputs to NFC before sending to the backend and
  before storing in URL params (`lib/format/devanagari.ts`).
- Compare strings using NFC-normalized form. Never `===` user input
  against backend strings directly.
- The global search debounces 250 ms and only submits queries of length
  ≥ 1 Devanagari grapheme cluster (use `Intl.Segmenter`).

## 9. Deep-link rules

- All "Open in graph" CTAs across detail pages route to
  `/graph?node=<nk>&depth=2`.
- Sharing the graph URL re-creates the same view. The store is
  reconstructed from URL params via `expandFromNode` on mount.
