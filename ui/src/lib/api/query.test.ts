import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
import { ApiError } from './_fetch';
import { searchTopics, topicsMatch, graphragTopics } from './query';

const BASE = 'http://localhost:3000/api/query';

describe('query API', () => {
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

  describe('searchTopics', () => {
    it('uses POST method', async () => {
      mockSuccess({ results: [] });
      await searchTopics({ q: 'dharma' });
      const [, init] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0];
      expect((init as RequestInit).method).toBe('POST');
    });

    it('calls correct URL', async () => {
      mockSuccess({ results: [] });
      await searchTopics({ q: 'dharma' });
      expect((fetch as ReturnType<typeof vi.fn>).mock.calls[0][0]).toBe(
        `${BASE}/v1/graphrag/topics`
      );
    });

    it('sends correct JSON body with q', async () => {
      mockSuccess({ results: [] });
      await searchTopics({ q: 'dharma' });
      const [, init] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0];
      const body = JSON.parse((init as RequestInit).body as string);
      expect(body.q).toBe('dharma');
    });

    it('defaults caller to public-ui', async () => {
      mockSuccess({ results: [] });
      await searchTopics({ q: 'dharma' });
      const [, init] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0];
      const body = JSON.parse((init as RequestInit).body as string);
      expect(body.caller).toBe('public-ui');
    });

    it('uses provided caller when given', async () => {
      mockSuccess({ results: [] });
      await searchTopics({ q: 'dharma', caller: 'admin-ui' });
      const [, init] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0];
      const body = JSON.parse((init as RequestInit).body as string);
      expect(body.caller).toBe('admin-ui');
    });

    it('returns search response', async () => {
      const fixture = {
        results: [
          {
            topic_nk: 'dharma',
            title_hi: 'धर्म',
            overlap: { matched: 1, total: 1 },
            score: 0.9,
            matched_tokens: ['dharma'],
            excerpt: 'Test excerpt',
            mentions: [],
          },
        ],
      };
      mockSuccess(fixture);
      const result = await searchTopics({ q: 'dharma' });
      expect(result).toEqual(fixture);
    });

    it('sets Content-Type header', async () => {
      mockSuccess({ results: [] });
      await searchTopics({ q: 'test' });
      const [, init] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0];
      expect((init as RequestInit).headers).toMatchObject({
        'Content-Type': 'application/json',
      });
    });

    it('throws ApiError on error', async () => {
      mockError(500);
      await expect(searchTopics({ q: 'dharma' })).rejects.toThrow(ApiError);
      await expect(searchTopics({ q: 'dharma' })).rejects.toMatchObject({ status: 500 });
    });
  });

  describe('topicsMatch', () => {
    it('uses POST method', async () => {
      mockSuccess({ matches: [], tool_trace_id: 'abc' });
      await topicsMatch({ phrase: 'द्रव्य' });
      const [, init] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0];
      expect((init as RequestInit).method).toBe('POST');
    });

    it('calls correct URL', async () => {
      mockSuccess({ matches: [], tool_trace_id: 'abc' });
      await topicsMatch({ phrase: 'द्रव्य' });
      expect((fetch as ReturnType<typeof vi.fn>).mock.calls[0][0]).toBe(
        `${BASE}/v1/query/topics_match`
      );
    });

    it('sends phrase in body', async () => {
      mockSuccess({ matches: [], tool_trace_id: 'abc' });
      await topicsMatch({ phrase: 'द्रव्य स्वतंत्रता' });
      const [, init] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0];
      const body = JSON.parse((init as RequestInit).body as string);
      expect(body.phrase).toBe('द्रव्य स्वतंत्रता');
    });

    it('sends keywords array in body', async () => {
      mockSuccess({ matches: [], tool_trace_id: 'abc' });
      await topicsMatch({ keywords: ['द्रव्य', 'गुण'] });
      const [, init] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0];
      const body = JSON.parse((init as RequestInit).body as string);
      expect(body.keywords).toEqual(['द्रव्य', 'गुण']);
    });

    it('defaults limit to 10', async () => {
      mockSuccess({ matches: [], tool_trace_id: 'abc' });
      await topicsMatch({ phrase: 'test' });
      const [, init] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0];
      const body = JSON.parse((init as RequestInit).body as string);
      expect(body.limit).toBe(10);
    });

    it('defaults min_similarity to 0.3', async () => {
      mockSuccess({ matches: [], tool_trace_id: 'abc' });
      await topicsMatch({ phrase: 'test' });
      const [, init] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0];
      const body = JSON.parse((init as RequestInit).body as string);
      expect(body.min_similarity).toBe(0.3);
    });

    it('passes include_extracts and include_references', async () => {
      mockSuccess({ matches: [], tool_trace_id: 'abc' });
      await topicsMatch({ phrase: 'test', includeExtracts: true, includeReferences: true });
      const [, init] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0];
      const body = JSON.parse((init as RequestInit).body as string);
      expect(body.include_extracts).toBe(true);
      expect(body.include_references).toBe(true);
    });

    it('returns TopicsMatchResponse', async () => {
      const fixture = {
        matches: [
          {
            topic_natural_key: 'द्रव्य/स्वतंत्रता',
            topic_pg_id: 'uuid-1',
            display_text_hi: 'स्वतंत्रता',
            ancestors_hi: ['द्रव्य'],
            is_leaf: true,
            source: 'jainkosh',
            similarity: 0.71,
            score: 0.71,
            extracts_hi: null,
            references: null,
          },
        ],
        tool_trace_id: 'trace-123',
      };
      mockSuccess(fixture);
      const result = await topicsMatch({ phrase: 'द्रव्य स्वतंत्रता' });
      expect(result.matches).toHaveLength(1);
      expect(result.matches[0].topic_natural_key).toBe('द्रव्य/स्वतंत्रता');
      expect(result.matches[0].ancestors_hi).toEqual(['द्रव्य']);
    });

    it('throws ApiError on 422', async () => {
      mockError(422);
      await expect(topicsMatch({ phrase: 'test' })).rejects.toThrow(ApiError);
    });

    it('passes leaf_only flag', async () => {
      mockSuccess({ matches: [], tool_trace_id: 'abc' });
      await topicsMatch({ phrase: 'test', leafOnly: true });
      const [, init] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0];
      const body = JSON.parse((init as RequestInit).body as string);
      expect(body.leaf_only).toBe(true);
    });
  });

  describe('graphragTopics', () => {
    it('uses POST method', async () => {
      mockSuccess({ ranked_topics: [], unresolved_tokens: [], tool_trace_id: 'abc' });
      await graphragTopics({ tokens: ['द्रव्य'] });
      const [, init] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0];
      expect((init as RequestInit).method).toBe('POST');
    });

    it('calls correct URL', async () => {
      mockSuccess({ ranked_topics: [], unresolved_tokens: [], tool_trace_id: 'abc' });
      await graphragTopics({ tokens: ['द्रव्य'] });
      expect((fetch as ReturnType<typeof vi.fn>).mock.calls[0][0]).toBe(
        `${BASE}/v1/query/graphrag`
      );
    });

    it('sends tokens in body', async () => {
      mockSuccess({ ranked_topics: [], unresolved_tokens: [], tool_trace_id: 'abc' });
      await graphragTopics({ tokens: ['द्रव्य', 'गुण'] });
      const [, init] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0];
      const body = JSON.parse((init as RequestInit).body as string);
      expect(body.tokens).toEqual(['द्रव्य', 'गुण']);
    });

    it('defaults max_hops to 2', async () => {
      mockSuccess({ ranked_topics: [], unresolved_tokens: [], tool_trace_id: 'abc' });
      await graphragTopics({ tokens: ['test'] });
      const [, init] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0];
      const body = JSON.parse((init as RequestInit).body as string);
      expect(body.max_hops).toBe(2);
    });

    it('defaults fuzzy to false', async () => {
      mockSuccess({ ranked_topics: [], unresolved_tokens: [], tool_trace_id: 'abc' });
      await graphragTopics({ tokens: ['test'] });
      const [, init] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0];
      const body = JSON.parse((init as RequestInit).body as string);
      expect(body.fuzzy).toBe(false);
    });

    it('returns GraphRAGResponse', async () => {
      const fixture = {
        ranked_topics: [
          {
            topic_natural_key: 'द्रव्य/स्वतंत्रता',
            topic_pg_id: 'uuid-1',
            display_text_hi: 'स्वतंत्रता',
            ancestors_hi: ['द्रव्य'],
            score: 23.5,
            overlap_count: 2,
            matched_seed_keywords: ['द्रव्य'],
            is_leaf: true,
            source: 'jainkosh',
            extracts_hi: null,
            references: null,
            neighbors: null,
          },
        ],
        unresolved_tokens: [],
        tool_trace_id: 'trace-456',
      };
      mockSuccess(fixture);
      const result = await graphragTopics({ tokens: ['द्रव्य'] });
      expect(result.ranked_topics).toHaveLength(1);
      expect(result.ranked_topics[0].overlap_count).toBe(2);
      expect(result.unresolved_tokens).toEqual([]);
    });

    it('throws ApiError on error', async () => {
      mockError(500);
      await expect(graphragTopics({ tokens: ['test'] })).rejects.toThrow(ApiError);
    });
  });
});
