import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
import { ApiError } from './_fetch';
import {
  getActivityRecent,
  getStatsCounts,
  getEntityDetail,
  getKeywordsLetters,
  getKeywordsRecent,
  getKeywords,
  getKeyword,
  getTopics,
  getTopic,
  getGatha,
  getGathaRelatedTopics,
  getGathaRelatedKeywords,
  getKalash,
  getKalashWordMeanings,
} from './data';

const BASE = 'http://localhost:3000/api/data';

describe('data API', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  const mockSuccess = (data: unknown) => {
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: true,
      json: async () => data,
    });
  };

  const mockError = (status = 404) => {
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: false,
      status,
      json: async () => ({ error: 'not found' }),
    });
  };

  describe('getActivityRecent', () => {
    it('calls correct URL and returns data', async () => {
      const fixture = [{ id: '1', run_at: '2024-01-01T00:00:00Z', source: 'manual', entities_touched: 5 }];
      mockSuccess(fixture);
      const result = await getActivityRecent();
      expect((fetch as ReturnType<typeof vi.fn>).mock.calls[0][0]).toBe(`${BASE}/v1/activity/recent`);
      expect(result).toEqual(fixture);
    });

    it('throws ApiError on error', async () => {
      mockError(500);
      await expect(getActivityRecent()).rejects.toThrow(ApiError);
      await expect(getActivityRecent()).rejects.toMatchObject({ status: 500 });
    });

    it('returns empty list on 404 fallback', async () => {
      mockError(404);
      const result = await getActivityRecent();
      expect(result).toEqual([]);
    });
  });

  describe('getStatsCounts', () => {
    it('calls correct URL and returns data', async () => {
      const fixture = { shastras: 10, gathas: 100, topics: 50, keywords: 200 };
      mockSuccess(fixture);
      const result = await getStatsCounts();
      expect((fetch as ReturnType<typeof vi.fn>).mock.calls[0][0]).toBe(`${BASE}/v1/stats/counts`);
      expect(result).toEqual(fixture);
    });

    it('throws ApiError on error', async () => {
      mockError(500);
      await expect(getStatsCounts()).rejects.toThrow(ApiError);
    });

    it('returns zero counts on 404 fallback', async () => {
      mockError(404);
      const result = await getStatsCounts();
      expect(result).toEqual({
        shastras: 0,
        gathas: 0,
        topics: 0,
        keywords: 0,
      });
    });
  });

  describe('getEntityDetail', () => {
    it('calls keywords endpoint and maps response for keyword kind', async () => {
      const fixture = {
        id: 'kw-1',
        natural_key: 'atma',
        display_text: 'आत्मा',
        aliases: [],
        definition: null,
      };
      mockSuccess(fixture);
      const result = await getEntityDetail('keyword', 'atma');
      expect((fetch as ReturnType<typeof vi.fn>).mock.calls[0][0]).toBe(
        `${BASE}/v1/keywords/atma`
      );
      expect(result).toMatchObject({
        nk: 'atma',
        kind: 'keyword',
        title_hi: 'आत्मा',
      });
    });

    it('calls metadata-backed shastra endpoint and maps response', async () => {
      const fixture = {
        id: 'sh-1',
        natural_key: 'tattvaartha',
        title: [{ lang: 'hi', script: 'devanagari', text: 'तत्त्वार्थसूत्र' }],
      };
      mockSuccess(fixture);
      await getEntityDetail('shastra', 'tattvaartha');
      expect((fetch as ReturnType<typeof vi.fn>).mock.calls[0][0]).toBe(
        `http://localhost:3000/api/metadata/v1/shastras/tattvaartha`
      );
    });

    it('calls topics endpoint for topic kind', async () => {
      mockSuccess({
        id: 'tp-1',
        natural_key: 'moksha',
        display_text: [{ lang: 'hi', script: 'devanagari', text: 'मोक्ष' }],
        source: 'manual',
        is_leaf: true,
        topic_path: '/moksha',
        parent_keyword: null,
        is_synthetic: false,
        parent_topic: null,
        extracts: [],
      });
      await getEntityDetail('topic', 'moksha');
      expect((fetch as ReturnType<typeof vi.fn>).mock.calls[0][0]).toBe(
        `${BASE}/v1/topics/moksha`
      );
    });

    describe('keyword branch — definition normalisation', () => {
      const makeDefinition = (firstText: string) => ({
        created_at: '2024-01-01T00:00:00Z',
        keyword_id: 'kw-1',
        natural_key: 'dravya',
        page_sections: [{
          section_index: 0,
          section_kind: 'siddhantkosh',
          h2_text: 'सिद्धांतकोष से',
          definitions: [{
            definition_index: 0,
            blocks: [{
              kind: 'hindi_text',
              text_devanagari: firstText,
              hindi_translation: null,
              references: [],
              is_orphan_translation: false,
              is_bullet_point: false,
              raw_html: null,
              table_rows: null,
              target_keyword: null,
              target_topic_path: null,
              target_url: null,
              is_self: false,
              target_exists: true,
            }],
            raw_html: null,
          }],
          label_topic_seeds: [],
          extra_blocks: [],
        }],
        redirect_aliases: [],
        source_url: 'https://example.com',
        updated_at: '2024-01-01T00:00:00Z',
      });

      it('populates definitionSections when definition has page_sections', async () => {
        mockSuccess({
          id: 'kw-1',
          natural_key: 'dravya',
          display_text: 'द्रव्य',
          aliases: [],
          definition: makeDefinition('लोक द्रव्यों का समूह है।'),
        });
        const result = await getEntityDetail('keyword', 'dravya');
        expect(result.definitionSections).toHaveLength(1);
        expect(result.definitionSections![0].h2_text).toBe('सिद्धांतकोष से');
      });

      it('sets description from first block text (up to 250 chars)', async () => {
        const longText = 'अ'.repeat(300);
        mockSuccess({
          id: 'kw-1',
          natural_key: 'dravya',
          display_text: 'द्रव्य',
          aliases: [],
          definition: makeDefinition(longText),
        });
        const result = await getEntityDetail('keyword', 'dravya');
        expect(result.description).toHaveLength(250);
      });

      it('omits definitionSections when definition is null', async () => {
        mockSuccess({
          id: 'kw-1',
          natural_key: 'dravya',
          display_text: 'द्रव्य',
          aliases: [],
          definition: null,
        });
        const result = await getEntityDetail('keyword', 'dravya');
        expect(result.definitionSections).toBeUndefined();
        expect(result.description).toBeUndefined();
      });

      it('omits definitionSections when page_sections is empty', async () => {
        mockSuccess({
          id: 'kw-1',
          natural_key: 'dravya',
          display_text: 'द्रव्य',
          aliases: [],
          definition: { ...makeDefinition('text'), page_sections: [] },
        });
        const result = await getEntityDetail('keyword', 'dravya');
        expect(result.definitionSections).toBeUndefined();
      });
    });

    describe('topic branch — extracts normalisation', () => {
      const baseTopic = {
        id: 'tp-1',
        natural_key: 'dharma',
        display_text: [{ lang: 'hi', script: 'devanagari', text: 'धर्म' }],
        source: 'manual',
        is_leaf: true,
        topic_path: '1.2',
        parent_keyword: null,
        is_synthetic: false,
        parent_topic: null,
      };

      it('flattens blocks from all extracts into topicExtracts', async () => {
        const block1 = { kind: 'sanskrit_text', text_devanagari: 'गुणसमुदायो द्रव्यमिति।', hindi_translation: 'गुणों का समुदाय द्रव्य होता है।', references: [] };
        const block2 = { kind: 'hindi_text', text_devanagari: 'द्रव्य नित्य है।', hindi_translation: null, references: [] };
        mockSuccess({ ...baseTopic, extracts: [
          { blocks: [block1], heading: [] },
          { blocks: [block2], heading: [] },
        ]});
        const result = await getEntityDetail('topic', 'dharma');
        expect(result.topicExtracts).toHaveLength(2);
        expect(result.topicExtracts![0]).toMatchObject({ kind: 'sanskrit_text', text_devanagari: 'गुणसमुदायो द्रव्यमिति।' });
        expect(result.topicExtracts![1]).toMatchObject({ kind: 'hindi_text', text_devanagari: 'द्रव्य नित्य है।' });
      });

      it('preserves hindi_translation on each block', async () => {
        const block = { kind: 'sanskrit_text', text_devanagari: 'गुणसमुदायो द्रव्यमिति।', hindi_translation: 'गुणों का समुदाय द्रव्य होता है।', references: [] };
        mockSuccess({ ...baseTopic, extracts: [{ blocks: [block], heading: [] }] });
        const result = await getEntityDetail('topic', 'dharma');
        expect(result.topicExtracts![0].hindi_translation).toBe('गुणों का समुदाय द्रव्य होता है।');
      });

      it('omits topicExtracts when all extracts have empty blocks', async () => {
        mockSuccess({ ...baseTopic, extracts: [{ blocks: [], heading: [] }, { blocks: [], heading: [] }] });
        const result = await getEntityDetail('topic', 'dharma');
        expect(result.topicExtracts).toBeUndefined();
      });

      it('omits topicExtracts when extracts array is empty', async () => {
        mockSuccess({ ...baseTopic, extracts: [] });
        const result = await getEntityDetail('topic', 'dharma');
        expect(result.topicExtracts).toBeUndefined();
      });

      it('sets description to topic_path', async () => {
        mockSuccess({ ...baseTopic, extracts: [] });
        const result = await getEntityDetail('topic', 'dharma');
        expect(result.description).toBe('1.2');
      });

      it('sets description to undefined when topic_path is null', async () => {
        mockSuccess({ ...baseTopic, topic_path: null, extracts: [] });
        const result = await getEntityDetail('topic', 'dharma');
        expect(result.description).toBeUndefined();
      });
    });

    it('calls gathas endpoint for gatha kind', async () => {
      mockSuccess({
        id: 'g-1',
        natural_key: 'gatha-1',
        gatha_number: '1',
        shastra: { natural_key: 'ts', title: [] },
        adhikaar: [],
        heading: [],
        prakrit: null,
        sanskrit: null,
        hindi_chhand: [],
        word_meanings: null,
      });
      await getEntityDetail('gatha', 'gatha-1');
      expect((fetch as ReturnType<typeof vi.fn>).mock.calls[0][0]).toBe(
        `${BASE}/v1/gathas/gatha-1`
      );
    });

    it('throws ApiError on error', async () => {
      mockError(404);
      await expect(getEntityDetail('keyword', 'missing')).rejects.toThrow(ApiError);
      await expect(getEntityDetail('keyword', 'missing')).rejects.toMatchObject({ status: 404 });
    });
  });

  describe('getKeywordsLetters', () => {
    it('calls correct URL and returns data', async () => {
      const fixture = [{ letter: 'अ', count: 10 }];
      mockSuccess(fixture);
      const result = await getKeywordsLetters();
      expect((fetch as ReturnType<typeof vi.fn>).mock.calls[0][0]).toBe(`${BASE}/v1/keywords/letters`);
      expect(result).toEqual(fixture);
    });

    it('throws ApiError on error', async () => {
      mockError(500);
      await expect(getKeywordsLetters()).rejects.toThrow(ApiError);
    });
  });

  describe('getKeywordsRecent', () => {
    it('calls /v1/keywords?limit=10 and returns items array', async () => {
      const items = [{ id: '1', natural_key: 'atma', display_text: 'आत्मा' }];
      mockSuccess({ pagination: { total: 1, limit: 10, offset: 0 }, items });
      const result = await getKeywordsRecent();
      expect((fetch as ReturnType<typeof vi.fn>).mock.calls[0][0]).toBe(`${BASE}/v1/keywords?limit=10`);
      expect(result).toEqual(items);
    });
  });

  describe('getKeywords', () => {
    it('calls correct URL with no params', async () => {
      mockSuccess({ pagination: { total: 0, limit: 20, offset: 0 }, items: [] });
      await getKeywords();
      expect((fetch as ReturnType<typeof vi.fn>).mock.calls[0][0]).toBe(`${BASE}/v1/keywords`);
    });

    it('appends query params', async () => {
      mockSuccess({ pagination: { total: 0, limit: 10, offset: 0 }, items: [] });
      await getKeywords({ q: 'test', letter: 'अ', limit: 10, offset: 0 });
      const url = (fetch as ReturnType<typeof vi.fn>).mock.calls[0][0] as string;
      expect(url).toContain('q=test');
      expect(url).toContain('letter=');
      expect(url).toContain('limit=10');
    });

    it('throws ApiError on error', async () => {
      mockError(500);
      await expect(getKeywords()).rejects.toThrow(ApiError);
    });
  });

  describe('getKeyword', () => {
    it('calls correct URL and returns data', async () => {
      const fixture = { id: '1', natural_key: 'atma', display_text: 'आत्मा', aliases: [], definition: null };
      mockSuccess(fixture);
      const result = await getKeyword('atma');
      expect((fetch as ReturnType<typeof vi.fn>).mock.calls[0][0]).toBe(`${BASE}/v1/keywords/atma`);
      expect(result).toEqual(fixture);
    });

    it('throws ApiError on 404', async () => {
      mockError(404);
      await expect(getKeyword('missing')).rejects.toThrow(ApiError);
      await expect(getKeyword('missing')).rejects.toMatchObject({ status: 404 });
    });
  });

  describe('getTopics', () => {
    it('calls correct URL with no params', async () => {
      mockSuccess({ pagination: { total: 0, limit: 20, offset: 0 }, items: [] });
      await getTopics();
      expect((fetch as ReturnType<typeof vi.fn>).mock.calls[0][0]).toBe(`${BASE}/v1/topics`);
    });

    it('appends query params', async () => {
      mockSuccess({ pagination: { total: 0, limit: 5, offset: 0 }, items: [] });
      await getTopics({ q: 'dharma', source: 'manual', limit: 5, offset: 10 });
      const url = (fetch as ReturnType<typeof vi.fn>).mock.calls[0][0] as string;
      expect(url).toContain('q=dharma');
      expect(url).toContain('source=manual');
      expect(url).toContain('limit=5');
      expect(url).toContain('offset=10');
    });

    it('throws ApiError on error', async () => {
      mockError(500);
      await expect(getTopics()).rejects.toThrow(ApiError);
    });
  });

  describe('getTopic', () => {
    it('calls correct URL and returns data', async () => {
      const fixture = {
        id: '1',
        natural_key: 'dharma',
        display_text: [],
        source: 'manual',
        is_leaf: true,
        topic_path: '/dharma',
        parent_keyword: null,
        is_synthetic: false,
        parent_topic: null,
        extracts: [],
      };
      mockSuccess(fixture);
      const result = await getTopic('dharma');
      expect((fetch as ReturnType<typeof vi.fn>).mock.calls[0][0]).toBe(`${BASE}/v1/topics/dharma`);
      expect(result).toEqual(fixture);
    });

    it('throws ApiError on 404', async () => {
      mockError(404);
      await expect(getTopic('missing')).rejects.toThrow(ApiError);
      await expect(getTopic('missing')).rejects.toMatchObject({ status: 404 });
    });
  });

  describe('getGatha', () => {
    it('calls correct URL and returns data', async () => {
      const fixture = {
        id: '1',
        natural_key: 'g-1',
        gatha_number: '1',
        shastra: { natural_key: 'ts', title: [] },
        adhikaar: [],
        heading: [],
        prakrit: null,
        sanskrit: null,
        hindi_chhand: [],
        word_meanings: null,
      };
      mockSuccess(fixture);
      const result = await getGatha('g-1');
      expect((fetch as ReturnType<typeof vi.fn>).mock.calls[0][0]).toBe(`${BASE}/v1/gathas/g-1`);
      expect(result).toEqual(fixture);
    });

    it('throws ApiError on 404', async () => {
      mockError(404);
      await expect(getGatha('missing')).rejects.toThrow(ApiError);
      await expect(getGatha('missing')).rejects.toMatchObject({ status: 404 });
    });
  });

  describe('getGathaRelatedTopics', () => {
    it('calls correct URL', async () => {
      mockSuccess([]);
      await getGathaRelatedTopics('g-1');
      expect((fetch as ReturnType<typeof vi.fn>).mock.calls[0][0]).toBe(
        `${BASE}/v1/gathas/g-1/related-topics`
      );
    });

    it('throws ApiError on error', async () => {
      mockError(404);
      await expect(getGathaRelatedTopics('missing')).rejects.toThrow(ApiError);
    });
  });

  describe('getGathaRelatedKeywords', () => {
    it('calls correct URL', async () => {
      mockSuccess([]);
      await getGathaRelatedKeywords('g-1');
      expect((fetch as ReturnType<typeof vi.fn>).mock.calls[0][0]).toBe(
        `${BASE}/v1/gathas/g-1/related-keywords`
      );
    });

    it('throws ApiError on error', async () => {
      mockError(404);
      await expect(getGathaRelatedKeywords('missing')).rejects.toThrow(ApiError);
    });
  });

  describe('getGatha with include', () => {
    it('appends include query param when provided', async () => {
      const fixture = {
        id: '1', natural_key: 'g-1', gatha_number: '1',
        shastra: { natural_key: 'ts', title: [] },
        adhikaar: [], heading: [], prakrit: null, sanskrit: null,
        hindi_chhand: [], word_meanings: null,
      };
      mockSuccess(fixture);
      await getGatha('g-1', { include: ['teeka_mapping'] });
      const url = (fetch as ReturnType<typeof vi.fn>).mock.calls[0][0] as string;
      expect(url).toBe(`${BASE}/v1/gathas/g-1?include=teeka_mapping`);
    });

    it('does not append include when not provided', async () => {
      const fixture = {
        id: '1', natural_key: 'g-1', gatha_number: '1',
        shastra: { natural_key: 'ts', title: [] },
        adhikaar: [], heading: [], prakrit: null, sanskrit: null,
        hindi_chhand: [], word_meanings: null,
      };
      mockSuccess(fixture);
      await getGatha('g-1');
      const url = (fetch as ReturnType<typeof vi.fn>).mock.calls[0][0] as string;
      expect(url).toBe(`${BASE}/v1/gathas/g-1`);
    });
  });

  describe('getKalash', () => {
    it('calls correct URL and returns data', async () => {
      const fixture = {
        id: 'k-1', natural_key: 'samaysar:amritchandra:kalash:001',
        kalash_number: '001',
        teeka: { id: 't-1', natural_key: 'samaysar:amritchandra', shastra: { natural_key: 'samaysar', title: [] } },
        sanskrit: null, hindi: null, bhaavarth: [],
      };
      mockSuccess(fixture);
      const result = await getKalash('samaysar:amritchandra:kalash:001');
      expect((fetch as ReturnType<typeof vi.fn>).mock.calls[0][0]).toBe(
        `${BASE}/v1/kalashas/samaysar%3Aamritchandra%3Akalash%3A001`
      );
      expect(result).toEqual(fixture);
    });

    it('throws ApiError on 404', async () => {
      mockError(404);
      await expect(getKalash('missing')).rejects.toThrow(ApiError);
    });
  });

  describe('getKalashWordMeanings', () => {
    it('calls correct URL and returns data', async () => {
      const fixture = {
        kalash_id: 'k-1',
        kalash_natural_key: 'samaysar:amritchandra:kalash:001',
        teeka_natural_key: 'samaysar:amritchandra',
        kalash_number: '001',
        entries: [{ source_word: 'स्वानुभूत्या', meaning: 'स्वानुभूति से', position: 1 }],
      };
      mockSuccess(fixture);
      const result = await getKalashWordMeanings('samaysar:amritchandra:kalash:001');
      expect((fetch as ReturnType<typeof vi.fn>).mock.calls[0][0]).toBe(
        `${BASE}/v1/kalashas/samaysar%3Aamritchandra%3Akalash%3A001/word_meanings`
      );
      expect(result).toEqual(fixture);
    });

    it('returns null on 404', async () => {
      mockError(404);
      const result = await getKalashWordMeanings('missing:kalash:001');
      expect(result).toBeNull();
    });

    it('throws ApiError on non-404 error', async () => {
      mockError(500);
      await expect(getKalashWordMeanings('k-1')).rejects.toThrow(ApiError);
    });
  });
});
