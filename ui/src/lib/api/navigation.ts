import { apiFetch } from './_fetch';
import type { GraphPayload, TopicNeighborsResponse } from '@/lib/types';

const BASE_URL = process.env.NAV_SVC_URL ?? '/api/navigation';

export async function getNavLanding(): Promise<GraphPayload> {
  return apiFetch<GraphPayload>(BASE_URL, '/v1/landing');
}

export async function expandNode(nk: string, depth: 1 | 2 | 3 | 4): Promise<GraphPayload> {
  return apiFetch<GraphPayload>(BASE_URL, `/v1/expand/${nk}?depth=${depth}`);
}

export async function getPreview(nk: string, hops?: 1 | 2): Promise<GraphPayload> {
  const query = hops !== undefined ? `?hops=${hops}` : '';
  return apiFetch<GraphPayload>(BASE_URL, `/v1/preview/${nk}${query}`);
}

export async function getTopicNeighbors(nk: string): Promise<TopicNeighborsResponse> {
  return apiFetch<TopicNeighborsResponse>(BASE_URL, `/v1/topics/${nk}/neighbors`);
}
