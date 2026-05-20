import { apiFetch } from './_fetch';
import type { GraphRAGResponse, SearchResponse, TopicsMatchResponse } from '@/lib/types';

const BASE_URL = process.env.QUERY_SVC_URL ?? '/api/query';

export async function searchTopics(params: {
  q: string;
  caller?: string;
}): Promise<SearchResponse> {
  return apiFetch<SearchResponse>(BASE_URL, '/v1/graphrag/topics', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ q: params.q, caller: params.caller ?? 'public-ui' }),
  });
}

export async function topicsMatch(params: {
  phrase?: string;
  keywords?: string[];
  limit?: number;
  minSimilarity?: number;
  includeExtracts?: boolean;
  includeReferences?: boolean;
  leafOnly?: boolean;
}): Promise<TopicsMatchResponse> {
  return apiFetch<TopicsMatchResponse>(BASE_URL, '/v1/query/topics_match', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      phrase: params.phrase,
      keywords: params.keywords,
      limit: params.limit ?? 10,
      min_similarity: params.minSimilarity ?? 0.3,
      include_extracts: params.includeExtracts ?? false,
      include_references: params.includeReferences ?? false,
      leaf_only: params.leafOnly ?? false,
    }),
  });
}

export async function graphragTopics(params: {
  tokens: string[];
  maxHops?: number;
  limit?: number;
  includeExtracts?: boolean;
  includeNeighbors?: boolean;
  includeReferences?: boolean;
  fuzzy?: boolean;
}): Promise<GraphRAGResponse> {
  return apiFetch<GraphRAGResponse>(BASE_URL, '/v1/query/graphrag', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      tokens: params.tokens,
      max_hops: params.maxHops ?? 2,
      limit: params.limit ?? 5,
      include_extracts: params.includeExtracts ?? false,
      include_neighbors: params.includeNeighbors ?? false,
      include_references: params.includeReferences ?? false,
      fuzzy: params.fuzzy ?? false,
    }),
  });
}
