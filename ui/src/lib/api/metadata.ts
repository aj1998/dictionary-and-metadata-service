import { apiFetch } from './_fetch';
import type { Paginated, ShastraSummary, ShastraDetail, TeekaSummary, GathaSummary } from '@/lib/types';

const BASE_URL = process.env.METADATA_SVC_URL ?? '/api/metadata';

export async function getShastras(params?: {
  q?: string;
  anuyoga?: string;
  limit?: number;
  offset?: number;
  fuzzy?: boolean;
  minSimilarity?: number;
}): Promise<Paginated<ShastraSummary>> {
  const qs = new URLSearchParams();
  if (params?.q !== undefined) qs.set('q', params.q);
  if (params?.anuyoga !== undefined) qs.set('anuyoga', params.anuyoga);
  if (params?.limit !== undefined) qs.set('limit', String(params.limit));
  if (params?.offset !== undefined) qs.set('offset', String(params.offset));
  if (params?.fuzzy) qs.set('fuzzy', 'true');
  if (params?.minSimilarity !== undefined) qs.set('min_similarity', String(params.minSimilarity));
  const query = qs.toString();
  return apiFetch<Paginated<ShastraSummary>>(BASE_URL, `/v1/shastras${query ? `?${query}` : ''}`);
}

export async function getShastra(nk: string): Promise<ShastraDetail> {
  return apiFetch<ShastraDetail>(BASE_URL, `/v1/shastras/${nk}`);
}

// Either a scalar offset or an array of [upToPublishedPage, offset] pairs.
// Pairs are applied in ascending order of threshold: for a published page P,
// the first pair where P <= upToPublishedPage wins.
export type OffsetSpec = number | Array<[number, number]>;

export interface ShastraPdfOffsetsResponse {
  pdf_page_offset: OffsetSpec;
  pustak_offsets: Record<string, OffsetSpec> | null;
  available: boolean;
}

export async function getShastraPdfOffsets(nk: string): Promise<ShastraPdfOffsetsResponse> {
  return apiFetch<ShastraPdfOffsetsResponse>(BASE_URL, `/v1/shastras/${nk}/pdf-offsets`);
}

export async function getShastraTeekas(nk: string): Promise<TeekaSummary[]> {
  const result = await apiFetch<{ items: TeekaSummary[] } | TeekaSummary[]>(BASE_URL, `/v1/shastras/${nk}/teekas`);
  if (Array.isArray(result)) return result;
  return result.items ?? [];
}

export async function getShastraGathas(
  nk: string,
  params?: { limit?: number; offset?: number }
): Promise<Paginated<GathaSummary>> {
  const qs = new URLSearchParams();
  if (params?.limit !== undefined) qs.set('limit', String(params.limit));
  if (params?.offset !== undefined) qs.set('offset', String(params.offset));
  const query = qs.toString();
  return apiFetch<Paginated<GathaSummary>>(BASE_URL, `/v1/shastras/${nk}/gathas${query ? `?${query}` : ''}`);
}
