import type { GraphNode, GraphEdge, EntityKind, EdgeKind } from '@/lib/types';

export const MAX_GRAPH_NODES = 20;

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
 * Returns at most `limit` visible nodes, mapped to canvas shape.
 * Nodes with hidden categories are excluded before the slice, so the
 * limit always applies to what is actually rendered.
 */
export function buildCanvasNodes(
  nodes: Record<string, GraphNode>,
  categoryVisibility: Record<EntityKind, boolean>,
  selectedNodeId: string | null,
  pinned: Set<string>,
  limit = MAX_GRAPH_NODES,
): RenderedNode[] {
  return Object.values(nodes)
    .filter((n) => categoryVisibility[n.kind])
    .slice(0, limit)
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
 * Returns only edges where both endpoints are in `renderedNks` AND
 * both categories are visible.  Edges that reference nodes outside the
 * rendered set would produce dangling lines in the force simulation.
 */
export function buildCanvasEdges(
  edges: Record<string, GraphEdge>,
  nodes: Record<string, GraphNode>,
  renderedNks: Set<string>,
  categoryVisibility: Record<EntityKind, boolean>,
  selectedEdgeId: string | null,
): RenderedEdge[] {
  return Object.values(edges)
    .filter(
      (e) =>
        renderedNks.has(e.src) &&
        renderedNks.has(e.dst) &&
        categoryVisibility[nodes[e.src]?.kind ?? 'topic'] &&
        categoryVisibility[nodes[e.dst]?.kind ?? 'topic'],
    )
    .map((e) => ({
      id: e.id,
      src: e.src,
      dst: e.dst,
      kind: e.kind,
      active: e.id === selectedEdgeId,
    }));
}
