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
| `HIER_PADDING_TOP` | 100 px | Top margin before depth-0 row |
| `HIER_LEVEL_HEIGHT` | 180 px | Vertical gap between consecutive depth levels |
| `HIER_NODE_SPACING` | 260 px | Horizontal gap between nodes in the same level |

### Known limitations / future work

- `focusNk` is not added to the effect deps — if the user selects a different node and expects the hierarchy to re-root, they must switch layout away and back. This was intentional to avoid jarring position resets on every node click.
- Dragging a node in hierarchical mode pins it (`fx`/`fy`), but switching layout and back resets all positions.
- Radial layout is still a placeholder (disabled radio option).

## Bugfix - 1

There was a bug in d3-force's architecture: the exported simulation.tick() (line 39 in the source) runs physics but returns simulation without calling event.call("tick") — the event is only dispatched from the internal step() function that the timer invokes. So calling sim.tick() manually updated D3's internal node coordinates but our DOM handler was never called, leaving every <foreignObject> stuck at x=0, y=0. 
 
The fix uses sim.alpha(0.001).restart() in static mode:
- alpha = 0.001 = alphaMin → the timer fires one async tick via step() → emits the "tick" event → our handler runs and applies fx/fy coordinates to every foreignObject and edge path → alpha then decays below alphaMin → sim auto-stops

Also a secondary benefit: the async firing guarantees React has already committed the DOM and registerNode ref callbacks have populated nodeElsRef before the tick runs.
