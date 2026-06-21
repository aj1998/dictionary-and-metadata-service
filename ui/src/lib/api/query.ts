import { apiFetch } from './_fetch';
import type { GraphRAGResponse, KeywordResolveBatchResponse, SearchResponse, TopicsMatchResponse } from '@/lib/types';

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
  // content_only (query_engine/08 Part A): keep only topics with extract_count>0
  // (leaf AND content-bearing intermediates), dropping content-less containers.
  contentOnly?: boolean;
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
      // content_only defaults to false here so existing callers keep "show all";
      // the /topics search page sets it explicitly from the filter.
      content_only: params.contentOnly ?? false,
    }),
  });
}

export async function keywordResolveBatch(params: {
  tokens: string[];
  fuzzyTopK?: number;
  minSimilarity?: number;
  includeDefinitions?: boolean;
}): Promise<KeywordResolveBatchResponse> {
  return apiFetch<KeywordResolveBatchResponse>(BASE_URL, '/v1/query/keyword_resolve_batch', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      tokens: params.tokens,
      fuzzy_top_k: params.fuzzyTopK ?? 5,
      min_similarity: params.minSimilarity ?? 0.35,
      include_definitions: params.includeDefinitions ?? false,
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
