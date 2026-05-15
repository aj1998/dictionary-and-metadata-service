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

  it('resolves relative base URLs on the server to localhost origin by default', async () => {
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: true,
      json: async () => ({}),
    });

    await apiFetch('/api/data', '/v1/stats/counts');
    expect((fetch as ReturnType<typeof vi.fn>).mock.calls[0][0]).toBe(
      'http://localhost:3000/api/data/v1/stats/counts'
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

// ─── Bug 3: 404 classification for graceful handling in DetailsPanel ──────────
//
// DetailsPanel checks `err instanceof ApiError && err.status === 404` to decide
// whether to suppress console.error.  These tests lock the ApiError shape so
// that the check remains valid if the class is ever refactored.

describe('ApiError 404 classification', () => {
  it('is an instance of ApiError', () => {
    const err = new ApiError(404, { error: 'not found' }, 'API 404: /v1/keywords/foo');
    expect(err).toBeInstanceOf(ApiError);
    expect(err).toBeInstanceOf(Error);
  });

  it('exposes status 404 as a numeric property', () => {
    const err = new ApiError(404, null, 'not found');
    expect(err.status).toBe(404);
  });

  it('distinguishes 404 from other error statuses', () => {
    const err404 = new ApiError(404, null, 'not found');
    const err500 = new ApiError(500, null, 'server error');
    expect(err404.status === 404).toBe(true);
    expect(err500.status === 404).toBe(false);
  });

  it('carries the original body payload', () => {
    const body = { detail: 'keyword does not exist' };
    const err = new ApiError(404, body, 'API 404: /v1/keywords/सामान्य');
    expect(err.body).toEqual(body);
  });

  it('the 404 guard pattern used in DetailsPanel evaluates correctly', () => {
    // Mirrors: err instanceof ApiError && err.status === 404
    const shouldSuppress = (err: unknown) =>
      err instanceof ApiError && err.status === 404;

    expect(shouldSuppress(new ApiError(404, null, ''))).toBe(true);
    expect(shouldSuppress(new ApiError(500, null, ''))).toBe(false);
    expect(shouldSuppress(new Error('plain error'))).toBe(false);
    expect(shouldSuppress('string error')).toBe(false);
  });
});
