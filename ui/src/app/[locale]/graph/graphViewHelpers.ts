import type { GraphNode, GraphEdge, EntityKind, EdgeKind } from '@/lib/types';

// ─── Hierarchical layout constants (exported for tests) ───────────────────────

/** Vertical distance (px) between BFS depth levels in hierarchical mode. */
export const HIER_LEVEL_HEIGHT = 240;
/** Horizontal gap (px) between nodes within the same BFS level. */
export const HIER_NODE_SPACING = 320;
/** Top padding (px) before the first level row. */
export const HIER_PADDING_TOP = 120;

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

  // Unreachable nodes go one row past the deepest reachable node
  const maxReachable = level.size > 0 ? Math.max(...level.values()) : 0;
  for (const nk of nodeNks) {
    if (!level.has(nk)) level.set(nk, maxReachable + 1);
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
