# Phase 4 — Handoff / Session State

## What was implemented this session

### New files created

| File | What |
|------|------|
| `ui/src/components/NodeCard.tsx` | Node card component — all 4 entity kinds, 5 states (resting/hover/selected/faded/pinned), `NODE_KIND_META` exported for tests |
| `ui/src/components/RelationConnector.tsx` | Static SVG connector — cubic Bézier + endpoint circles + rotating pill label. `EDGE_LABELS` + `EDGE_TOOLTIPS` exported for tests. Used for the `/dev` gallery; GraphCanvas renders edges via direct DOM refs instead |
| `ui/src/components/CategoryFilterList.tsx` | Left-pane filter — 4 category rows with colour swatches + Switch, Layout radio group (Force active, Radial/Hierarchical disabled), Depth stepper 1–4, Reset link. `CATEGORY_DATA` exported for tests |
| `ui/src/app/[locale]/graph/useForceSimulation.ts` | D3-force hook — **direct DOM manipulation, zero React re-renders per tick**. Exports `buildBezierPath()` (pure function, unit-testable). Returns stable `registerNode`, `registerEdge`, `restart` refs |
| `ui/src/app/[locale]/graph/ZoomControls.tsx` | Three 36 px buttons (Plus / Minus / Maximize2), bottom-left of canvas |
| `ui/src/app/[locale]/graph/GraphCanvas.tsx` | SVG canvas — dotted grid (panning/scaling pattern), camera state (translate+scale), pan on drag, wheel zoom. Uses `React.memo` boundary (`EdgesAndNodes`) so camera state changes never re-render the force-sim-managed subtree |

### Files updated

| File | What changed |
|------|------|
| `ui/src/app/[locale]/graph/layout.tsx` | Now a `'use client'` component; mounts `CategoryFilterList` in the 280 px left pane with local `visibility` + `depth` state |
| `ui/src/app/[locale]/graph/page.tsx` | Replaces placeholder with `GraphCanvas` + 5 hard-coded demo nodes (all 4 kinds, selected/faded/pinned states) + 4 demo edges |

---

## What still needs to be done (in this session's scope)

### 1. Test files — NOT yet written

All four Phase 4 test files are planned but not created. Write them in `vitest` (Node, no browser), testing only pure/exported constants:

#### `ui/src/components/NodeCard.test.ts`
- `NODE_KIND_META` has entries for all 4 EntityKinds
- Each entry has non-empty `labelHi` (Devanagari), non-empty `labelEn`, a `catVar` starting with `var(--cat-`
- `Icon` field is a function (renderable React component)
- Spot-check: `shastra.labelHi === 'शास्त्र'`, `catVar === 'var(--cat-shastra)'`

#### `ui/src/components/RelationConnector.test.ts`
- `EDGE_LABELS` has exactly 11 EdgeKind keys (all of the EdgeKind union)
- `EDGE_TOOLTIPS` has exactly 11 keys matching `EDGE_LABELS`
- Each value is a non-empty string
- Spot-check a few: `IS_A → 'है का प्रकार'`, `RELATED_TO → 'संबंधित'`

#### `ui/src/components/CategoryFilterList.test.ts`
- `CATEGORY_DATA` has exactly 4 items
- Each item has `kind`, `labelHi`, `labelEn`, `catVar` fields
- All 4 EntityKinds are covered (no duplicates)
- Each `catVar` starts with `var(--cat-`

#### `ui/src/app/[locale]/graph/useForceSimulation.test.ts`
Tests for `buildBezierPath` (the only exported pure function):
```ts
import { buildBezierPath } from './useForceSimulation';

describe('buildBezierPath', () => {
  test('returns a valid SVG cubic Bézier path string', () => {
    const { d } = buildBezierPath(0, 0, 400, 0);
    expect(d).toMatch(/^M -?\d+(\.\d+)? -?\d+(\.\d+)? C .+/);
  });

  test('provides a1 on the left side of source when target is to the right', () => {
    const { a1 } = buildBezierPath(100, 100, 400, 100);
    expect(a1.x).toBe(100 + 110); // right anchor: cx + CARD_HALF_W
    expect(a1.y).toBe(100);
  });

  test('provides a2 on the right side of target when source is to the left', () => {
    const { a2 } = buildBezierPath(100, 100, 400, 100);
    expect(a2.x).toBe(400 - 110); // left anchor: cx - CARD_HALF_W
  });

  test('angle is clamped to [-20, +20] degrees', () => {
    // Steep vertical edge would exceed ±20° without clamping
    const { angle } = buildBezierPath(0, 0, 0, 500);
    expect(angle).toBeGreaterThanOrEqual(-20);
    expect(angle).toBeLessThanOrEqual(20);
  });

  test('mid-point is defined', () => {
    const { mid } = buildBezierPath(0, 0, 300, 200);
    expect(typeof mid.x).toBe('number');
    expect(typeof mid.y).toBe('number');
  });
});
```

### 2. `implementation_notes.md` update — NOT yet written

Append a **Phase 4** section with the same table-driven format used in earlier phases. Key points to document:

- **Architecture decision**: `React.memo` boundary (`EdgesAndNodes`) separates camera React state from force-sim-managed DOM. Camera changes re-render the `<g transform>` wrapper but NOT the foreignObject/path subtree, so D3's direct DOM writes persist across React renders.
- **Grid pattern**: screen-space `<pattern>` with `patternTransform` that tracks `camera.x % tileSize` and `camera.y % tileSize`. Dot radius clamped to `[0.75, 1.5]` px = `Math.max(0.75, Math.min(camera.k, 1.5))`.
- **RelationConnector vs GraphCanvas edges**: `RelationConnector` is the standalone static SVG component (used in `/dev` gallery and future detail pages). Inside `GraphCanvas`, edges are rendered as raw SVG elements (path + 2 circles + foreignObject) so the force-sim hook can hold refs to each element and update them directly.
- **`useForceSimulation` restart ref pattern**: `restart` is exposed as `useRef(...).current` (not `useCallback`) to guarantee a stable identity that never changes — important so the `EdgesAndNodes` memo boundary is not broken when the hook re-executes.
- **`accumulateEdgeRef` pattern**: each of the 4 SVG sub-elements for an edge (path, c1, c2, labelFo) registers independently via ref callbacks; only once all 4 are non-null does the full `EdgeEl` object get passed to `registerEdge`.
- Note: the `CategoryFilterList` state in `layout.tsx` is local-only in Phase 4. In Phase 5 it will be lifted into `useGraphState` (Zustand) so the canvas can respond to visibility toggles.

### 3. Verify the build passes

```bash
cd ui
pnpm build
pnpm test
```

Common issues to watch for:
- `'use client'` in `layout.tsx` — Next.js App Router requires that a layout using `useState` is a client component. This is intentional and correct.
- `d3-force` ESM imports in Vitest — should work; if not, add `{ ssr: false }` in vitest config or transform the package.
- TypeScript: `SVGForeignObjectElement` is in the `lib.dom` types; ensure `tsconfig.json` includes `"dom"` in `lib`.

---

## Checkpoint 4 verification (manual UI checks)

Once `pnpm dev` is running, visit `http://localhost:3000/graph`:

1. **Dotted grid** — grey dots on white/light-grey background, 24 px spacing. Pan with drag → dots move with the canvas. Zoom with wheel → dot spacing scales (dots stay small, never disappear or grow huge).
2. **NodeCards** — five cards appear and settle via force simulation:
   - शास्त्र (BookOpen icon, red stripe + red selected fill, white text)
   - गाथा (ScrollText icon, orange stripe)
   - विषय (Tag icon, teal stripe)
   - कीवर्ड (Sparkles icon, dark-teal stripe, 25% opacity = faded)
   - समयसार शास्त्र (Pin icon visible = pinned state)
3. **RelationConnector edges** — Bézier curves with:
   - Small circles at each anchor point
   - Rotating pill labels (विषय, कीवर्ड, शास्त्र में, संबंधित)
   - Active edge (e1: IN_SHASTRA) renders in `--accent` red; others in `--graph-edge` muted blue
4. **Force sim** — cards animate from their initial positions to a settled layout. Simulation stops automatically (alpha < 0.001).
5. **CategoryFilterList** (left pane, visible at xl+ viewport):
   - Four coloured swatches with labels
   - Switches default ON
   - Layout radios: Force active, Radial + Hierarchical disabled/grey
   - Depth stepper at 2, −/+ buttons work, clamped 1–4
   - "Reset graph" link
6. **ZoomControls** (bottom-left of canvas):
   - Plus → zoom in (anchored to canvas centre)
   - Minus → zoom out
   - Maximize2 → animated fit-to-content (resets camera to identity over 600 ms)
7. **Empty state** — temporarily pass `nodes={[]}` to `<GraphCanvas>` → centered card with "अभी कोई डेटा नहीं है / No graph data yet"
8. **Mobile / tablet** (<xl viewport): left filter pane is hidden; canvas fills full width.
9. **Reduced-motion**: enable `prefers-reduced-motion` in browser → force sim should still run (it's D3-internal; the CSS `animation-duration: 0ms` rule applies to CSS animations, not D3's RAF loop — this is acceptable in Phase 4; Phase 8 will add the explicit check in `useForceSimulation`).

---

## Key design decisions made

| Decision | Rationale |
|---|---|
| `React.memo` boundary for `EdgesAndNodes` | Prevents camera state re-renders from overwriting D3's direct DOM position updates |
| `useRef(...).current` for stable `registerNode`/`registerEdge`/`restart` | These are never recreated, so they can be passed to memoised children without breaking equality checks |
| `accumulateEdgeRef` with 4-part accumulator | Each SVG element registers independently (React's ref callback fires per-element); the hook only gets called once all 4 are ready |
| Grid pattern in screen space (outside camera `<g>`) | Prevents the grid from being part of the memoised subtree; camera state drives the pattern transform via React state, which is correct and lightweight |
| `RelationConnector` is NOT used inside `GraphCanvas` | The force-sim hook needs direct refs to the `<path>`, two `<circle>`s, and label `<foreignObject>` separately; `RelationConnector` is kept as a standalone static component for `/dev` gallery and future static previews |
| `CategoryFilterList` state is local to `layout.tsx` in Phase 4 | Phase 5 will wire it to the Zustand `useGraphState` store so visibility changes fade nodes in the canvas |
