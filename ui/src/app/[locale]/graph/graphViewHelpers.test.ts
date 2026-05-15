import { describe, it, expect } from 'vitest';
import {
  MAX_GRAPH_NODES,
  buildCanvasNodes,
  buildCanvasEdges,
  computeHierarchicalPositions,
  HIER_LEVEL_HEIGHT,
  HIER_NODE_SPACING,
  HIER_PADDING_TOP,
} from './graphViewHelpers';
import type { GraphNode, GraphEdge, EntityKind } from '@/lib/types';

// ─── Fixtures ─────────────────────────────────────────────────────────────────

const ALL_VISIBLE: Record<EntityKind, boolean> = {
  shastra: true,
  gatha: true,
  topic: true,
  keyword: true,
};

function makeNode(nk: string, kind: EntityKind = 'topic'): GraphNode {
  return { nk, kind, title_hi: `${nk}-hi`, title_en: `${nk}-en`, degree: 1 };
}

function makeEdge(id: string, src: string, dst: string): GraphEdge {
  return { id, src, dst, kind: 'RELATED_TO', weight: 1 };
}

// ─── Bug 1a: MAX_GRAPH_NODES constant ─────────────────────────────────────────

describe('MAX_GRAPH_NODES', () => {
  it('is 20', () => {
    expect(MAX_GRAPH_NODES).toBe(20);
  });
});

// ─── Bug 1b: buildCanvasNodes — node limit ────────────────────────────────────

describe('buildCanvasNodes', () => {
  it('returns at most MAX_GRAPH_NODES nodes when the store has more', () => {
    const nodes: Record<string, GraphNode> = {};
    for (let i = 0; i < 30; i++) nodes[`n${i}`] = makeNode(`n${i}`);

    const result = buildCanvasNodes(nodes, ALL_VISIBLE, null, new Set());
    expect(result).toHaveLength(MAX_GRAPH_NODES);
  });

  it('returns fewer than MAX_GRAPH_NODES when fewer nodes are present', () => {
    const nodes: Record<string, GraphNode> = {
      a: makeNode('a'),
      b: makeNode('b'),
    };
    const result = buildCanvasNodes(nodes, ALL_VISIBLE, null, new Set());
    expect(result).toHaveLength(2);
  });

  it('respects a custom limit passed as the fifth argument', () => {
    const nodes: Record<string, GraphNode> = {};
    for (let i = 0; i < 10; i++) nodes[`n${i}`] = makeNode(`n${i}`);

    expect(buildCanvasNodes(nodes, ALL_VISIBLE, null, new Set(), 5)).toHaveLength(5);
    expect(buildCanvasNodes(nodes, ALL_VISIBLE, null, new Set(), 3)).toHaveLength(3);
  });

  it('excludes nodes whose category is toggled off before slicing', () => {
    const nodes: Record<string, GraphNode> = {
      t1: makeNode('t1', 'topic'),
      k1: makeNode('k1', 'keyword'),
      k2: makeNode('k2', 'keyword'),
    };
    const vis = { ...ALL_VISIBLE, keyword: false };
    const result = buildCanvasNodes(nodes, vis, null, new Set());
    expect(result.every((n) => n.kind === 'topic')).toBe(true);
    expect(result).toHaveLength(1);
  });

  it('marks the selected node', () => {
    const nodes = { a: makeNode('a'), b: makeNode('b') };
    const result = buildCanvasNodes(nodes, ALL_VISIBLE, 'a', new Set());
    expect(result.find((n) => n.nk === 'a')!.selected).toBe(true);
    expect(result.find((n) => n.nk === 'b')!.selected).toBe(false);
  });

  it('marks pinned nodes', () => {
    const nodes = { a: makeNode('a'), b: makeNode('b') };
    const result = buildCanvasNodes(nodes, ALL_VISIBLE, null, new Set(['b']));
    expect(result.find((n) => n.nk === 'a')!.pinned).toBe(false);
    expect(result.find((n) => n.nk === 'b')!.pinned).toBe(true);
  });
});

// ─── Bug 1c: buildCanvasEdges — no dangling edges ────────────────────────────

describe('buildCanvasEdges', () => {
  it('excludes edges whose source is not in the rendered set', () => {
    const nodes = { a: makeNode('a'), b: makeNode('b'), c: makeNode('c') };
    const edges = { e1: makeEdge('e1', 'a', 'b'), e2: makeEdge('e2', 'c', 'b') };
    // c is in the store but NOT in the rendered set (beyond the 20-node slice)
    const rendered = new Set(['a', 'b']);
    const result = buildCanvasEdges(edges, nodes, rendered, ALL_VISIBLE, null);
    expect(result.map((e) => e.id)).toEqual(['e1']);
  });

  it('excludes edges whose destination is not in the rendered set', () => {
    const nodes = { a: makeNode('a'), b: makeNode('b'), c: makeNode('c') };
    const edges = { e1: makeEdge('e1', 'a', 'b'), e2: makeEdge('e2', 'a', 'c') };
    const rendered = new Set(['a', 'b']);
    const result = buildCanvasEdges(edges, nodes, rendered, ALL_VISIBLE, null);
    expect(result.map((e) => e.id)).toEqual(['e1']);
  });

  it('includes all edges when both endpoints are rendered', () => {
    const nodes = { a: makeNode('a'), b: makeNode('b'), c: makeNode('c') };
    const edges = {
      e1: makeEdge('e1', 'a', 'b'),
      e2: makeEdge('e2', 'b', 'c'),
    };
    const rendered = new Set(['a', 'b', 'c']);
    const result = buildCanvasEdges(edges, nodes, rendered, ALL_VISIBLE, null);
    expect(result).toHaveLength(2);
  });

  it('excludes edges where either node category is hidden', () => {
    const nodes = {
      a: makeNode('a', 'topic'),
      b: makeNode('b', 'keyword'),
    };
    const edges = { e1: makeEdge('e1', 'a', 'b') };
    const rendered = new Set(['a', 'b']);
    const vis = { ...ALL_VISIBLE, keyword: false };
    const result = buildCanvasEdges(edges, nodes, rendered, vis, null);
    expect(result).toHaveLength(0);
  });

  it('marks the active edge', () => {
    const nodes = { a: makeNode('a'), b: makeNode('b') };
    const edges = {
      e1: makeEdge('e1', 'a', 'b'),
      e2: makeEdge('e2', 'b', 'a'),
    };
    const rendered = new Set(['a', 'b']);
    const result = buildCanvasEdges(edges, nodes, rendered, ALL_VISIBLE, 'e1');
    expect(result.find((e) => e.id === 'e1')!.active).toBe(true);
    expect(result.find((e) => e.id === 'e2')!.active).toBe(false);
  });
});

// ─── computeHierarchicalPositions ─────────────────────────────────────────────

describe('computeHierarchicalPositions', () => {
  const W = 1000;
  const H = 800;

  it('returns an empty map when given no nodes', () => {
    const result = computeHierarchicalPositions([], [], null, W, H);
    expect(result.size).toBe(0);
  });

  it('places the focus node at depth 0 (top row)', () => {
    const nodeNks = ['a', 'b', 'c'];
    const edges = [{ src: 'a', dst: 'b' }, { src: 'b', dst: 'c' }];
    const result = computeHierarchicalPositions(nodeNks, edges, 'a', W, H);
    expect(result.get('a')!.y).toBe(HIER_PADDING_TOP);
  });

  it('places 1-hop neighbors one level below the focus node', () => {
    const nodeNks = ['a', 'b'];
    const edges = [{ src: 'a', dst: 'b' }];
    const result = computeHierarchicalPositions(nodeNks, edges, 'a', W, H);
    expect(result.get('b')!.y).toBe(HIER_PADDING_TOP + HIER_LEVEL_HEIGHT);
  });

  it('places 2-hop neighbors two levels below the focus node', () => {
    const nodeNks = ['a', 'b', 'c'];
    const edges = [{ src: 'a', dst: 'b' }, { src: 'b', dst: 'c' }];
    const result = computeHierarchicalPositions(nodeNks, edges, 'a', W, H);
    expect(result.get('c')!.y).toBe(HIER_PADDING_TOP + 2 * HIER_LEVEL_HEIGHT);
  });

  it('centers a single node in each row horizontally', () => {
    const nodeNks = ['root'];
    const result = computeHierarchicalPositions(nodeNks, [], 'root', W, H);
    expect(result.get('root')!.x).toBe(W / 2);
  });

  it('spreads two same-level nodes symmetrically around the center', () => {
    // b and c are both 1-hop from a, so they share level 1
    const nodeNks = ['a', 'b', 'c'];
    const edges = [{ src: 'a', dst: 'b' }, { src: 'a', dst: 'c' }];
    const result = computeHierarchicalPositions(nodeNks, edges, 'a', W, H);
    const xB = result.get('b')!.x;
    const xC = result.get('c')!.x;
    // The two nodes should be symmetric around W/2
    expect(xB + xC).toBeCloseTo(W);
    // And separated by HIER_NODE_SPACING
    expect(Math.abs(xB - xC)).toBeCloseTo(HIER_NODE_SPACING);
  });

  it('assigns unreachable nodes one row past the deepest reachable level', () => {
    // 'isolated' has no edges to the focus node
    const nodeNks = ['focus', 'child', 'isolated'];
    const edges = [{ src: 'focus', dst: 'child' }];
    const result = computeHierarchicalPositions(nodeNks, edges, 'focus', W, H);
    // deepest reachable = 1 (child), so isolated → level 2
    expect(result.get('isolated')!.y).toBe(HIER_PADDING_TOP + 2 * HIER_LEVEL_HEIGHT);
  });

  it('falls back to the first node as root when focusNk is null', () => {
    const nodeNks = ['x', 'y'];
    const edges = [{ src: 'x', dst: 'y' }];
    const result = computeHierarchicalPositions(nodeNks, edges, null, W, H);
    // 'x' (first) should be at depth 0
    expect(result.get('x')!.y).toBe(HIER_PADDING_TOP);
    expect(result.get('y')!.y).toBe(HIER_PADDING_TOP + HIER_LEVEL_HEIGHT);
  });

  it('falls back to the first node when focusNk is not in the node list', () => {
    const nodeNks = ['a', 'b'];
    const edges = [{ src: 'a', dst: 'b' }];
    const result = computeHierarchicalPositions(nodeNks, edges, 'nonexistent', W, H);
    expect(result.get('a')!.y).toBe(HIER_PADDING_TOP);
  });

  it('returns a position for every node in the input', () => {
    const nodeNks = ['a', 'b', 'c', 'd'];
    const edges = [{ src: 'a', dst: 'b' }, { src: 'b', dst: 'c' }];
    const result = computeHierarchicalPositions(nodeNks, edges, 'a', W, H);
    for (const nk of nodeNks) {
      expect(result.has(nk)).toBe(true);
    }
  });

  it('treats edges as bidirectional (child can be the BFS start)', () => {
    // Edge goes b→a but focus is 'a', so 'b' should still be reachable
    const nodeNks = ['a', 'b'];
    const edges = [{ src: 'b', dst: 'a' }];
    const result = computeHierarchicalPositions(nodeNks, edges, 'a', W, H);
    expect(result.get('b')!.y).toBe(HIER_PADDING_TOP + HIER_LEVEL_HEIGHT);
  });
});
