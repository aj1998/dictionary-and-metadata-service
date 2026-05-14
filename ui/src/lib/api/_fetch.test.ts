import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
import { apiFetch, ApiError } from './_fetch';

describe('apiFetch', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('returns parsed JSON on success', async () => {
    const fixture = { foo: 'bar' };
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: true,
      json: async () => fixture,
    });

    const result = await apiFetch<typeof fixture>('http://localhost:8001', '/v1/test');
    expect(result).toEqual(fixture);
  });

  it('calls the correct URL', async () => {
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: true,
      json: async () => ({}),
    });

    await apiFetch('http://localhost:8001', '/v1/shastras');
    expect((fetch as ReturnType<typeof vi.fn>).mock.calls[0][0]).toBe(
      'http://localhost:8001/v1/shastras'
    );
  });

  it('throws ApiError with correct status on 4xx', async () => {
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: false,
      status: 404,
      json: async () => ({ error: 'not found' }),
    });

    await expect(apiFetch('http://localhost:8001', '/v1/missing')).rejects.toThrow(ApiError);
    await expect(apiFetch('http://localhost:8001', '/v1/missing')).rejects.toMatchObject({
      status: 404,
      body: { error: 'not found' },
    });
  });

  it('throws ApiError with correct status on 5xx', async () => {
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: false,
      status: 500,
      json: async () => ({ error: 'server error' }),
    });

    await expect(apiFetch('http://localhost:8001', '/v1/broken')).rejects.toThrow(ApiError);
    await expect(apiFetch('http://localhost:8001', '/v1/broken')).rejects.toMatchObject({
      status: 500,
    });
  });

  it('percent-encodes Devanagari path segments', async () => {
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: true,
      json: async () => ({}),
    });

    await apiFetch('http://localhost:8002', '/v1/keywords/आत्मा');
    const calledUrl = (fetch as ReturnType<typeof vi.fn>).mock.calls[0][0] as string;
    expect(calledUrl).toBe('http://localhost:8002/v1/keywords/%E0%A4%86%E0%A4%A4%E0%A5%8D%E0%A4%AE%E0%A4%BE');
  });

  it('handles trailing slash on baseUrl', async () => {
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: true,
      json: async () => ({}),
    });

    await apiFetch('http://localhost:8001/', '/v1/shastras');
    expect((fetch as ReturnType<typeof vi.fn>).mock.calls[0][0]).toBe(
      'http://localhost:8001/v1/shastras'
    );
  });

  it('sets body to null when error response has no JSON', async () => {
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: false,
      status: 503,
      json: async () => { throw new Error('no json'); },
    });

    await expect(apiFetch('http://localhost:8001', '/v1/down')).rejects.toMatchObject({
      status: 503,
      body: null,
    });
  });
});
