# Graph Changes — Implementation Notes

## Hierarchical Layout Mode (2026-05-15)

### What was built

Implemented a fully-functional **Hierarchical layout** for the graph page and made it the default. Users can switch between Force and Hierarchical via the left-panel radio. Radial remains a placeholder.

### Design decisions

**BFS depth from focus node** (not entity-kind tiers)
The hierarchy levels are determined by graph distance from the current focus node (selected node → first expanded node → first canvas node). The focus node sits at depth 0 (top row); each hop adds one row below. This works for any graph topology, not just the Shastra→Gatha→Topic→Keyword entity-kind chain.

**Fully static positions — no force simulation**
In hierarchical mode the D3 force sim is stopped and nodes are fixed via `fx`/`fy`. A single synchronous `sim.tick()` is called to push the fixed positions to the DOM and compute edge bezier paths. No animation loop runs, so CPU stays idle while the layout is displayed.

**Switching layouts re-runs the restart effect**
`[nodes.length, layout]` are the `useEffect` deps in `GraphCanvas`. Switching Force→Hierarchical (or vice versa) triggers a fresh position computation. `focusNkRef` is read via a stable ref so that selecting a node mid-session doesn't re-trigger the layout — hierarchy is recomputed only on node-set or layout changes.

**Unreachable nodes** (disconnected from the focus node) are placed one row past the deepest reachable level, keeping them visible and not overlapping with the main hierarchy.

### Files changed

| File | Change |
|---|---|
| `graph/graphViewHelpers.ts` | Added `computeHierarchicalPositions` + exported `HIER_LEVEL_HEIGHT`, `HIER_NODE_SPACING`, `HIER_PADDING_TOP` constants |
| `graph/useForceSimulation.ts` | `restart` accepts optional `mode: 'force' \| 'static'`; static mode stops sim and ticks once synchronously |
| `graph/GraphCanvas.tsx` | Added `layout` + `focusNk` props; `useEffect` deps now `[nodes.length, layout]`; branches to hierarchical path which passes `fx/fy` fixed nodes |
| `graph/page.tsx` | Subscribes to `layout` from store; derives `focusNk`; passes both to `GraphCanvas` |
| `lib/store/graphStore.ts` | `initialState.layout` changed from `'force'` to `'hierarchical'` |
| `components/CategoryFilterList.tsx` | Hierarchical radio option `enabled` changed to `true` |
| `graph/graphViewHelpers.test.ts` | 10 new tests for `computeHierarchicalPositions` |

### Layout constants

| Constant | Value | Meaning |
|---|---|---|
| `HIER_PADDING_TOP` | 120 px | Top margin before depth-0 row |
| `HIER_LEVEL_HEIGHT` | 240 px | Vertical gap between consecutive depth levels |
| `HIER_NODE_SPACING` | 320 px | Horizontal gap between nodes in the same level |

### Known limitations / future work

- `focusNk` is not added to the effect deps — if the user selects a different node and expects the hierarchy to re-root, they must switch layout away and back. This was intentional to avoid jarring position resets on every node click.
- Dragging a node in hierarchical mode pins it (`fx`/`fy`), but switching layout and back resets all positions.

## Radial Layout (2026-05-31)

### What was built

Implemented the **Radial layout** for the graph page. The focus node is placed at the canvas centre; each BFS ring is a concentric circle at `RADIAL_FIRST_RING + (level - 1) * RADIAL_RING_SPACING`. The `RADIAL_MIN_ARC` clamp expands rings when the arc-per-node would fall below 96 px, preventing card overlap on dense inner rings. Unreachable nodes go one ring past the deepest reachable level, consistent with hierarchical.

### Layout constants

| Constant | Value | Meaning |
|---|---|---|
| `RADIAL_FIRST_RING` | 220 px | Radius of the level-1 ring around the focus |
| `RADIAL_RING_SPACING` | 220 px | Additional radius per BFS depth beyond level 1 |
| `RADIAL_MIN_ARC` | 96 px | Minimum arc length between adjacent same-ring nodes |

### Algorithm summary

1. BFS from `focusNk` (fallback: `nodeNks[0]`), identical to hierarchical.
2. Group nodes by BFS level.
3. Place focus at `(canvasW/2, canvasH/2)`.
4. For each ring `lv ≥ 1`: compute `r = max(RADIAL_FIRST_RING + (lv-1)*RADIAL_RING_SPACING, n*RADIAL_MIN_ARC/(2π))`; distribute nodes evenly from `θ_start = -π/2` (12 o'clock).

### Files changed

| File | Change |
|---|---|
| `graph/graphViewHelpers.ts` | Added `computeRadialPositions`; exported `RADIAL_FIRST_RING`, `RADIAL_RING_SPACING`, `RADIAL_MIN_ARC` |
| `graph/GraphCanvas.tsx` | Extended static-layout branch to `layout === 'hierarchical' \|\| layout === 'radial'`; imports `computeRadialPositions` |
| `components/CategoryFilterList.tsx` | Radial radio `enabled` flipped to `true` |
| `graph/graphViewHelpers.test.ts` | 12 new tests for `computeRadialPositions` |

---

## Bugfix - 1

There was a bug in d3-force's architecture: the exported simulation.tick() (line 39 in the source) runs physics but returns simulation without calling event.call("tick") — the event is only dispatched from the internal step() function that the timer invokes. So calling sim.tick() manually updated D3's internal node coordinates but our DOM handler was never called, leaving every <foreignObject> stuck at x=0, y=0. 
 
The fix uses sim.alpha(0.001).restart() in static mode:
- alpha = 0.001 = alphaMin → the timer fires one async tick via step() → emits the "tick" event → our handler runs and applies fx/fy coordinates to every foreignObject and edge path → alpha then decays below alphaMin → sim auto-stops

Also a secondary benefit: the async firing guarantees React has already committed the DOM and registerNode ref callbacks have populated nodeElsRef before the tick runs.

Note (2026-05-31 update): the earlier row-wrapping behavior (chunking each BFS level into rows of `HIER_MAX_PER_ROW`) was reverted. All nodes at the same BFS depth are now placed on a single horizontal row at the same y, even when the row extends beyond the visible canvas. Reason: wrapped rows broke the visual invariant of "same depth = same height" — a row of 5 + a row of 2 looked like two separate levels. Off-screen nodes are reachable via pan/zoom.

## Bugfix - 2

bugfix: duplicate edges, The fix is in graphViewHelpers.ts:buildCanvasEdges. Here's what changed:

Root cause: The backend returns both A→B PART_OF and B→A PART_OF as separate edges with different IDs. Both survived the filter and were rendered as overlapping SVG paths between the same node pair — producing
the visual duplicate lines (and a loop artifact when the force sim placed them on top of each other).

Fix: After filtering valid edges, buildCanvasEdges now deduplicates by a canonical key min(src,dst) + '\x00' + max(src,dst) + '\x00' + kind. The first-seen edge is kept as the representative; if the other
direction's ID happens to be the selected one, the representative is promoted to active: true so the highlight still works.

Tests added/updated:
- Updated 'marks the active edge' to use genuinely different edge pairs (not a bidirectional duplicate)
- New: 'deduplicates A→B and B→A edges with the same kind into one rendered edge'
- New: 'marks the representative active when the duplicate direction is selected'
- New: 'keeps distinct edges between different node pairs'

---
## 02_graph_traversal_and_node_colors.md changes

### Section 1

### Decisions / Diversions

- **Seed fallback condition**: uses `payload.edges` (non-empty) rather than `len(nodes) > 1`. An isolated node with no edges is not useful as a landing seed regardless of whether Neo4j returned a record for it.
- **Fallback attempts**: capped at `min(4, len(LANDING_SEED_KEYWORDS))` — shuffles the list and tries up to 4. With only 2 seeds this tries both.
- **URL rewrite in boot**: writes `?node=focus_nk` directly via `history.replaceState` inside the `boot` function (not via the 500 ms debounce), so the URL is deterministic immediately on first render before the debounce fires.
- **`buildCanvasNodes` signature**: `limit` parameter removed entirely (was dead code after removing the slice). No callers used it except tests.
- **Pre-existing test failures**: `test_edges.py` (4 tests) fails due to a missing `edge_types.yaml` — unrelated to this change.

Backend (navigation_service) 
 
- config.py: Added LANDING_SEED_KEYWORDS = ["keyword:द्रव्य", "keyword:पर्याय"] r uters/graph.py: Added GET /v1/landing/random?depth=&exclud _stubs= — picks a random seed, calls the existing expand logic, falls back across seeds if empty, returns 503 with {"code": "no_seed_available"} if 
all fail ─ ── ─ ─ ── ─ ─ ──── ─── ─── ─ ── ──
- tests/test_landing_random.py: 6 tests covering focus_nk in seed list, depth param, depth=5 rejection, and fallback behavior

Frontend 
- navigation.ts: Added getNavLandingRandom(depth) calling the new endpoint; getNavLanding marked deprecated
- page.tsx: Boot sequence uses getNavLandingRandom(parsed.depth) when no ?node in URL; immediately writes ?node=focus_nk via history.replaceState so refresh is deterministic
- graphViewHelpers.ts: Removed MAX_GRAPH_NODES = 20 constant and the .slice() in buildCanvasNodes; limit parameter removed 
- graphViewHelpers.test.ts + navigation.test.ts: Tests updated/added (256 frontend tests all pass, 44/48 backend tests pass — 4 pre-existing failures unrelated to this change)

### Bugfixes:

Bug 1 - Depth stepper had no effect on the graph data layout.tsx was calling setDepth() which only updated the number in the store — it never re-fetched from the backend. So changing depth=2 → depth=1 kept all the same (accumulated) nodes visible.
 
Fix: Added a changeDepth(depth) action to the store (graphStore.ts:125-144) that:
1. Updates the depth value
2. Re-fetches expandNode from the current focus node at the new depth (selected node → seed node → nothing)
3. Replaces (not merges) the graph data so the canvas reflects exactly depth-N from the focus
 
layout.tsx now calls changeDepth instead of setDepth.
 
Bug 2 — URL lost the seed node 500ms after boot

When loading with no ?node= param, the boot picked a random seed and called seedFromPayload(landing, null). 500ms later the URL sync effect fired and wrote ?depth=2 with no ?node= (because nothing was 
"selected"). On the next refresh, a different random seed was picked.
 
Fix: Added seedNk: string | null to the store state, set on every seedFromPayload call. The URL sync in page.tsx now uses selectedNode ?? seedNk so ?node= is always preserved in the URL even when no node is 
explicitly selected

### Section 2

Behavior changes:
- onNodeClick / onNodeDoubleClick → now only call selectNode (no auto-expand)
- Each NodeCard has two new icon buttons: Maximize2 (expand) and ChevronRight (details), both with proper aria-label and stopPropagation 
- The expand button is visually accented (text-accent) when the node is already expanded 
 
Collapse logic:
- nodeOrigins: Record<string, Set<string>> tracks which expander (or 'seed') brought each node into the graph
- Seed nodes get origin 'seed' and are never removable by collapse 
- expandFromNode adds the expander's nk to each node's origin set
- collapseNode(nk) removes nk from all origin sets, then deletes any node whose origin set is now empty (except seedNk), and cleans up dangling edges

### Section 3

#### Decisions / Diversions

- **`bandIconBoxBg` field added to `NODE_KIND_META`**: The spec only mentions `bandFg`, but the icon box needs a distinct translucent overlay per band lightness. Rather than deriving it from `bandFg` at render time (fragile string comparison), the value is stored explicitly in the META: `rgba(255,255,255,0.18)` for white-text bands (shastra, topic, keyword) and `rgba(0,0,0,0.10)` for the dark-text gatha band.
- **`--cat-topic` darkened to `#1D7A6F`**: Spec preferred this route over bumping font size. The existing theme test's `#2A9D8F` assertion was updated to `#1D7A6F`. The old value no longer appears anywhere in the CSS.
- **Button idle/hover**: Instead of `text-foreground-subtle hover:text-foreground` (which relied on absolute token colors), buttons inside the band now use `opacity-70 hover:opacity-100` so they lighten/darken relative to the inherited `bandFg` color. This keeps hover behavior correct across all four band colors without needing per-kind button token overrides.
- **Label font size**: Spec suggested bumping Topic band label to `14px` for WCAG. Since the fix is to darken the token instead, the label size was unified at `14px` (`text-[14px]`) across all four kinds (previously `var(--font-size-sm)` = 13px). This is a minor size bump that also improves readability on the colored bands generally.
- **Pin indicator position**: Kept `absolute right-[72px] top-2` unchanged — the band wraps the inner flex row at the same depth as the old header div, so relative positioning is unaffected.

#### Files Changed

- `ui/src/styles/theme.css` — `--cat-topic` darkened to `#1D7A6F`; `--cat-*-fg` tokens added
- `ui/src/app/globals.css` — `--color-cat-*-fg` mapped in `@theme inline`
- `ui/src/components/NodeCard.tsx` — `bandFg`/`bandIconBoxBg` added to `NODE_KIND_META`; 4 px stripe removed; header band replaces old header row
- `ui/src/components/NodeCard.test.ts` — two new `describe` blocks for `bandFg` field and CSS variable values
- `ui/src/styles/theme.test.ts` — `--cat-*-fg` tokens added to `REQUIRED_TOKENS`; topic color assertion updated; new `it` block for fg hex values