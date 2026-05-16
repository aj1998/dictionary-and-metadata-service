const raw = Number(process.env.NEXT_PUBLIC_DEFAULT_GRAPH_DEPTH ?? 1);

/** Default graph traversal depth, configurable via NEXT_PUBLIC_DEFAULT_GRAPH_DEPTH (1–4). */
export const DEFAULT_GRAPH_DEPTH: 1 | 2 | 3 | 4 =
  raw === 1 || raw === 2 || raw === 3 || raw === 4 ? raw : 1;
