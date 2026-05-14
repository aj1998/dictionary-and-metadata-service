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
} from './data';

const BASE = '/api/data';

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
        `/api/metadata/v1/shastras/tattvaartha`
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
    it('calls correct URL and returns data', async () => {
      const fixture = [{ id: '1', natural_key: 'atma', display_text: 'आत्मा' }];
      mockSuccess(fixture);
      const result = await getKeywordsRecent();
      expect((fetch as ReturnType<typeof vi.fn>).mock.calls[0][0]).toBe(`${BASE}/v1/keywords/recent`);
      expect(result).toEqual(fixture);
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
});
