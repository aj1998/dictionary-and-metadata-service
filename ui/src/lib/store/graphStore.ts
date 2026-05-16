import { create } from 'zustand';
import * as navigationApi from '@/lib/api/navigation';
import type { EntityKind, GraphEdge, GraphNode, GraphPayload } from '@/lib/types';

const DEFAULT_VISIBILITY: Record<EntityKind, boolean> = {
  shastra: true,
  gatha: true,
  topic: true,
  keyword: true,
};

type Selected =
  | { kind: 'node'; id: string }
  | { kind: 'edge'; id: string }
  | null;

type GraphState = {
  nodes: Record<string, GraphNode>;
  edges: Record<string, GraphEdge>;
  pinned: Set<string>;
  expanded: Set<string>;
  selected: Selected;
  categoryVisibility: Record<EntityKind, boolean>;
  depth: 1 | 2 | 3 | 4;
  layout: 'force' | 'radial' | 'hierarchical';
  camera: { x: number; y: number; k: number };
  loading: boolean;
  lastError: string | null;
  seedNk: string | null;
  selectNode: (id: string) => void;
  selectEdge: (id: string) => void;
  clearSelection: () => void;
  togglePin: (id: string) => void;
  seedFromPayload: (payload: GraphPayload, selectedNk?: string | null) => void;
  expandFromNode: (nk: string, depth: 1 | 2 | 3 | 4, confirm?: (newCount: number) => boolean) => Promise<void>;
  setCategoryVisibility: (kind: EntityKind, visible: boolean) => void;
  setDepth: (depth: 1 | 2 | 3 | 4) => void;
  changeDepth: (depth: 1 | 2 | 3 | 4) => Promise<void>;
  setLayout: (layout: 'force' | 'radial' | 'hierarchical') => void;
  setCamera: (camera: { x: number; y: number; k: number }) => void;
  reset: () => void;
};

function mergePayload(
  oldNodes: Record<string, GraphNode>,
  oldEdges: Record<string, GraphEdge>,
  payload: GraphPayload,
): { nodes: Record<string, GraphNode>; edges: Record<string, GraphEdge> } {
  const nodes = { ...oldNodes };
  const edges = { ...oldEdges };
  for (const node of payload.nodes) nodes[node.nk] = node;
  for (const edge of payload.edges) edges[edge.id] = edge;
  return { nodes, edges };
}

const initialState = {
  nodes: {},
  edges: {},
  pinned: new Set<string>(),
  expanded: new Set<string>(),
  selected: null as Selected,
  categoryVisibility: { ...DEFAULT_VISIBILITY },
  depth: 2 as 1 | 2 | 3 | 4,
  layout: 'hierarchical' as const,
  camera: { x: 0, y: 0, k: 1 },
  loading: false,
  lastError: null,
  seedNk: null as string | null,
};

export const useGraphStore = create<GraphState>((set, get) => ({
  ...initialState,

  selectNode: (id) => set({ selected: { kind: 'node', id } }),
  selectEdge: (id) => set({ selected: { kind: 'edge', id } }),
  clearSelection: () => set({ selected: null }),
  togglePin: (id) => set((state) => {
    const pinned = new Set(state.pinned);
    if (pinned.has(id)) pinned.delete(id);
    else pinned.add(id);
    return { pinned };
  }),
  seedFromPayload: (payload, selectedNk) => set((state) => {
    const merged = mergePayload(state.nodes, state.edges, payload);
    return {
      ...merged,
      selected: selectedNk ? { kind: 'node', id: selectedNk } : state.selected,
      expanded: new Set(state.expanded).add(payload.focus_nk),
      depth: Math.max(1, Math.min(4, payload.depth)) as 1 | 2 | 3 | 4,
      seedNk: payload.focus_nk,
    };
  }),
  expandFromNode: async (nk, depth, confirm) => {
    set({ loading: true, lastError: null });
    try {
      const payload = await navigationApi.expandNode(nk, depth);
      const currentCount = Object.keys(get().nodes).length;
      const incoming = payload.nodes.filter((n) => !get().nodes[n.nk]).length;
      const wouldBe = currentCount + incoming;
      if (wouldBe > 300) {
        const ok = confirm ? confirm(incoming) : globalThis.confirm(`यह ${incoming} और नोड्स लोड करेगा — जारी रखें?`);
        if (!ok) {
          set({ loading: false, lastError: 'expand cancelled by user' });
          return;
        }
      }
      set((state) => {
        const merged = mergePayload(state.nodes, state.edges, payload);
        return {
          ...merged,
          expanded: new Set(state.expanded).add(nk),
          seedNk: state.seedNk ?? nk,
          loading: false,
        };
      });
    } catch (err) {
      console.warn('expandFromNode failed');
      set({ loading: false, lastError: 'expand failed' });
    }
  },
  setCategoryVisibility: (kind, visible) => set((state) => ({
    categoryVisibility: { ...state.categoryVisibility, [kind]: visible },
  })),
  setDepth: (depth) => set({ depth }),
  changeDepth: async (depth) => {
    const { selected, seedNk } = get();
    const focusNk = (selected?.kind === 'node' ? selected.id : null) ?? seedNk;
    set({ depth });
    if (!focusNk) return;
    set({ loading: true, lastError: null });
    try {
      const payload = await navigationApi.expandNode(focusNk, depth);
      set({
        nodes: Object.fromEntries(payload.nodes.map((n) => [n.nk, n])),
        edges: Object.fromEntries(payload.edges.map((e) => [e.id, e])),
        expanded: new Set([focusNk]),
        pinned: new Set<string>(),
        loading: false,
      });
    } catch {
      console.warn('changeDepth failed');
      set({ loading: false, lastError: 'depth change failed' });
    }
  },
  setLayout: (layout) => set({ layout }),
  setCamera: (camera) => set({ camera }),
  reset: () => set({ ...initialState, categoryVisibility: { ...DEFAULT_VISIBILITY } }),
}));
