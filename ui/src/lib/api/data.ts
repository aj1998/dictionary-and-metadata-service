import { apiFetch } from './_fetch';
import type {
  ActivityRow,
  EntityCounts,
  EntityDetail,
  EntityKind,
  KeywordSummary,
  KeywordDetail,
  LetterCount,
  Paginated,
  TopicSummary,
  TopicDetail,
  GathaDetail,
} from '@/lib/types';

const BASE_URL = process.env.DATA_SVC_URL ?? 'http://localhost:8002';

export async function getActivityRecent(): Promise<ActivityRow[]> {
  return apiFetch<ActivityRow[]>(BASE_URL, '/v1/activity/recent');
}

export async function getStatsCounts(): Promise<EntityCounts> {
  return apiFetch<EntityCounts>(BASE_URL, '/v1/stats/counts');
}

export async function getEntityDetail(kind: EntityKind, nk: string): Promise<EntityDetail> {
  return apiFetch<EntityDetail>(BASE_URL, `/v1/entity/${kind}/${nk}/detail`);
}

export async function getKeywordsLetters(): Promise<LetterCount[]> {
  return apiFetch<LetterCount[]>(BASE_URL, '/v1/keywords/letters');
}

export async function getKeywordsRecent(): Promise<KeywordSummary[]> {
  return apiFetch<KeywordSummary[]>(BASE_URL, '/v1/keywords/recent');
}

export async function getKeywords(params?: {
  q?: string;
  letter?: string;
  limit?: number;
  offset?: number;
}): Promise<Paginated<KeywordSummary>> {
  const qs = new URLSearchParams();
  if (params?.q !== undefined) qs.set('q', params.q);
  if (params?.letter !== undefined) qs.set('letter', params.letter);
  if (params?.limit !== undefined) qs.set('limit', String(params.limit));
  if (params?.offset !== undefined) qs.set('offset', String(params.offset));
  const query = qs.toString();
  return apiFetch<Paginated<KeywordSummary>>(BASE_URL, `/v1/keywords${query ? `?${query}` : ''}`);
}

export async function getKeyword(nk: string): Promise<KeywordDetail> {
  return apiFetch<KeywordDetail>(BASE_URL, `/v1/keywords/${nk}`);
}

export async function getTopics(params?: {
  q?: string;
  source?: string;
  limit?: number;
  offset?: number;
}): Promise<Paginated<TopicSummary>> {
  const qs = new URLSearchParams();
  if (params?.q !== undefined) qs.set('q', params.q);
  if (params?.source !== undefined) qs.set('source', params.source);
  if (params?.limit !== undefined) qs.set('limit', String(params.limit));
  if (params?.offset !== undefined) qs.set('offset', String(params.offset));
  const query = qs.toString();
  return apiFetch<Paginated<TopicSummary>>(BASE_URL, `/v1/topics${query ? `?${query}` : ''}`);
}

export async function getTopic(nk: string): Promise<TopicDetail> {
  return apiFetch<TopicDetail>(BASE_URL, `/v1/topics/${nk}`);
}

export async function getGatha(nk: string): Promise<GathaDetail> {
  return apiFetch<GathaDetail>(BASE_URL, `/v1/gathas/${nk}`);
}

export async function getGathaRelatedTopics(nk: string): Promise<TopicSummary[]> {
  return apiFetch<TopicSummary[]>(BASE_URL, `/v1/gathas/${nk}/related-topics`);
}

export async function getGathaRelatedKeywords(nk: string): Promise<KeywordSummary[]> {
  return apiFetch<KeywordSummary[]>(BASE_URL, `/v1/gathas/${nk}/related-keywords`);
}
