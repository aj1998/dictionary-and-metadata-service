import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
import { ApiError } from './_fetch';
import { searchTopics } from './query';

const BASE = '/api/query';

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
});
