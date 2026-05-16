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
| `HIER_MAX_PER_ROW` | 4 | Max nodes per horizontal row before wrapping |

### Known limitations / future work

- `focusNk` is not added to the effect deps — if the user selects a different node and expects the hierarchy to re-root, they must switch layout away and back. This was intentional to avoid jarring position resets on every node click.
- Dragging a node in hierarchical mode pins it (`fx`/`fy`), but switching layout and back resets all positions.
- Radial layout is still a placeholder (disabled radio option).

## Bugfix - 1

There was a bug in d3-force's architecture: the exported simulation.tick() (line 39 in the source) runs physics but returns simulation without calling event.call("tick") — the event is only dispatched from the internal step() function that the timer invokes. So calling sim.tick() manually updated D3's internal node coordinates but our DOM handler was never called, leaving every <foreignObject> stuck at x=0, y=0. 
 
The fix uses sim.alpha(0.001).restart() in static mode:
- alpha = 0.001 = alphaMin → the timer fires one async tick via step() → emits the "tick" event → our handler runs and applies fx/fy coordinates to every foreignObject and edge path → alpha then decays below alphaMin → sim auto-stops

Also a secondary benefit: the async firing guarantees React has already committed the DOM and registerNode ref callbacks have populated nodeElsRef before the tick runs.

Also,  instead of placing all nodes of a BFS level in a single row, it chunks them into groups of HIER_MAX_PER_ROW = 5 and increments currentY after each chunk. For a landing page with 10 topic nodes at the same level, you'd get two rows of 5 instead of one row of 10 sprawling off-screen.

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

Backend (navigation_service) 
 
- config.py: Added LANDING_SEED_KEYWORDS = ["keyword:द्रव्य", "keyword:पर्याय"] r uters/graph.py: Added GET /v1/landing/random?depth=&exclud _stubs= — picks a random seed, calls the existing expand logic, falls back across seeds if empty, returns 503 with {"code": "no_seed_available"} if 
all fail ─ ── ─ ─ ── ─ ─ ──── ─── ─── ─ ── ──
- tests/test_landing_random.py: 6 tests covering focus_nk in seed list, depth param, depth=5 rejection, and fallback behavior

Frontend 
- navigation.ts: Added getNavLandingRandom(depth) calling the new endpoint; getNavLanding marked deprecated
- page.tsx: Boot sequence uses getNavLandingRandom(parsed.depth) when no ?node in URL; immediately writes ?node=focus_nk via history.replaceState so refresh is deterministic
- graphViewHelpers.ts: Removed MAX_GRAPH_NODES = 20 constant and the .slice() in buildCanvasNodes; limit parameter removed 
- graphViewHelpers.test.ts + navigation.test.ts: Tests updated/added (256 frontend tests all pass, 44/48 backend tests pass — 4 pre-existing failures unrelated to this change)
 
Manual verification steps (from the spec, for Phase 1):
1. pnpm dev + navigation service running 
2. Navigate to /graph with no query params — confirm a different seed renders each refresh, depth=2 by default, URL rewrites to ?node=…
3. Change depth stepper — confirm node count grows with depth