import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useGraphStore } from './graphStore';
import type { GraphPayload } from '@/lib/types';

vi.mock('@/lib/api/navigation', () => ({
  expandNode: vi.fn(),
}));

const { expandNode } = await import('@/lib/api/navigation');

const payload: GraphPayload = {
  focus_nk: 'n1',
  depth: 2,
  nodes: [
    { nk: 'n1', kind: 'topic', title_hi: 'एक', degree: 1 },
    { nk: 'n2', kind: 'keyword', title_hi: 'दो', degree: 1 },
  ],
  edges: [
    { id: 'e1', src: 'n1', dst: 'n2', kind: 'RELATED_TO', weight: 1 },
  ],
};

describe('useGraphStore', () => {
  beforeEach(() => {
    useGraphStore.getState().reset();
    vi.clearAllMocks();
  });

  it('seedFromPayload merges nodes/edges and sets selected node', () => {
    useGraphStore.getState().seedFromPayload(payload, 'n1');
    const state = useGraphStore.getState();
    expect(Object.keys(state.nodes)).toEqual(['n1', 'n2']);
    expect(Object.keys(state.edges)).toEqual(['e1']);
    expect(state.selected).toEqual({ kind: 'node', id: 'n1' });
  });

  it('togglePin toggles set membership', () => {
    useGraphStore.getState().togglePin('n1');
    expect(useGraphStore.getState().pinned.has('n1')).toBe(true);
    useGraphStore.getState().togglePin('n1');
    expect(useGraphStore.getState().pinned.has('n1')).toBe(false);
  });

  it('expandFromNode de-dupes by nk/id and marks node expanded', async () => {
    vi.mocked(expandNode).mockResolvedValueOnce(payload);
    await useGraphStore.getState().expandFromNode('n1', 2);
    await useGraphStore.getState().expandFromNode('n1', 2);

    const state = useGraphStore.getState();
    expect(Object.keys(state.nodes)).toHaveLength(2);
    expect(Object.keys(state.edges)).toHaveLength(1);
    expect(state.expanded.has('n1')).toBe(true);
  });

  it('expandFromNode enforces 300 node cap', async () => {
    const bigPayload: GraphPayload = {
      focus_nk: 'n1',
      depth: 2,
      nodes: Array.from({ length: 301 }, (_, i) => ({
        nk: `n${i}`,
        kind: 'topic' as const,
        title_hi: `t${i}`,
        degree: 1,
      })),
      edges: [],
    };
    vi.mocked(expandNode).mockResolvedValueOnce(bigPayload);

    await useGraphStore.getState().expandFromNode('n1', 2, () => false);

    expect(Object.keys(useGraphStore.getState().nodes)).toHaveLength(0);
    expect(useGraphStore.getState().lastError).toContain('cancelled');
  });

  it('expandFromNode merges new nodes without removing existing ones', async () => {
    const initial: GraphPayload = {
      focus_nk: 'n1',
      depth: 2,
      nodes: [
        { nk: 'n1', kind: 'topic', title_hi: 'एक', degree: 1 },
        { nk: 'n2', kind: 'keyword', title_hi: 'दो', degree: 1 },
      ],
      edges: [{ id: 'e1', src: 'n1', dst: 'n2', kind: 'RELATED_TO', weight: 1 }],
    };
    useGraphStore.getState().seedFromPayload(initial, null);

    const expansion: GraphPayload = {
      focus_nk: 'n2',
      depth: 2,
      nodes: [
        { nk: 'n2', kind: 'keyword', title_hi: 'दो', degree: 1 },
        { nk: 'n3', kind: 'topic', title_hi: 'तीन', degree: 1 },
      ],
      edges: [{ id: 'e2', src: 'n2', dst: 'n3', kind: 'RELATED_TO', weight: 1 }],
    };
    vi.mocked(expandNode).mockResolvedValueOnce(expansion);
    await useGraphStore.getState().expandFromNode('n2', 2);

    const state = useGraphStore.getState();
    expect(Object.keys(state.nodes)).toEqual(expect.arrayContaining(['n1', 'n2', 'n3']));
    expect(Object.keys(state.nodes)).toHaveLength(3);
    expect(Object.keys(state.edges)).toEqual(expect.arrayContaining(['e1', 'e2']));
  });

  it('expandFromNode preserves selection and pins', async () => {
    useGraphStore.getState().seedFromPayload(payload, 'n1');
    useGraphStore.getState().togglePin('n1');

    const expansion: GraphPayload = {
      focus_nk: 'n2',
      depth: 2,
      nodes: [{ nk: 'n2', kind: 'keyword', title_hi: 'दो', degree: 1 }, { nk: 'n3', kind: 'topic', title_hi: 'तीन', degree: 1 }],
      edges: [],
    };
    vi.mocked(expandNode).mockResolvedValueOnce(expansion);
    await useGraphStore.getState().expandFromNode('n2', 2);

    const state = useGraphStore.getState();
    expect(state.selected).toEqual({ kind: 'node', id: 'n1' });
    expect(state.pinned.has('n1')).toBe(true);
  });

  it('collapseNode removes only nodes whose sole origin was that expander', async () => {
    const initial: GraphPayload = {
      focus_nk: 'n1',
      depth: 2,
      nodes: [
        { nk: 'n1', kind: 'topic', title_hi: 'एक', degree: 1 },
      ],
      edges: [],
    };
    useGraphStore.getState().seedFromPayload(initial, null);

    const expansion: GraphPayload = {
      focus_nk: 'n1',
      depth: 2,
      nodes: [
        { nk: 'n1', kind: 'topic', title_hi: 'एक', degree: 1 },
        { nk: 'n2', kind: 'keyword', title_hi: 'दो', degree: 1 },
      ],
      edges: [{ id: 'e1', src: 'n1', dst: 'n2', kind: 'RELATED_TO', weight: 1 }],
    };
    vi.mocked(expandNode).mockResolvedValueOnce(expansion);
    await useGraphStore.getState().expandFromNode('n1', 2);

    expect(Object.keys(useGraphStore.getState().nodes)).toHaveLength(2);

    useGraphStore.getState().collapseNode('n1');
    const state = useGraphStore.getState();
    // n1 was seeded, so it stays; n2 was only from n1's expansion, so it's removed
    expect(Object.keys(state.nodes)).toEqual(['n1']);
    expect(Object.keys(state.edges)).toHaveLength(0);
    expect(state.expanded.has('n1')).toBe(false);
  });
});
