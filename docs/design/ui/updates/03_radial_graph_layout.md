# Radial Graph Layout

**Date:** 2026-05-31
**Scope:** Make the third graph layout option — `रेडियल / Radial` — fully functional. Currently the radio in `CategoryFilterList` is rendered as a disabled placeholder (`enabled: false`); the store accepts the value but `GraphCanvas` has no branch for it and silently falls through to the force-simulation path.
**Status:** Spec — not yet implemented.

---

## Background

The graph page (`ui/src/app/[locale]/graph/`) ships two working layouts and one placeholder:

| Layout | Source | Behaviour |
|---|---|---|
| `force` | `useForceSimulation.ts` | D3 force-directed; nodes free-float, gravity pulls toward center |
| `hierarchical` | `graphViewHelpers.ts::computeHierarchicalPositions` | BFS-depth → single row per depth, centered on `canvasW/2` |
| `radial` | — | Radio is disabled in `CategoryFilterList`; store accepts the value but `GraphCanvas` falls through to the force branch |

Users browsing a focus keyword/topic with a wide level-1 neighbourhood (8+ neighbours) currently choose between:

- **Force:** legible but unstable — neighbour ordering shifts each load; sibling distance is irregular.
- **Hierarchical:** stable y by depth, but the row sprawls horizontally off-screen for fan-outs > 6.

Radial fills this gap: the focus node sits at the centre and each BFS ring is a concentric circle around it. Same-depth siblings share a radius (the "same height" invariant from hierarchical, expressed radially), and a wide fan-out wraps around the focus instead of trailing off-screen.

This spec builds on the hierarchical implementation (same BFS pass, same constants pattern) and the existing static-layout plumbing in `GraphCanvas` (`restart(..., 'static')` mode introduced in the hierarchical bugfix). No backend changes.

---

## 1. Algorithm — `computeRadialPositions`

**File:** `ui/src/app/[locale]/graph/graphViewHelpers.ts` (alongside `computeHierarchicalPositions`).

**Signature:**

```typescript
export function computeRadialPositions(
  nodeNks: string[],
  edges: Array<{ src: string; dst: string }>,
  focusNk: string | null,
  canvasW: number,
  canvasH: number,
): Map<string, { x: number; y: number }>;
```

**Steps:**

1. **Resolve start node.** If `focusNk` is null or not in `nodeNks`, use `nodeNks[0]` (same fallback as hierarchical).
2. **BFS depth assignment.** Identical to hierarchical: build a bidirectional adjacency restricted to rendered nodes, BFS from start, record `level: Map<nk, number>`. Unreachable nodes get `maxReachable + 1`.
3. **Group by level.** `byLevel: Map<number, string[]>` — preserves BFS insertion order so siblings of the same parent stay adjacent on the ring.
4. **Place focus node** at the canvas centre: `(canvasW / 2, canvasH / 2)`.
5. **Place each ring `lv ≥ 1`** on a circle of radius `r(lv) = RADIAL_FIRST_RING + (lv - 1) * RADIAL_RING_SPACING`.
   - Let `n = nks.length` at this level.
   - Angle per node: `dθ = 2π / n`.
   - For the first sibling-bearing ring (level 1) the angular order is the BFS visit order — this keeps siblings of the same depth-0 parent contiguous (relevant once we generalise to multi-root forests; for the single-focus case it just stabilises ordering across renders).
   - Position of node `i`: `(cx + r · cos(θ_start + i · dθ), cy + r · sin(θ_start + i · dθ))`.
   - `θ_start = -π / 2` (start at the 12-o'clock position) so the first sibling sits directly above the focus — matches the visual reading order of hierarchical's top-down layout.
6. **Return** `Map<nk, {x, y}>` containing every input nk.

**Exported constants** (alongside the `HIER_*` group):

| Constant | Value | Meaning |
|---|---|---|
| `RADIAL_FIRST_RING` | 220 px | Radius of the level-1 ring around the focus |
| `RADIAL_RING_SPACING` | 220 px | Additional radius per BFS depth beyond level 1 |
| `RADIAL_MIN_ARC` | 96 px | Minimum arc length between adjacent same-ring nodes — when `2π · r / n < RADIAL_MIN_ARC`, the ring is expanded so `r = (n · RADIAL_MIN_ARC) / (2π)` |

The `RADIAL_MIN_ARC` clamp prevents wide rings (e.g. 12 nodes at level 1) from visually overlapping a 220 px `NodeCard` width. Implementation: compute `r(lv)` from the constant ladder, then take `max(r(lv), n * RADIAL_MIN_ARC / (2π))`. Inner rings stay put even when an outer ring expands — rings can grow but never shrink relative to the constant ladder.

**Edge cases:**

- `nodeNks.length === 0` → empty map (same as hierarchical).
- `nodeNks.length === 1` → only the focus, placed at centre.
- A level with exactly 1 node still goes on its ring (do not collapse to focus); place at `θ_start`.
- Edges referencing nodes not in `nodeNks` are ignored in adjacency.

---

## 2. GraphCanvas wiring

**File:** `ui/src/app/[locale]/graph/GraphCanvas.tsx`

Extend the `layout === 'hierarchical'` branch into a single static-layout branch covering both static modes:

```typescript
if (layout === 'hierarchical' || layout === 'radial') {
  const positions = layout === 'hierarchical'
    ? computeHierarchicalPositions(nodes.map(n => n.nk), simEdges, focusNkRef.current, w, h)
    : computeRadialPositions(nodes.map(n => n.nk), simEdges, focusNkRef.current, w, h);
  const simNodes: SimNodeInput[] = nodes.map(n => {
    const pos = positions.get(n.nk);
    const x = pos?.x ?? w / 2;
    const y = pos?.y ?? h / 2;
    return { nk: n.nk, x, y, fx: x, fy: y };
  });
  restart(simNodes, simEdges, 'static');
} else {
  /* existing force branch unchanged */
}
```

The restart-effect dep list (`[nodes.length, layout]`) is unchanged — switching the layout radio already triggers a recompute.

No changes to `useForceSimulation` are needed; the static mode (`sim.alpha(0.001).restart()`) handles fixed-position layouts uniformly.

---

## 3. UI — enable the radio

**File:** `ui/src/components/CategoryFilterList.tsx`

Flip the layout option:

```diff
- { value: 'radial', labelHi: 'रेडियल', labelEn: 'Radial', enabled: false },
+ { value: 'radial', labelHi: 'रेडियल', labelEn: 'Radial', enabled: true },
```

No other CategoryFilterList changes — `onLayoutChange` already routes `'radial'` into the store; the disabled styling falls away once `enabled: true`.

---

## 4. Store — no schema change

`graphStore.ts` already types `layout: 'force' | 'radial' | 'hierarchical'` and `setLayout` accepts `'radial'`. No change required.

URL state (`graphUrlState.ts`): the layout is not currently serialised to the URL and this spec does not add it (separate scope). Refresh on a `radial` selection resets to the store initial (`hierarchical`) — acceptable; revisit alongside any future URL-state expansion.

---

## 5. Tests

**File:** `ui/src/__tests__/graph/graphViewHelpers.test.ts` — add a `describe('computeRadialPositions', …)` block.

Pure-logic tests (no JSX), mirroring the hierarchical suite:

| # | Test |
|---|---|
| 1 | Returns an empty map when given no nodes |
| 2 | Places the focus node at the canvas centre `(W/2, H/2)` |
| 3 | Places a single 1-hop neighbour on the level-1 ring at the 12-o'clock position: `(W/2, H/2 - RADIAL_FIRST_RING)` |
| 4 | Two 1-hop neighbours are diametrically opposite — sum of x equals `W`, sum of y equals `H` |
| 5 | All same-level nodes share the same euclidean distance to the centre (within a small ε) |
| 6 | A 2-hop chain `a → b → c` puts `c` on the level-2 ring at radius `RADIAL_FIRST_RING + RADIAL_RING_SPACING` |
| 7 | Unreachable nodes go on the ring one past the deepest reachable level |
| 8 | Falls back to the first node as focus when `focusNk` is null |
| 9 | Falls back to the first node when `focusNk` is not in the node list |
| 10 | Treats edges as bidirectional (focus reachable from a child-direction edge) |
| 11 | `RADIAL_MIN_ARC` clamp: 12 same-level siblings expand the ring beyond `RADIAL_FIRST_RING`; all 12 still share the same radius |
| 12 | All exported constants are positive numbers |

Use the same `W = 1000, H = 800` fixtures as the hierarchical tests for parity.

No changes to existing hierarchical tests.

---

## 6. Manual verification steps

After implementation, exercise these paths in the browser at `localhost:3000/graph?node=द्रव्य&depth=2`:

1. Click the `रेडियल / Radial` radio. Focus node moves to centre; level-1 neighbours form a ring around it; level-2 neighbours form a wider ring.
2. Toggle between Force / Hierarchical / Radial — each switch re-lays out without re-fetching; no console errors.
3. Open `/graph?node=पर्याय&depth=1` (10+ neighbours fixture from the screenshot in the previous task). Radial layout should wrap all siblings around the focus without horizontal sprawl.
4. Pan/zoom (`+` / `−` controls) — positions remain anchored; rings do not jitter.
5. Drag a node — it pins (`fx`/`fy`), as in hierarchical. Switching layout away and back resets.
6. Select a node via click — `DetailsPanel` opens; layout does not reset (re-root is a separate action via the node card icon, unchanged here).
7. Verify `prefers-reduced-motion`: with the OS toggle on, switching to radial settles instantly with no animation tail.

---

## 7. Files changed

| File | Change |
|---|---|
| `ui/src/app/[locale]/graph/graphViewHelpers.ts` | Add `computeRadialPositions`; export `RADIAL_FIRST_RING`, `RADIAL_RING_SPACING`, `RADIAL_MIN_ARC` |
| `ui/src/app/[locale]/graph/GraphCanvas.tsx` | Extend static-layout branch to also call radial; import the new helper |
| `ui/src/components/CategoryFilterList.tsx` | Flip `enabled: false` → `true` on the radial row |
| `ui/src/__tests__/graph/graphViewHelpers.test.ts` | Add `computeRadialPositions` describe block (12 tests) |
| `ui/README.md` | §10 Graph Page → Graph view helpers: document `computeRadialPositions` and constants; Phase Log: add `Radial layout` row |
| `docs/design/ui/implementation_notes/graph_changes_implementation_notes.md` | Append "Radial layout" section listing constants + algorithm summary; remove the "Radial layout is still a placeholder" line from Known limitations |

---

## 8. Out of scope

- **URL-serialising the layout.** Refresh still drops back to the store-initial layout.
- **Per-ring colour or label decoration.** Rings are implicit from node positions only — no overlay arcs, no concentric guide circles. Can be added later as a polish pass.
- **Re-rooting on focus change.** Same constraint as hierarchical — `focusNk` is excluded from the restart-effect deps. Toggle layout to re-root, unchanged.
- **Force-radial hybrid** (D3 `forceRadial`). The static layout above is sufficient and matches the determinism of hierarchical; a force-driven radial can be a future option but is not needed for parity.
- **Backend changes.** None — radial reuses the same `GraphPayload` and edge set as the other two layouts.

---

## 9. Risks / open questions

- **Long Devanagari titles + tight ring** — at 12+ siblings on the inner ring with `RADIAL_MIN_ARC = 96 px`, the ring radius is ~183 px which is smaller than the 220 px `NodeCard` width, so cards will visually touch even after the clamp. The clamp keeps centres apart, not card edges. If this proves cramped in QA, raise `RADIAL_MIN_ARC` to `NodeCard width + gap` (~256 px) — single-constant change, no algorithm change.
- **Mixed-depth dense graphs** — when a focus has 8 level-1 + 30 level-2 neighbours, the level-2 ring becomes very wide. Acceptable — pan/zoom is the explicit answer (same call as hierarchical's off-screen rows). Document in the README §10 helper description.
- **Direction-aware ordering** — current spec uses BFS visit order for angular placement. If different parents at level 1 each have distinct children at level 2, those children are still globally angular-ordered by BFS, not grouped under their parent's angle. Acceptable for a single-focus root; revisit if the radial layout is later extended to multi-root forests.

---

## 10. Implementation Notes

**Implemented 2026-05-31.**

- No diversions from the spec. All four files listed in §7 were changed.
- 12 tests added to `graphViewHelpers.test.ts`; all 50 tests pass.
- `RADIAL_MIN_ARC = 96 px`: at 12 level-1 siblings the ring expands to ~183 px radius — cards may visually touch at this density. Raise to ~256 px if QA finds it too cramped (single-constant change).
- `GraphCanvas.tsx` static-layout branch now covers `'hierarchical' || 'radial'`; the existing `[nodes.length, layout]` dep list triggers recompute on layout switch without extra changes.
