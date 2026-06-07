import { apiFetch } from './_fetch';
import type { GraphPayload, TopicNeighborsResponse } from '@/lib/types';
import { DEFAULT_GRAPH_DEPTH } from '@/lib/config';

const BASE_URL = process.env.NAV_SVC_URL ?? '/api/navigation';

// Set NEXT_PUBLIC_GRAPH_EXCLUDE_STUBS=true to hide stub (cross-reference placeholder) nodes.
// Defaults to false so stub Gatha/GathaTeeka/GathaTeekaBhaavarth/Kalash/KalashBhaavarth
// nodes (seeded by JainKosh ingestion and later filled in by NJ ingestion) are visible.
const EXCLUDE_STUBS = process.env.NEXT_PUBLIC_GRAPH_EXCLUDE_STUBS === 'true';

// deprecated: replaced by /v1/landing/random
export async function getNavLanding(): Promise<GraphPayload> {
  const qs = EXCLUDE_STUBS ? '' : '?exclude_stubs=false';
  return apiFetch<GraphPayload>(BASE_URL, `/v1/landing${qs}`);
}

export async function getNavLandingRandom(depth: 1 | 2 | 3 | 4 = DEFAULT_GRAPH_DEPTH): Promise<GraphPayload> {
  const params = new URLSearchParams({ depth: String(depth) });
  if (!EXCLUDE_STUBS) params.set('exclude_stubs', 'false');
  return apiFetch<GraphPayload>(BASE_URL, `/v1/landing/random?${params.toString()}`);
}

export async function expandNode(nk: string, depth: 1 | 2 | 3 | 4): Promise<GraphPayload> {
  const stubParam = EXCLUDE_STUBS ? '' : '&exclude_stubs=false';
  return apiFetch<GraphPayload>(BASE_URL, `/v1/expand/${nk}?depth=${depth}${stubParam}`);
}

export async function getPreview(nk: string, hops?: 1 | 2): Promise<GraphPayload> {
  const params = new URLSearchParams();
  if (hops !== undefined) params.set('hops', String(hops));
  if (!EXCLUDE_STUBS) params.set('exclude_stubs', 'false');
  const qs = params.toString() ? `?${params.toString()}` : '';
  return apiFetch<GraphPayload>(BASE_URL, `/v1/preview/${nk}${qs}`);
}

export async function getTopicNeighbors(nk: string): Promise<TopicNeighborsResponse> {
  return apiFetch<TopicNeighborsResponse>(BASE_URL, `/v1/topics/${nk}/neighbors`);
}

export async function getKeywordTopics(nk: string): Promise<{ keyword_natural_key: string; topics: Array<{ natural_key: string; display_text_hi: string; edge_type: string; is_stub: boolean }> }> {
  return apiFetch(BASE_URL, `/v1/keywords/${nk}/topics`);
}
