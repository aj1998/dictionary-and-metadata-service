import { apiFetch } from './_fetch';
import type { SearchResponse } from '@/lib/types';

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
