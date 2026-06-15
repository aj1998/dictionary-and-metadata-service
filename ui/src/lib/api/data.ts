import { ApiError, apiFetch } from './_fetch';
import type {
  ActivityRow,
  DefinitionBlock,
  EntityCounts,
  EntityDetail,
  EntityKind,
  ExtractMatch,
  KeywordSummary,
  KeywordDetail,
  KeywordPageSection,
  LetterCount,
  Paginated,
  TopicSummary,
  TopicDetail,
  GathaDetail,
  GathaSummary,
  GathaAdjacentResponse,
  KalashDetail,
  KalashWordMeanings,
  ShastraDetail,
  TableFull,
  TableSummary,
} from '@/lib/types';

const BASE_URL = process.env.DATA_SVC_URL ?? '/api/data';
const METADATA_BASE_URL = process.env.METADATA_SVC_URL ?? '/api/metadata';

export async function getActivityRecent(): Promise<ActivityRow[]> {
  try {
    return await apiFetch<ActivityRow[]>(BASE_URL, '/v1/activity/recent');
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) {
      console.warn('data-service missing /v1/activity/recent, returning empty activity list');
      return [];
    }
    throw error;
  }
}

export async function getStatsCounts(): Promise<EntityCounts> {
  try {
    return await apiFetch<EntityCounts>(BASE_URL, '/v1/stats/counts');
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) {
      console.warn('data-service missing /v1/stats/counts, returning zero counts');
      return {
        shastras: 0,
        gathas: 0,
        topics: 0,
        keywords: 0,
      };
    }
    throw error;
  }
}

function extractBlocks(e: unknown): DefinitionBlock[] {
  if (e && typeof e === 'object') {
    const obj = e as Record<string, unknown>;
    if (Array.isArray(obj.blocks)) return obj.blocks as DefinitionBlock[];
  }
  return [];
}

export async function getEntityDetail(kind: EntityKind, nk: string): Promise<EntityDetail> {
  if (kind === 'keyword') {
    const keyword = await apiFetch<KeywordDetail>(BASE_URL, `/v1/keywords/${nk}`);
    const sections: KeywordPageSection[] = keyword.definition?.page_sections ?? [];
    const firstText = sections[0]?.definitions[0]?.blocks[0]?.text_devanagari ?? '';
    const allKwBlocks = sections.flatMap((s) => s.definitions.flatMap((d) => d.blocks));
    const totalBlocks = allKwBlocks.length;
    const totalKwRefs = allKwBlocks.reduce((sum, b) => sum + (b.references?.length ?? 0), 0);
    return {
      nk: keyword.natural_key,
      kind: 'keyword',
      title_hi: keyword.display_text,
      description: firstText.slice(0, 250) || undefined,
      stats: { aliases: keyword.aliases.length, definitions: totalBlocks, references: totalKwRefs },
      connected: [],
      definitionSections: sections.length ? sections : undefined,
    };
  }

  if (kind === 'topic') {
    const topic = await apiFetch<TopicDetail>(BASE_URL, `/v1/topics/${nk}`);
    const hi = topic.display_text.find((row) => row.lang === 'hi')?.text ?? topic.natural_key;
    const parent = topic.parent_keyword;
    const allBlocks = topic.extracts.flatMap(extractBlocks)
      .filter((b) => b.text_devanagari?.trim() || b.hindi_translation?.trim());
    const totalRefs = allBlocks.reduce((sum, b) => sum + (b.references?.length ?? 0), 0);
    return {
      nk: topic.natural_key,
      kind: 'topic',
      title_hi: hi,
      stats: { extracts: allBlocks.length, is_leaf: topic.is_leaf ? 1 : 0, references: totalRefs },
      topicPath: topic.topic_path ?? undefined,
      connected: parent
        ? [{
            nk: parent.natural_key,
            kind: 'keyword',
            title_hi: parent.display_text,
            edge_kind: 'HAS_TOPIC',
          }]
        : [],
      topicExtracts: allBlocks.length ? allBlocks : undefined,
    };
  }

  if (kind === 'gatha') {
    const gatha = await apiFetch<GathaDetail>(BASE_URL, `/v1/gathas/${nk}`);
    return {
      nk: gatha.natural_key,
      kind: 'gatha',
      title_hi: `गाथा ${gatha.gatha_number}`,
      description: gatha.heading.find((row) => row.lang === 'hi')?.text,
      stats: { hindi_chhand: gatha.hindi_chhand.length },
      connected: [{
        nk: gatha.shastra.natural_key,
        kind: 'shastra',
        title_hi: gatha.shastra.title.find((row) => row.lang === 'hi')?.text ?? gatha.shastra.natural_key,
        edge_kind: 'IN_SHASTRA',
      }],
    };
  }

  const shastra = await apiFetch<ShastraDetail>(METADATA_BASE_URL, `/v1/shastras/${nk}`);
  const hi = shastra.title.find((row) => row.lang === 'hi')?.text ?? shastra.natural_key;
  return {
    nk: shastra.natural_key,
    kind: 'shastra',
    title_hi: hi,
    description: shastra.source_url,
    stats: { teekas: shastra.teekas?.length ?? 0 },
    connected: [],
  };
}

export async function getKeywordsLetters(): Promise<LetterCount[]> {
  return apiFetch<LetterCount[]>(BASE_URL, '/v1/keywords/letters');
}

export async function getKeywordsRecent(): Promise<KeywordSummary[]> {
  try {
    const result = await apiFetch<{ items: KeywordSummary[] }>(BASE_URL, '/v1/keywords?limit=10');
    return result.items ?? [];
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) {
      console.warn('data-service /v1/keywords not available, returning empty list');
      return [];
    }
    throw error;
  }
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
  hasTopicPath?: boolean;
  isLeaf?: boolean;
}): Promise<Paginated<TopicSummary>> {
  const qs = new URLSearchParams();
  if (params?.q !== undefined) qs.set('q', params.q);
  if (params?.source !== undefined) qs.set('source', params.source);
  if (params?.limit !== undefined) qs.set('limit', String(params.limit));
  if (params?.offset !== undefined) qs.set('offset', String(params.offset));
  if (params?.hasTopicPath !== undefined) qs.set('has_topic_path', params.hasTopicPath ? 'true' : 'false');
  if (params?.isLeaf !== undefined) qs.set('is_leaf', params.isLeaf ? 'true' : 'false');
  const query = qs.toString();
  return apiFetch<Paginated<TopicSummary>>(BASE_URL, `/v1/topics${query ? `?${query}` : ''}`);
}

export async function getTopic(nk: string): Promise<TopicDetail> {
  return apiFetch<TopicDetail>(BASE_URL, `/v1/topics/${nk}`);
}

export async function getGathasByShastraId(
  shastraId: string,
  params?: { limit?: number; offset?: number }
): Promise<Paginated<GathaSummary>> {
  const qs = new URLSearchParams({ shastra_id: shastraId });
  if (params?.limit !== undefined) qs.set('limit', String(params.limit));
  if (params?.offset !== undefined) qs.set('offset', String(params.offset));
  return apiFetch<Paginated<GathaSummary>>(BASE_URL, `/v1/gathas?${qs.toString()}`);
}

export async function getGatha(nk: string, options?: { include?: string[] }): Promise<GathaDetail> {
  const inc = options?.include;
  const qs = inc?.length ? `?include=${inc.join(',')}` : '';
  return apiFetch<GathaDetail>(BASE_URL, `/v1/gathas/${nk}${qs}`);
}

export async function getGathaByPath(
  shastraNk: string,
  rawId: string,
  options?: { include?: string[] }
): Promise<GathaDetail> {
  const inc = options?.include;
  const qs = inc?.length ? `?include=${inc.join(',')}` : '';
  return apiFetch<GathaDetail>(BASE_URL, `/v1/shastras/${shastraNk}/gathas/${rawId}${qs}`);
}

export async function getGathaAdjacent(
  shastraNk: string,
  rawId: string
): Promise<GathaAdjacentResponse> {
  return apiFetch<GathaAdjacentResponse>(BASE_URL, `/v1/shastras/${shastraNk}/gathas/${rawId}/adjacent`);
}

export async function getKalash(nk: string): Promise<KalashDetail> {
  return apiFetch<KalashDetail>(BASE_URL, `/v1/kalashas/${nk}`);
}

export async function getKalashWordMeanings(nk: string): Promise<KalashWordMeanings | null> {
  try {
    return await apiFetch<KalashWordMeanings>(BASE_URL, `/v1/kalashas/${nk}/word_meanings`);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null;
    throw error;
  }
}

export async function getGathaRelatedTopics(nk: string): Promise<TopicSummary[]> {
  return apiFetch<TopicSummary[]>(BASE_URL, `/v1/gathas/${nk}/related-topics`);
}

export async function getGathaRelatedKeywords(nk: string): Promise<KeywordSummary[]> {
  return apiFetch<KeywordSummary[]>(BASE_URL, `/v1/gathas/${nk}/related-keywords`);
}

export async function getExtractMatch(naturalKey: string): Promise<ExtractMatch> {
  return apiFetch<ExtractMatch>(BASE_URL, `/v1/extract-matches/${naturalKey}`);
}

export async function getTable(naturalKey: string): Promise<TableFull> {
  return apiFetch<TableFull>(BASE_URL, `/v1/tables/${naturalKey}`);
}

export async function listTablesForParent(parentNaturalKey: string): Promise<TableSummary[]> {
  return apiFetch<TableSummary[]>(
    BASE_URL,
    `/v1/tables?parent_natural_key=${encodeURIComponent(parentNaturalKey)}`,
  );
}
