import type { EntityKind } from '@/lib/types';
import { DEFAULT_GRAPH_DEPTH } from '@/lib/config';

const VALID_CATS: EntityKind[] = ['shastra', 'gatha', 'topic', 'keyword'];

export interface ParsedGraphQuery {
  node: string | null;
  edge: string | null;
  depth: 1 | 2 | 3 | 4;
  hiddenCats: EntityKind[];
}

export function parseGraphQuery(params: URLSearchParams): ParsedGraphQuery {
  const rawDepth = Number(params.get('depth') ?? DEFAULT_GRAPH_DEPTH);
  const bounded = Math.max(1, Math.min(4, Number.isFinite(rawDepth) ? rawDepth : DEFAULT_GRAPH_DEPTH)) as 1 | 2 | 3 | 4;

  const hiddenCats = (params.get('cat') ?? '')
    .split(',')
    .map(x => x.trim())
    .filter((x): x is EntityKind => VALID_CATS.includes(x as EntityKind));

  return {
    node: params.get('node'),
    edge: params.get('edge'),
    depth: bounded,
    hiddenCats,
  };
}

export function buildGraphQuery(input: {
  selectedNode: string | null;
  selectedEdge: string | null;
  depth: 1 | 2 | 3 | 4;
  hiddenCats: EntityKind[];
}): URLSearchParams {
  const params = new URLSearchParams();
  if (input.selectedNode) params.set('node', input.selectedNode);
  if (input.selectedEdge) params.set('edge', input.selectedEdge);
  params.set('depth', String(input.depth));
  if (input.hiddenCats.length > 0) {
    params.set('cat', [...input.hiddenCats].sort().join(','));
  }
  return params;
}
