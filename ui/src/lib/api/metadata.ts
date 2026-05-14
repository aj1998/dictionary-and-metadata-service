import { apiFetch } from './_fetch';
import type { Paginated, ShastraSummary, ShastraDetail, TeekaSummary } from '@/lib/types';

const BASE_URL = process.env.METADATA_SVC_URL ?? 'http://localhost:8001';

export async function getShastras(params?: {
  q?: string;
  anuyoga?: string;
  limit?: number;
  offset?: number;
}): Promise<Paginated<ShastraSummary>> {
  const qs = new URLSearchParams();
  if (params?.q !== undefined) qs.set('q', params.q);
  if (params?.anuyoga !== undefined) qs.set('anuyoga', params.anuyoga);
  if (params?.limit !== undefined) qs.set('limit', String(params.limit));
  if (params?.offset !== undefined) qs.set('offset', String(params.offset));
  const query = qs.toString();
  return apiFetch<Paginated<ShastraSummary>>(BASE_URL, `/v1/shastras${query ? `?${query}` : ''}`);
}

export async function getShastra(nk: string): Promise<ShastraDetail> {
  return apiFetch<ShastraDetail>(BASE_URL, `/v1/shastras/${nk}`);
}

export async function getShastraTeekas(nk: string): Promise<TeekaSummary[]> {
  return apiFetch<TeekaSummary[]>(BASE_URL, `/v1/shastras/${nk}/teekas`);
}
