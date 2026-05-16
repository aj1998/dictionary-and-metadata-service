# Graph Traversal Overhaul + Node Color Coding

**Date:** 2026-05-15
**Scope:** Graph page UX — depth-driven node loading, in-graph expand-to-source action, full-band category color coding. Includes a new navigation-service endpoint for picking a random seed keyword.
**Status:** Phases 1–3 implemented (Phase 1: 2026-05-15; Phase 3: 2026-05-16)

---

## Background

The current graph page (`ui/src/app/[locale]/graph/`) caps the rendered set to `MAX_GRAPH_NODES = 20` (see `graphViewHelpers.ts:buildCanvasNodes`). This was a stop-gap to keep the force/hierarchical layouts legible, but it severely limits exploration — only one BFS level of a busy keyword is visible at depth 2, and there is no Neo4j-Browser-like way to traverse outward from an arbitrary node.

Three concrete changes:

1. **Depth-driven loading, no node cap.** Initial load picks a random seed keyword from a config-defined list and shows its neighborhood expanded to the configured depth (default 2). Sub-graph size is bounded by depth, not by an arbitrary node-count slice.
2. **Re-root from any node.** Every `NodeCard` gains a second affordance — an "expand / re-root" icon next to the existing "open details" target. Clicking it re-renders the graph with that node as the new focus.
3. **Full-band category color coding.** Replace the 4 px top stripe on `NodeCard` with a full-width tinted header band so the `विषय / Topic` (and `कीवर्ड / Keyword`, etc.) text sits on the category color, making node kinds scannable at a glance.

The earlier hierarchical-layout work and the side-panel vivaran spec (`01_side_panel_vivaran.md`) are unaffected — this builds on top of them.

---

## 1. Random-seed Landing + Depth-Driven Sub-graphs

### 1a. New backend endpoint — `GET /v1/landing/random`

**Service:** `navigation-service` (port 8003)
**File:** `services/navigation_service/routers/graph.py`
**Returns:** `GraphPayload` (existing schema — `nodes`, `edges`, `focus_nk`, `depth`)

A small config-defined list of candidate seed keywords lives in `services/navigation_service/config.py`:

```python
# config.py
LANDING_SEED_KEYWORDS: list[str] = [
    "keyword:द्रव्य",
    "keyword:पर्याय",
]
```

Endpoint behavior:

1. Pick a random natural_key from `LANDING_SEED_KEYWORDS` (uniform `random.choice`).
2. Accept `?depth=` (default 2, clamped 1–4) and `?exclude_stubs=` (default true).
3. Internally call the same Cypher used by `expand(natural_key=…, depth=…)`.
4. Return the `GraphPayload` with `focus_nk` set to the chosen seed.

If a seed has no neighbors (degenerate), retry up to 3 alternative seeds; on full failure return 503 with `{"code": "no_seed_available"}`. Log the chosen seed for observability.

Tests (`services/navigation_service/tests/test_landing_random.py`):
- Returns a payload with `focus_nk` ∈ `LANDING_SEED_KEYWORDS`.
- Respects `depth` parameter.
- Falls back across seeds when the first is empty (mock Neo4j to return empty for nk 0).
- Reject `depth=5` (422).

### 1b. Remove the 20-node hard cap

`ui/src/lib/graph/graphViewHelpers.ts`:
- Delete `MAX_GRAPH_NODES = 20` and the `.slice(0, MAX_GRAPH_NODES)` in `buildCanvasNodes`.
- Keep the existing `buildCanvasEdges` dangling-edge filter and bidirectional-edge dedup (the `5d9c2e5` fix) — both still required.
- Update `graphViewHelpers.test.ts`: replace the node-limit assertions with assertions that depth-1 expansion returns exactly the depth-1 neighborhood the fixture describes, and that depth-2 returns the union of depth-1 + depth-2 neighbors.

Visual safety: the existing `expandFromNode` 300-node guard dialog (`graphStore.ts`) stays — it protects against pathological hubs (e.g. `द्रव्य` at depth 3+). The default depth remains 2 to keep most loads well under that threshold.

### 1c. UI client wiring

`ui/src/lib/api/navigation.ts`:
- Add `getNavLandingRandom(depth: number): Promise<GraphPayload>` calling `/api/navigation/v1/landing/random?depth={depth}`.

`ui/src/app/[locale]/graph/page.tsx` boot sequence:
- Step 3 currently calls `getNavLanding()` when there is no `?node`. Replace with `getNavLandingRandom(depth)` where `depth` is the depth already applied to the store from the URL (default 2).
- When the user lands with no `?node` param, the URL is rewritten on first sync to include the chosen `focus_nk` as `?node=…` so the back button and refresh remain deterministic. Use `history.replaceState` (consistent with the existing 500 ms debounced URL sync).

Existing `getNavLanding()` and `/v1/landing` are kept untouched — used nowhere else after this change, but left in place to avoid unnecessary deletes; mark with a `// deprecated: replaced by /v1/landing/random` comment.

---

## 2. Expand-from-Node Affordance on Each Node

> **Clarified behavior:** "Expand" does **not** replace the current graph. The currently rendered nodes/edges stay in place; clicking expand on a node fetches that node's neighborhood at the current depth and **merges** the result into the existing graph. Effectively, the user grows the visible sub-graph outward from any visible node, Neo4j-Browser style.

### Anatomy change to `NodeCard.tsx`

Today the entire card is a single click target that opens the right `DetailsPanel`. New layout:

```
┌─────────────────────────────────────────────────────┐
│  [icon]  विषय / Topic            [⤢ expand]  [›]    │ ← header band (full-width category color)
├─────────────────────────────────────────────────────┤
│  द्रव्य के भेद व लक्षण                                │
└─────────────────────────────────────────────────────┘
```

Two right-aligned icon buttons in the header band:

| Button | Icon (`lucide-react`) | Action |
|---|---|---|
| Expand from node | `GitBranchPlus` (or `Maximize2`) | Calls the existing `expandFromNode(nk, depth)` store action (additive merge) |
| Open details | existing `ChevronRight` | Existing `selectNode(nk)` behavior |

Click target rules:
- Clicking anywhere on the **body** (title row) → open details (unchanged).
- Clicking the **expand button** → re-root. Stops propagation; does not select.
- Both buttons get 32×32 hit area, focus ring, `aria-label` (`"इस नोड से ग्राफ़ का विस्तार करें"` / `"विवरण देखें"`).

### Store action — reuse `expandFromNode`

The existing `expandFromNode(nk, depth)` in `ui/src/lib/store/graphStore.ts` already does what's needed:
- Calls `expandNode(nk, depth)` against navigation-service.
- **Merges** new nodes/edges into the existing store (de-duped by `nk` / `id`).
- Seeds new node positions at the clicked node's current `{x, y}` so the layout grows outward smoothly rather than jumping.
- Has the 300-node confirmation guard — still wanted; if a single expand would push total > 300, prompt before merging.

The expand button on `NodeCard` simply invokes this action. No new store action required.

State the button leaves alone:
- `pinned` — preserved (previously pinned nodes are still on screen).
- `selected` — preserved. Expanding does not change which node's details are open. The user explicitly clicks the chevron / body to switch the details panel.
- `camera` — preserved. No re-center; the user can pan/zoom or use the existing fit-to-view control to reframe.

### URL contract

- `?node={nk}` continues to mean "seed/focus node" — set only on initial load (random landing) and never overwritten by an expand click. Expanding does not push history; it's an additive in-page operation, comparable to opening more rows in a list. A page refresh therefore returns to the original seed, not the most-recently-expanded node. This matches the user's mental model ("expand grows what's there") and avoids surprising back-button behavior.
- If we later want shareable "expanded views", we can serialize the merged node-set into a `?seeds=` CSV — out of scope for this update.

### Tests

`graphStore.test.ts` (additions):
- Expanding a node from `NodeCard` merges new neighbors without removing the original nodes.
- Selection and pins are preserved across an expand.
- 300-node guard still fires when an expand would breach the limit.

`NodeCard.test.ts`:
- Both buttons render with correct `aria-label`.
- (Click handling is logic-tested via store; no JSX render tests per project convention.)

---

## 3. Full-Band Category Color Coding

### Current
`NodeCard.tsx:77–83` renders a 4 px top stripe `<div>` colored with `catVar`. Header row text uses `text-foreground` / `text-foreground-muted`.

### New
Replace the 4 px stripe with a tinted **header band** that wraps the entire icon+label+action row. Title row stays on `--surface`.

Per-kind band design — band fill uses the category color at full saturation; text uses an automatically legible foreground. The four category colors and their paired foregrounds:

| Kind | `--cat-*` | Band background | Band foreground |
|---|---|---|---|
| Shastra | `#E63946` | `--cat-shastra` | `#FFFFFF` |
| Gatha | `#F4A261` | `--cat-gatha` | `#1A1A1A` (orange isn't dark enough for white) |
| Topic | `#2A9D8F` | `--cat-topic` | `#FFFFFF` |
| Keyword | `#264653` | `--cat-keyword` | `#FFFFFF` |

Extend `NODE_KIND_META` in `NodeCard.tsx` with a `bandFg: string` field. Add the values above.

### Tokenization

Add to `ui/src/styles/theme.css`:

```css
--cat-shastra-fg: #FFFFFF;
--cat-gatha-fg:   #1A1A1A;
--cat-topic-fg:   #FFFFFF;
--cat-keyword-fg: #FFFFFF;
```

…and map them in `globals.css` `@theme inline` so they're consumable as `text-cat-shastra-fg` etc., consistent with existing tokens.

### Selected state interaction

When `selected = true`:
- The selected fill (`--node-bg-selected = --accent #E63946`) already paints the whole card red.
- For non-shastra kinds, the header band is overridden by the accent fill (same as today — selection trumps category). For `shastra` the band color is already the accent — visually identical, no edge case.

### Hover state

No change — hover already lifts shadow and tints border with `--accent` mix. The band stays its category color on hover.

### Accessibility

WCAG AA contrast verified for each pair:
- `#E63946` vs `#FFFFFF` → 4.83:1 ✅
- `#F4A261` vs `#1A1A1A` → 9.92:1 ✅
- `#2A9D8F` vs `#FFFFFF` → 3.61:1 ⚠️ — fails AA for normal text; the band text is `font-semibold` 13 px (`text-sm`) which qualifies as "large text" only when ≥14 px bold. **Action:** bump the band labelHi to `text-[14px] font-semibold` for the Topic kind, or darken `--cat-topic` to `#1D7A6F` (4.5:1). Prefer darkening the token — keeps a uniform type scale.
- `#264653` vs `#FFFFFF` → 9.69:1 ✅

### Tests

Update `components/NodeCard.test.ts` and `styles/theme.test.ts`:
- All four kinds expose `bandFg` in `NODE_KIND_META`.
- New theme tokens `--cat-*-fg` declared with the spec hex values.
- Theme test asserts `--cat-topic` is updated to `#1D7A6F` if we take that route.

---

## Files Touched (summary)

**Backend**
- `services/navigation_service/config.py` — add `LANDING_SEED_KEYWORDS`.
- `services/navigation_service/routers/graph.py` — new `GET /v1/landing/random`.
- `services/navigation_service/tests/test_landing_random.py` — new tests.

**Frontend**
- `ui/src/lib/api/navigation.ts` — add `getNavLandingRandom`.
- `ui/src/app/[locale]/graph/page.tsx` — boot sequence uses random landing.
- `ui/src/lib/graph/graphViewHelpers.ts` — remove `MAX_GRAPH_NODES` cap.
- `ui/src/lib/store/graphStore.ts` — no new action (reuse `expandFromNode`); minor wiring only if needed for the button callback.
- `ui/src/components/NodeCard.tsx` — band layout, expand button, `bandFg`.
- `ui/src/styles/theme.css` + `globals.css` — `--cat-*-fg` tokens; possibly darken `--cat-topic`.
- Tests: `graphViewHelpers.test.ts`, `graphStore.test.ts`, `NodeCard.test.ts`, `theme.test.ts`.

---

## Out of Scope (explicit)

- New layout algorithms (force/hierarchical/radial unchanged; radial still a placeholder).
- Edge color coding / new edge styles.
- Keyboard shortcut wiring for re-root (can be added later — proposed `e` key).
- Backend caching of the random-seed payload — Neo4j is fast enough at depth 2; revisit only if p95 > 300 ms.

---

## Manual Verification Steps

1. `pnpm dev` + all backend services running.
2. Navigate to `/graph` with no query params. Confirm: a different seed keyword renders on each refresh; depth=2 by default; URL is rewritten to include `?node=…`.
3. Change depth stepper to 1, 3, 4 — confirm node count grows monotonically and the layout settles.
4. Click the expand icon on any non-focus node — confirm new neighbors merge into the existing graph (previous nodes stay), pins/selection are preserved, URL is unchanged, and the 300-node guard appears for large expansions.
5. Click the chevron / body — confirm details panel opens, focus does not change.
6. Toggle Shastra / Gatha / Topic / Keyword visibility — confirm bands match the spec colors and text is readable.
7. Select a node — confirm the band is replaced by the accent red fill across all kinds.
8. Lighthouse a11y pass on `/graph` — confirm no new contrast violations.

---

## Open Questions for the User

Please confirm before implementation:

1. **Random seed scope** — only keywords ✅ confirmed
2. **Topic color** — okay to darken `--cat-topic` from `#2A9D8F` to `#1D7A6F` for WCAG AA (pending Phase 3)
3. **Default depth** — keep 2 only ✅ confirmed