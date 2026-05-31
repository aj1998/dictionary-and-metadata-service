import type { GraphNode, GraphEdge, EntityKind, EdgeKind } from '@/lib/types';

// ─── Hierarchical layout constants (exported for tests) ───────────────────────

/** Vertical distance (px) between BFS depth levels in hierarchical mode. */
export const HIER_LEVEL_HEIGHT = 240;
/** Horizontal gap (px) between nodes within the same BFS level. */
export const HIER_NODE_SPACING = 320;
/** Top padding (px) before the first level row. */
export const HIER_PADDING_TOP = 120;

// ─── Radial layout constants (exported for tests) ─────────────────────────────

/** Radius (px) of the level-1 ring around the focus node. */
export const RADIAL_FIRST_RING = 300;
/** Additional radius (px) per BFS depth beyond level 1. */
export const RADIAL_RING_SPACING = 300;
/** Minimum arc length (px) between adjacent same-ring nodes — prevents card overlap. */
export const RADIAL_MIN_ARC = 256;

export interface RenderedNode {
  nk: string;
  kind: EntityKind;
  titleHi: string;
  titleEn?: string;
  selected: boolean;
  pinned: boolean;
}

export interface RenderedEdge {
  id: string;
  src: string;
  dst: string;
  kind: EdgeKind;
  active: boolean;
}

/**
 * Returns all visible nodes mapped to canvas shape.
 * Nodes with hidden categories are excluded.
 */
export function buildCanvasNodes(
  nodes: Record<string, GraphNode>,
  categoryVisibility: Record<EntityKind, boolean>,
  selectedNodeId: string | null,
  pinned: Set<string>,
): RenderedNode[] {
  return Object.values(nodes)
    .filter((n) => categoryVisibility[n.kind])
    .map((n) => ({
      nk: n.nk,
      kind: n.kind,
      titleHi: n.title_hi,
      titleEn: n.title_en,
      selected: n.nk === selectedNodeId,
      pinned: pinned.has(n.nk),
    }));
}

/**
 * Computes hierarchical node positions using BFS depth from `focusNk`.
 * The focus node is at the top (depth 0); each hop adds one row below.
 * Nodes at the same depth are spread evenly around the horizontal center.
 * Nodes unreachable from focusNk are placed one row below the deepest
 * reachable level. Traversal treats all edges as bidirectional.
 */
export function computeHierarchicalPositions(
  nodeNks: string[],
  edges: Array<{ src: string; dst: string }>,
  focusNk: string | null,
  canvasW: number,
  canvasH: number,
): Map<string, { x: number; y: number }> {
  if (nodeNks.length === 0) return new Map();

  const startNk = focusNk && nodeNks.includes(focusNk) ? focusNk : nodeNks[0];

  // Build bidirectional adjacency list restricted to rendered nodes
  const nkSet = new Set(nodeNks);
  const adj = new Map<string, string[]>();
  for (const nk of nodeNks) adj.set(nk, []);
  for (const e of edges) {
    if (nkSet.has(e.src) && nkSet.has(e.dst)) {
      adj.get(e.src)!.push(e.dst);
      adj.get(e.dst)!.push(e.src);
    }
  }

  // BFS to assign depth levels
  const level = new Map<string, number>();
  level.set(startNk, 0);
  const queue: string[] = [startNk];
  let qi = 0;
  while (qi < queue.length) {
    const cur = queue[qi++];
    const curLevel = level.get(cur)!;
    for (const neighbor of adj.get(cur) ?? []) {
      if (!level.has(neighbor)) {
        level.set(neighbor, curLevel + 1);
        queue.push(neighbor);
      }
    }
  }

  // Unreachable nodes: run BFS within each remaining connected component
  // from a local root (highest local degree). Stack each component as its
  // own subtree below the main one, separated by one extra level of spacing.
  let nextBaseLevel = (level.size > 0 ? Math.max(...level.values()) : 0) + 2;
  for (const nk of nodeNks) {
    if (level.has(nk)) continue;
    // Collect this component
    const componentNks: string[] = [];
    const stack = [nk];
    const seenInComponent = new Set<string>([nk]);
    while (stack.length) {
      const cur = stack.pop()!;
      componentNks.push(cur);
      for (const neighbor of adj.get(cur) ?? []) {
        if (!level.has(neighbor) && !seenInComponent.has(neighbor)) {
          seenInComponent.add(neighbor);
          stack.push(neighbor);
        }
      }
    }
    // Pick local root = highest-degree node in this component
    let localRoot = componentNks[0];
    let bestDegree = -1;
    for (const cnk of componentNks) {
      const deg = (adj.get(cnk) ?? []).length;
      if (deg > bestDegree) { bestDegree = deg; localRoot = cnk; }
    }
    // BFS within component to assign relative depths, offset by nextBaseLevel
    level.set(localRoot, nextBaseLevel);
    const localQueue: string[] = [localRoot];
    let lqi = 0;
    let localMax = nextBaseLevel;
    while (lqi < localQueue.length) {
      const cur = localQueue[lqi++];
      const curLevel = level.get(cur)!;
      for (const neighbor of adj.get(cur) ?? []) {
        if (!level.has(neighbor) && seenInComponent.has(neighbor)) {
          const nl = curLevel + 1;
          level.set(neighbor, nl);
          if (nl > localMax) localMax = nl;
          localQueue.push(neighbor);
        }
      }
    }
    nextBaseLevel = localMax + 2;
  }

  // Group nks by level
  const byLevel = new Map<number, string[]>();
  for (const [nk, lv] of level) {
    if (!byLevel.has(lv)) byLevel.set(lv, []);
    byLevel.get(lv)!.push(nk);
  }

  // Place every node at a given BFS depth on a single horizontal row so that
  // same-depth siblings share the same y, even if the row extends beyond the
  // visible canvas (pan/zoom is expected). Rows are centered on canvasW/2.
  const cx = canvasW / 2;
  const result = new Map<string, { x: number; y: number }>();

  for (const [lv, nks] of [...byLevel.entries()].sort((a, b) => a[0] - b[0])) {
    const y = HIER_PADDING_TOP + lv * HIER_LEVEL_HEIGHT;
    for (let i = 0; i < nks.length; i++) {
      const x = cx + (i - (nks.length - 1) / 2) * HIER_NODE_SPACING;
      result.set(nks[i], { x, y });
    }
  }

  return result;
}

/**
 * Computes radial node positions using BFS depth from `focusNk`.
 * The focus node sits at the canvas centre; each BFS ring is a concentric
 * circle at radius RADIAL_FIRST_RING + (level-1) * RADIAL_RING_SPACING.
 * When a ring's arc per node falls below RADIAL_MIN_ARC, the ring radius
 * is expanded so nodes stay visually separated.
 * Unreachable nodes are placed one ring past the deepest reachable level.
 */
export function computeRadialPositions(
  nodeNks: string[],
  edges: Array<{ src: string; dst: string }>,
  focusNk: string | null,
  canvasW: number,
  canvasH: number,
): Map<string, { x: number; y: number }> {
  if (nodeNks.length === 0) return new Map();

  const startNk = focusNk && nodeNks.includes(focusNk) ? focusNk : nodeNks[0];

  // Build bidirectional adjacency list restricted to rendered nodes
  const nkSet = new Set(nodeNks);
  const adj = new Map<string, string[]>();
  for (const nk of nodeNks) adj.set(nk, []);
  for (const e of edges) {
    if (nkSet.has(e.src) && nkSet.has(e.dst)) {
      adj.get(e.src)!.push(e.dst);
      adj.get(e.dst)!.push(e.src);
    }
  }

  // BFS to assign depth levels
  const level = new Map<string, number>();
  level.set(startNk, 0);
  const queue: string[] = [startNk];
  let qi = 0;
  while (qi < queue.length) {
    const cur = queue[qi++];
    const curLevel = level.get(cur)!;
    for (const neighbor of adj.get(cur) ?? []) {
      if (!level.has(neighbor)) {
        level.set(neighbor, curLevel + 1);
        queue.push(neighbor);
      }
    }
  }

  // Unreachable nodes: BFS within each remaining connected component from a
  // local root (highest-degree). Stack each as additional outer rings so
  // disconnected subtrees retain shape instead of flattening into one ring.
  let nextBaseLevel = (level.size > 0 ? Math.max(...level.values()) : 0) + 1;
  for (const nk of nodeNks) {
    if (level.has(nk)) continue;
    const componentNks: string[] = [];
    const stack = [nk];
    const seenInComponent = new Set<string>([nk]);
    while (stack.length) {
      const cur = stack.pop()!;
      componentNks.push(cur);
      for (const neighbor of adj.get(cur) ?? []) {
        if (!level.has(neighbor) && !seenInComponent.has(neighbor)) {
          seenInComponent.add(neighbor);
          stack.push(neighbor);
        }
      }
    }
    let localRoot = componentNks[0];
    let bestDegree = -1;
    for (const cnk of componentNks) {
      const deg = (adj.get(cnk) ?? []).length;
      if (deg > bestDegree) { bestDegree = deg; localRoot = cnk; }
    }
    level.set(localRoot, nextBaseLevel);
    const localQueue: string[] = [localRoot];
    let lqi = 0;
    let localMax = nextBaseLevel;
    while (lqi < localQueue.length) {
      const cur = localQueue[lqi++];
      const curLevel = level.get(cur)!;
      for (const neighbor of adj.get(cur) ?? []) {
        if (!level.has(neighbor) && seenInComponent.has(neighbor)) {
          const nl = curLevel + 1;
          level.set(neighbor, nl);
          if (nl > localMax) localMax = nl;
          localQueue.push(neighbor);
        }
      }
    }
    nextBaseLevel = localMax + 1;
  }

  // Group nks by level, preserving BFS insertion order
  const byLevel = new Map<number, string[]>();
  for (const [nk, lv] of level) {
    if (!byLevel.has(lv)) byLevel.set(lv, []);
    byLevel.get(lv)!.push(nk);
  }

  const cx = canvasW / 2;
  const cy = canvasH / 2;
  const THETA_START = -Math.PI / 2; // 12-o'clock start position
  const result = new Map<string, { x: number; y: number }>();

  for (const [lv, nks] of byLevel.entries()) {
    if (lv === 0) {
      result.set(nks[0], { x: cx, y: cy });
      continue;
    }

    const baseR = RADIAL_FIRST_RING + (lv - 1) * RADIAL_RING_SPACING;
    const minR = (nks.length * RADIAL_MIN_ARC) / (2 * Math.PI);
    const r = Math.max(baseR, minR);

    const n = nks.length;
    const dTheta = (2 * Math.PI) / n;
    for (let i = 0; i < n; i++) {
      const theta = THETA_START + i * dTheta;
      result.set(nks[i], {
        x: cx + r * Math.cos(theta),
        y: cy + r * Math.sin(theta),
      });
    }
  }

  return result;
}

/**
 * Resolves horizontal overlap between existing same-row nodes and a newly
 * placed children band on a hierarchical row.
 *
 * Existing nodes whose x falls inside (or within `spacing` of) the reserved
 * band [bandLeft, bandRight] are pushed horizontally outward — left of the
 * band's centre go further left, right of centre go further right. Cascading
 * shifts preserve at least `spacing` between same-row siblings.
 *
 * Returns a Map of nk → new x for every existing node that needs to move.
 * Nodes that don't need to move are absent from the map.
 */
export function resolveHierRowCollisions(
  existingSameRow: Array<{ nk: string; x: number }>,
  bandLeft: number,
  bandRight: number,
  bandCenterX: number,
  spacing: number = HIER_NODE_SPACING,
): Map<string, number> {
  const shifts = new Map<string, number>();

  const leftSide = existingSameRow
    .filter(e => e.x < bandCenterX)
    .sort((a, b) => b.x - a.x); // closest to band first
  const rightSide = existingSameRow
    .filter(e => e.x >= bandCenterX)
    .sort((a, b) => a.x - b.x); // closest to band first

  let leftFrontier = bandLeft;
  for (const e of leftSide) {
    const maxAllowed = leftFrontier - spacing;
    if (e.x > maxAllowed) {
      shifts.set(e.nk, maxAllowed);
      leftFrontier = maxAllowed;
    } else {
      leftFrontier = e.x;
    }
  }

  let rightFrontier = bandRight;
  for (const e of rightSide) {
    const minAllowed = rightFrontier + spacing;
    if (e.x < minAllowed) {
      shifts.set(e.nk, minAllowed);
      rightFrontier = minAllowed;
    } else {
      rightFrontier = e.x;
    }
  }

  return shifts;
}

/**
 * Pushes existing nodes radially outward from `pivot` when they fall inside a
 * disc of radius `discR` centred on `pivot`. The angular position relative to
 * pivot is preserved; only the distance is increased to `discR + clearance`.
 *
 * Used when a radial incremental expand fans children around the expander —
 * any previously-placed node sitting inside that fan disc is pushed out so
 * the new children don't overlap them.
 */
export function resolveRadialDiscCollisions(
  existing: Array<{ nk: string; x: number; y: number }>,
  pivot: { x: number; y: number },
  discR: number,
  clearance: number,
): Map<string, { x: number; y: number }> {
  const shifts = new Map<string, { x: number; y: number }>();
  for (const e of existing) {
    const dx = e.x - pivot.x;
    const dy = e.y - pivot.y;
    const d = Math.sqrt(dx * dx + dy * dy);
    if (d >= discR) continue;
    const angle = d < 1e-6 ? 0 : Math.atan2(dy, dx);
    const newR = discR + clearance;
    shifts.set(e.nk, {
      x: pivot.x + Math.cos(angle) * newR,
      y: pivot.y + Math.sin(angle) * newR,
    });
  }
  return shifts;
}

/**
 * Returns only edges where both endpoints are in `renderedNks` AND
 * both categories are visible.  Edges that reference nodes outside the
 * rendered set would produce dangling lines in the force simulation.
 *
 * Bidirectional duplicates (A→B and B→A with the same kind) are collapsed
 * into a single rendered edge — the backend sometimes returns both directions
 * of the same relationship, which would otherwise draw overlapping lines.
 * If either direction's ID matches `selectedEdgeId`, the representative edge
 * is marked active.
 */
export function buildCanvasEdges(
  edges: Record<string, GraphEdge>,
  nodes: Record<string, GraphNode>,
  renderedNks: Set<string>,
  categoryVisibility: Record<EntityKind, boolean>,
  selectedEdgeId: string | null,
): RenderedEdge[] {
  const filtered = Object.values(edges).filter(
    (e) =>
      renderedNks.has(e.src) &&
      renderedNks.has(e.dst) &&
      categoryVisibility[nodes[e.src]?.kind ?? 'topic'] &&
      categoryVisibility[nodes[e.dst]?.kind ?? 'topic'],
  );

  // Deduplicate: treat {A→B, kind} and {B→A, kind} as the same visual edge.
  // Keep the first-seen representative; mark it active if either direction is selected.
  const seen = new Map<string, { edge: GraphEdge; active: boolean }>();
  for (const e of filtered) {
    const [a, b] = e.src < e.dst ? [e.src, e.dst] : [e.dst, e.src];
    const key = `${a}\x00${b}\x00${e.kind}`;
    const isActive = e.id === selectedEdgeId;
    if (!seen.has(key)) {
      seen.set(key, { edge: e, active: isActive });
    } else if (isActive) {
      seen.get(key)!.active = true;
    }
  }

  return Array.from(seen.values()).map(({ edge: e, active }) => ({
    id: e.id,
    src: e.src,
    dst: e.dst,
    kind: e.kind,
    active,
  }));
}
