import { describe, it, expect } from 'vitest';
import {
  buildCanvasNodes,
  buildCanvasEdges,
  computeHierarchicalPositions,
  computeRadialPositions,
  HIER_LEVEL_HEIGHT,
  HIER_NODE_SPACING,
  HIER_PADDING_TOP,
  RADIAL_FIRST_RING,
  RADIAL_RING_SPACING,
  RADIAL_MIN_ARC,
} from '@/app/[locale]/graph/graphViewHelpers';
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

// ─── buildCanvasNodes ─────────────────────────────────────────────────────────

describe('buildCanvasNodes', () => {
  it('returns all nodes — no cap', () => {
    const nodes: Record<string, GraphNode> = {};
    for (let i = 0; i < 30; i++) nodes[`n${i}`] = makeNode(`n${i}`);

    const result = buildCanvasNodes(nodes, ALL_VISIBLE, null, new Set());
    expect(result).toHaveLength(30);
  });

  it('returns all depth-1 neighbors from a depth-1 fixture', () => {
    // Focus + 5 direct neighbors → all 6 should be returned
    const nodes: Record<string, GraphNode> = {
      focus: makeNode('focus'),
      n1: makeNode('n1'),
      n2: makeNode('n2'),
      n3: makeNode('n3'),
      n4: makeNode('n4'),
      n5: makeNode('n5'),
    };
    const result = buildCanvasNodes(nodes, ALL_VISIBLE, null, new Set());
    expect(result).toHaveLength(6);
    expect(result.map((n) => n.nk)).toContain('focus');
  });

  it('returns the union of depth-1 and depth-2 neighbors from a depth-2 fixture', () => {
    const nodes: Record<string, GraphNode> = {};
    // 3 depth-1 neighbors + 4 depth-2 neighbors + focus = 8
    ['focus', 'd1a', 'd1b', 'd1c', 'd2a', 'd2b', 'd2c', 'd2d'].forEach((nk) => {
      nodes[nk] = makeNode(nk);
    });
    const result = buildCanvasNodes(nodes, ALL_VISIBLE, null, new Set());
    expect(result).toHaveLength(8);
  });

  it('returns fewer nodes when fewer are present', () => {
    const nodes: Record<string, GraphNode> = {
      a: makeNode('a'),
      b: makeNode('b'),
    };
    const result = buildCanvasNodes(nodes, ALL_VISIBLE, null, new Set());
    expect(result).toHaveLength(2);
  });

  it('excludes nodes whose category is toggled off', () => {
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

  it('includes gatha nodes when gatha category is visible', () => {
    const nodes: Record<string, GraphNode> = {
      g1: makeNode('g1', 'gatha'),
      g2: makeNode('g2', 'gatha'),
      t1: makeNode('t1', 'topic'),
    };
    const result = buildCanvasNodes(nodes, ALL_VISIBLE, null, new Set());
    const gathaNodes = result.filter((n) => n.kind === 'gatha');
    expect(gathaNodes).toHaveLength(2);
  });

  it('excludes gatha nodes when gatha category is hidden', () => {
    const nodes: Record<string, GraphNode> = {
      g1: makeNode('g1', 'gatha'),
      t1: makeNode('t1', 'topic'),
    };
    const vis = { ...ALL_VISIBLE, gatha: false };
    const result = buildCanvasNodes(nodes, vis, null, new Set());
    expect(result.every((n) => n.kind !== 'gatha')).toBe(true);
    expect(result).toHaveLength(1);
  });

  it('includes shastra nodes when shastra category is visible', () => {
    const nodes: Record<string, GraphNode> = {
      s1: makeNode('s1', 'shastra'),
      t1: makeNode('t1', 'topic'),
    };
    const result = buildCanvasNodes(nodes, ALL_VISIBLE, null, new Set());
    const shastraNodes = result.filter((n) => n.kind === 'shastra');
    expect(shastraNodes).toHaveLength(1);
  });

  it('excludes shastra nodes when shastra category is hidden', () => {
    const nodes: Record<string, GraphNode> = {
      s1: makeNode('s1', 'shastra'),
      g1: makeNode('g1', 'gatha'),
      t1: makeNode('t1', 'topic'),
    };
    const vis = { ...ALL_VISIBLE, shastra: false };
    const result = buildCanvasNodes(nodes, vis, null, new Set());
    expect(result.every((n) => n.kind !== 'shastra')).toBe(true);
    expect(result).toHaveLength(2);
  });

  it('includes all 4 node kinds when all categories are visible', () => {
    const nodes: Record<string, GraphNode> = {
      s1: makeNode('s1', 'shastra'),
      g1: makeNode('g1', 'gatha'),
      t1: makeNode('t1', 'topic'),
      k1: makeNode('k1', 'keyword'),
    };
    const result = buildCanvasNodes(nodes, ALL_VISIBLE, null, new Set());
    const kinds = new Set(result.map((n) => n.kind));
    expect(kinds).toContain('shastra');
    expect(kinds).toContain('gatha');
    expect(kinds).toContain('topic');
    expect(kinds).toContain('keyword');
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

// ─── buildCanvasEdges — no dangling edges ────────────────────────────────────

describe('buildCanvasEdges', () => {
  it('excludes edges whose source is not in the rendered set', () => {
    const nodes = { a: makeNode('a'), b: makeNode('b'), c: makeNode('c') };
    const edges = { e1: makeEdge('e1', 'a', 'b'), e2: makeEdge('e2', 'c', 'b') };
    // c is in the store but NOT in the rendered set (category hidden)
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
    const nodes = { a: makeNode('a'), b: makeNode('b'), c: makeNode('c') };
    const edges = {
      e1: makeEdge('e1', 'a', 'b'),
      e2: makeEdge('e2', 'b', 'c'),
    };
    const rendered = new Set(['a', 'b', 'c']);
    const result = buildCanvasEdges(edges, nodes, rendered, ALL_VISIBLE, 'e1');
    expect(result.find((e) => e.id === 'e1')!.active).toBe(true);
    expect(result.find((e) => e.id === 'e2')!.active).toBe(false);
  });

  it('deduplicates A→B and B→A edges with the same kind into one rendered edge', () => {
    const nodes = { a: makeNode('a'), b: makeNode('b') };
    const edges = {
      e1: makeEdge('e1', 'a', 'b'),
      e2: makeEdge('e2', 'b', 'a'),
    };
    const rendered = new Set(['a', 'b']);
    const result = buildCanvasEdges(edges, nodes, rendered, ALL_VISIBLE, null);
    expect(result).toHaveLength(1);
  });

  it('marks the representative active when the duplicate direction is selected', () => {
    const nodes = { a: makeNode('a'), b: makeNode('b') };
    const edges = {
      e1: makeEdge('e1', 'a', 'b'),
      e2: makeEdge('e2', 'b', 'a'),
    };
    const rendered = new Set(['a', 'b']);
    // e2 is the duplicate direction — the representative (e1) should still be active
    const result = buildCanvasEdges(edges, nodes, rendered, ALL_VISIBLE, 'e2');
    expect(result).toHaveLength(1);
    expect(result[0].active).toBe(true);
  });

  it('keeps distinct edges between different node pairs', () => {
    const nodes = { a: makeNode('a'), b: makeNode('b'), c: makeNode('c') };
    const edges = {
      e1: makeEdge('e1', 'a', 'b'),
      e2: makeEdge('e2', 'b', 'c'),
      e3: makeEdge('e3', 'a', 'c'),
    };
    const rendered = new Set(['a', 'b', 'c']);
    const result = buildCanvasEdges(edges, nodes, rendered, ALL_VISIBLE, null);
    expect(result).toHaveLength(3);
  });

  it('includes MENTIONS_TOPIC edges between gatha and topic nodes', () => {
    const nodes = {
      g1: makeNode('g1', 'gatha'),
      t1: makeNode('t1', 'topic'),
    };
    const edges: Record<string, GraphEdge> = {
      e1: { id: 'e1', src: 'g1', dst: 't1', kind: 'MENTIONS_TOPIC', weight: 1 },
    };
    const rendered = new Set(['g1', 't1']);
    const result = buildCanvasEdges(edges, nodes, rendered, ALL_VISIBLE, null);
    expect(result).toHaveLength(1);
    expect(result[0].kind).toBe('MENTIONS_TOPIC');
  });

  it('includes IN_SHASTRA edges between gatha and shastra nodes', () => {
    const nodes = {
      g1: makeNode('g1', 'gatha'),
      s1: makeNode('s1', 'shastra'),
    };
    const edges: Record<string, GraphEdge> = {
      e1: { id: 'e1', src: 'g1', dst: 's1', kind: 'IN_SHASTRA', weight: 1 },
    };
    const rendered = new Set(['g1', 's1']);
    const result = buildCanvasEdges(edges, nodes, rendered, ALL_VISIBLE, null);
    expect(result).toHaveLength(1);
    expect(result[0].kind).toBe('IN_SHASTRA');
  });

  it('excludes MENTIONS_TOPIC edge when gatha category is hidden', () => {
    const nodes = {
      g1: makeNode('g1', 'gatha'),
      t1: makeNode('t1', 'topic'),
    };
    const edges: Record<string, GraphEdge> = {
      e1: { id: 'e1', src: 'g1', dst: 't1', kind: 'MENTIONS_TOPIC', weight: 1 },
    };
    const rendered = new Set(['g1', 't1']);
    const vis = { ...ALL_VISIBLE, gatha: false };
    const result = buildCanvasEdges(edges, nodes, rendered, vis, null);
    expect(result).toHaveLength(0);
  });

  it('excludes IN_SHASTRA edge when shastra category is hidden', () => {
    const nodes = {
      g1: makeNode('g1', 'gatha'),
      s1: makeNode('s1', 'shastra'),
    };
    const edges: Record<string, GraphEdge> = {
      e1: { id: 'e1', src: 'g1', dst: 's1', kind: 'IN_SHASTRA', weight: 1 },
    };
    const rendered = new Set(['g1', 's1']);
    const vis = { ...ALL_VISIBLE, shastra: false };
    const result = buildCanvasEdges(edges, nodes, rendered, vis, null);
    expect(result).toHaveLength(0);
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

  it('places unreachable component as its own subtree below the main one', () => {
    // 'isolated' has no edges to the focus node; left as its own component root.
    // Main deepest = 1; disconnected component starts at level 3 (gap of 1 row).
    const nodeNks = ['focus', 'child', 'isolated'];
    const edges = [{ src: 'focus', dst: 'child' }];
    const result = computeHierarchicalPositions(nodeNks, edges, 'focus', W, H);
    expect(result.get('isolated')!.y).toBe(HIER_PADDING_TOP + 3 * HIER_LEVEL_HEIGHT);
  });

  it('lays out a disconnected component using its own BFS rather than flattening it', () => {
    // Two disconnected components: focus↔a, and b↔c↔d (chain).
    const nodeNks = ['focus', 'a', 'b', 'c', 'd'];
    const edges = [
      { src: 'focus', dst: 'a' },
      { src: 'b', dst: 'c' },
      { src: 'c', dst: 'd' },
    ];
    const result = computeHierarchicalPositions(nodeNks, edges, 'focus', W, H);
    // 'c' has highest local degree → local root. b and d are its neighbours.
    const yC = result.get('c')!.y;
    const yB = result.get('b')!.y;
    const yD = result.get('d')!.y;
    expect(yB).toBe(yD);          // siblings on the same row
    expect(yB).toBeGreaterThan(yC); // c is the root of its own subtree
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

  it('places every node at the same BFS depth at the same y, regardless of count', () => {
    // 10 direct neighbors of root → all must share y = level 1, even if x
    // values extend beyond the canvas width.
    const count = 10;
    const neighbors = Array.from({ length: count }, (_, i) => `n${i}`);
    const nodeNks = ['root', ...neighbors];
    const edges = neighbors.map((n) => ({ src: 'root', dst: n }));
    const result = computeHierarchicalPositions(nodeNks, edges, 'root', W, H);

    expect(result.get('root')!.y).toBe(HIER_PADDING_TOP);

    const expectedY = HIER_PADDING_TOP + HIER_LEVEL_HEIGHT;
    for (const n of neighbors) {
      expect(result.get(n)!.y).toBe(expectedY);
    }
  });

  it('keeps same-depth nodes symmetric around the horizontal center even when off-screen', () => {
    const count = 8;
    const neighbors = Array.from({ length: count }, (_, i) => `n${i}`);
    const nodeNks = ['root', ...neighbors];
    const edges = neighbors.map((n) => ({ src: 'root', dst: n }));
    const result = computeHierarchicalPositions(nodeNks, edges, 'root', W, H);
    const xs = neighbors.map((n) => result.get(n)!.x);
    // First and last are equidistant from center
    expect(xs[0] + xs[xs.length - 1]).toBeCloseTo(W);
    // Adjacent spacing
    expect(xs[1] - xs[0]).toBeCloseTo(HIER_NODE_SPACING);
  });

  it('keeps each subsequent BFS depth on its own row at the expected y', () => {
    // Chain: a → b → c → d. Each at depths 0..3.
    const nodeNks = ['a', 'b', 'c', 'd'];
    const edges = [
      { src: 'a', dst: 'b' },
      { src: 'b', dst: 'c' },
      { src: 'c', dst: 'd' },
    ];
    const result = computeHierarchicalPositions(nodeNks, edges, 'a', W, H);
    expect(result.get('a')!.y).toBe(HIER_PADDING_TOP);
    expect(result.get('b')!.y).toBe(HIER_PADDING_TOP + HIER_LEVEL_HEIGHT);
    expect(result.get('c')!.y).toBe(HIER_PADDING_TOP + 2 * HIER_LEVEL_HEIGHT);
    expect(result.get('d')!.y).toBe(HIER_PADDING_TOP + 3 * HIER_LEVEL_HEIGHT);
  });
});

// ─── computeRadialPositions ───────────────────────────────────────────────────

describe('computeRadialPositions', () => {
  const W = 1000;
  const H = 800;

  it('returns an empty map when given no nodes', () => {
    const result = computeRadialPositions([], [], null, W, H);
    expect(result.size).toBe(0);
  });

  it('places the focus node at the canvas centre (W/2, H/2)', () => {
    const result = computeRadialPositions(['focus'], [], 'focus', W, H);
    expect(result.get('focus')!.x).toBeCloseTo(W / 2);
    expect(result.get('focus')!.y).toBeCloseTo(H / 2);
  });

  it('places a single 1-hop neighbour on the level-1 ring at 12-o\'clock', () => {
    const nodeNks = ['focus', 'n1'];
    const edges = [{ src: 'focus', dst: 'n1' }];
    const result = computeRadialPositions(nodeNks, edges, 'focus', W, H);
    expect(result.get('n1')!.x).toBeCloseTo(W / 2);
    expect(result.get('n1')!.y).toBeCloseTo(H / 2 - RADIAL_FIRST_RING);
  });

  it('two 1-hop neighbours are diametrically opposite — sum of x ≈ W, sum of y ≈ H', () => {
    const nodeNks = ['focus', 'a', 'b'];
    const edges = [{ src: 'focus', dst: 'a' }, { src: 'focus', dst: 'b' }];
    const result = computeRadialPositions(nodeNks, edges, 'focus', W, H);
    const ax = result.get('a')!.x;
    const bx = result.get('b')!.x;
    const ay = result.get('a')!.y;
    const by = result.get('b')!.y;
    expect(ax + bx).toBeCloseTo(W);
    expect(ay + by).toBeCloseTo(H);
  });

  it('all same-level nodes share the same euclidean distance to centre (within ε)', () => {
    const count = 6;
    const neighbors = Array.from({ length: count }, (_, i) => `n${i}`);
    const nodeNks = ['focus', ...neighbors];
    const edges = neighbors.map(n => ({ src: 'focus', dst: n }));
    const result = computeRadialPositions(nodeNks, edges, 'focus', W, H);
    const cx = W / 2;
    const cy = H / 2;
    const dists = neighbors.map(n => {
      const p = result.get(n)!;
      return Math.sqrt((p.x - cx) ** 2 + (p.y - cy) ** 2);
    });
    const first = dists[0];
    for (const d of dists) {
      expect(d).toBeCloseTo(first, 5);
    }
  });

  it('a 2-hop chain a→b→c puts c on the level-2 ring', () => {
    const nodeNks = ['a', 'b', 'c'];
    const edges = [{ src: 'a', dst: 'b' }, { src: 'b', dst: 'c' }];
    const result = computeRadialPositions(nodeNks, edges, 'a', W, H);
    const cx = W / 2;
    const cy = H / 2;
    const p = result.get('c')!;
    const dist = Math.sqrt((p.x - cx) ** 2 + (p.y - cy) ** 2);
    expect(dist).toBeCloseTo(RADIAL_FIRST_RING + RADIAL_RING_SPACING, 5);
  });

  it('unreachable nodes go on the ring one past the deepest reachable level', () => {
    const nodeNks = ['focus', 'child', 'isolated'];
    const edges = [{ src: 'focus', dst: 'child' }];
    const result = computeRadialPositions(nodeNks, edges, 'focus', W, H);
    // deepest reachable = 1 (child), so isolated goes to level 2
    const cx = W / 2;
    const cy = H / 2;
    const p = result.get('isolated')!;
    const dist = Math.sqrt((p.x - cx) ** 2 + (p.y - cy) ** 2);
    expect(dist).toBeCloseTo(RADIAL_FIRST_RING + RADIAL_RING_SPACING, 5);
  });

  it('falls back to the first node as focus when focusNk is null', () => {
    const nodeNks = ['x', 'y'];
    const edges = [{ src: 'x', dst: 'y' }];
    const result = computeRadialPositions(nodeNks, edges, null, W, H);
    expect(result.get('x')!.x).toBeCloseTo(W / 2);
    expect(result.get('x')!.y).toBeCloseTo(H / 2);
  });

  it('falls back to the first node when focusNk is not in the node list', () => {
    const nodeNks = ['a', 'b'];
    const edges = [{ src: 'a', dst: 'b' }];
    const result = computeRadialPositions(nodeNks, edges, 'nonexistent', W, H);
    expect(result.get('a')!.x).toBeCloseTo(W / 2);
    expect(result.get('a')!.y).toBeCloseTo(H / 2);
  });

  it('treats edges as bidirectional (focus reachable from a child-direction edge)', () => {
    // Edge goes b→a but focus is 'a', so 'b' should still be on level-1 ring
    const nodeNks = ['a', 'b'];
    const edges = [{ src: 'b', dst: 'a' }];
    const result = computeRadialPositions(nodeNks, edges, 'a', W, H);
    const cx = W / 2;
    const cy = H / 2;
    const p = result.get('b')!;
    const dist = Math.sqrt((p.x - cx) ** 2 + (p.y - cy) ** 2);
    expect(dist).toBeCloseTo(RADIAL_FIRST_RING, 5);
  });

  it('RADIAL_MIN_ARC clamp: 12 same-level siblings expand ring beyond RADIAL_FIRST_RING; all share same radius', () => {
    const count = 12;
    const neighbors = Array.from({ length: count }, (_, i) => `n${i}`);
    const nodeNks = ['focus', ...neighbors];
    const edges = neighbors.map(n => ({ src: 'focus', dst: n }));
    const result = computeRadialPositions(nodeNks, edges, 'focus', W, H);
    const cx = W / 2;
    const cy = H / 2;
    const dists = neighbors.map(n => {
      const p = result.get(n)!;
      return Math.sqrt((p.x - cx) ** 2 + (p.y - cy) ** 2);
    });
    // Minimum required radius for 12 nodes at RADIAL_MIN_ARC spacing
    const minR = (count * RADIAL_MIN_ARC) / (2 * Math.PI);
    // Ring must be at least minR (clamped) and beyond RADIAL_FIRST_RING in this case
    expect(dists[0]).toBeGreaterThanOrEqual(minR - 0.01);
    // All nodes share the same radius
    for (const d of dists) {
      expect(d).toBeCloseTo(dists[0], 5);
    }
  });

  it('all exported constants are positive numbers', () => {
    expect(RADIAL_FIRST_RING).toBeGreaterThan(0);
    expect(RADIAL_RING_SPACING).toBeGreaterThan(0);
    expect(RADIAL_MIN_ARC).toBeGreaterThan(0);
  });
});
