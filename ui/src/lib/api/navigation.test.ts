import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
import { ApiError } from './_fetch';
import { getNavLanding, expandNode, getPreview, getTopicNeighbors } from './navigation';

const BASE = '/api/navigation';

const emptyGraph = {
  nodes: [],
  edges: [],
  focus_nk: '',
  depth: 1,
};

describe('navigation API', () => {
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

  describe('getNavLanding', () => {
    it('calls correct URL and returns graph payload', async () => {
      mockSuccess(emptyGraph);
      const result = await getNavLanding();
      expect((fetch as ReturnType<typeof vi.fn>).mock.calls[0][0]).toBe(`${BASE}/v1/landing`);
      expect(result).toEqual(emptyGraph);
    });

    it('throws ApiError on error', async () => {
      mockError(500);
      await expect(getNavLanding()).rejects.toThrow(ApiError);
      await expect(getNavLanding()).rejects.toMatchObject({ status: 500 });
    });
  });

  describe('expandNode', () => {
    it('calls correct URL with depth param', async () => {
      mockSuccess(emptyGraph);
      await expandNode('dharma', 2);
      expect((fetch as ReturnType<typeof vi.fn>).mock.calls[0][0]).toBe(
        `${BASE}/v1/expand/dharma?depth=2`
      );
    });

    it('includes depth=1 correctly', async () => {
      mockSuccess(emptyGraph);
      await expandNode('atma', 1);
      const url = (fetch as ReturnType<typeof vi.fn>).mock.calls[0][0] as string;
      expect(url).toBe(`${BASE}/v1/expand/atma?depth=1`);
    });

    it('includes depth=4 correctly', async () => {
      mockSuccess(emptyGraph);
      await expandNode('karma', 4);
      const url = (fetch as ReturnType<typeof vi.fn>).mock.calls[0][0] as string;
      expect(url).toBe(`${BASE}/v1/expand/karma?depth=4`);
    });

    it('throws ApiError on error', async () => {
      mockError(404);
      await expect(expandNode('missing', 1)).rejects.toThrow(ApiError);
      await expect(expandNode('missing', 1)).rejects.toMatchObject({ status: 404 });
    });
  });

  describe('getPreview', () => {
    it('calls correct URL without hops when not provided', async () => {
      mockSuccess(emptyGraph);
      await getPreview('dharma');
      expect((fetch as ReturnType<typeof vi.fn>).mock.calls[0][0]).toBe(
        `${BASE}/v1/preview/dharma`
      );
    });

    it('appends hops param when provided', async () => {
      mockSuccess(emptyGraph);
      await getPreview('dharma', 2);
      expect((fetch as ReturnType<typeof vi.fn>).mock.calls[0][0]).toBe(
        `${BASE}/v1/preview/dharma?hops=2`
      );
    });

    it('appends hops=1 correctly', async () => {
      mockSuccess(emptyGraph);
      await getPreview('atma', 1);
      const url = (fetch as ReturnType<typeof vi.fn>).mock.calls[0][0] as string;
      expect(url).toBe(`${BASE}/v1/preview/atma?hops=1`);
    });

    it('throws ApiError on error', async () => {
      mockError(404);
      await expect(getPreview('missing')).rejects.toThrow(ApiError);
      await expect(getPreview('missing')).rejects.toMatchObject({ status: 404 });
    });
  });

  describe('getTopicNeighbors', () => {
    it('calls correct URL and returns response', async () => {
      const fixture = { topic_natural_key: 'dharma', neighbors: [] };
      mockSuccess(fixture);
      const result = await getTopicNeighbors('dharma');
      expect((fetch as ReturnType<typeof vi.fn>).mock.calls[0][0]).toBe(
        `${BASE}/v1/topics/dharma/neighbors`
      );
      expect(result).toEqual(fixture);
    });

    it('throws ApiError on error', async () => {
      mockError(404);
      await expect(getTopicNeighbors('missing')).rejects.toThrow(ApiError);
      await expect(getTopicNeighbors('missing')).rejects.toMatchObject({ status: 404 });
    });
  });
});
