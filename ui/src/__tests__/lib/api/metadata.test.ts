import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
import { ApiError } from '@/lib/api/_fetch';
import { getShastras, getShastra, getShastraTeekas } from '@/lib/api/metadata';

const BASE = 'http://localhost:3000/api/metadata';

describe('metadata API', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  describe('getShastras', () => {
    it('calls correct URL with no params', async () => {
      const fixture = { pagination: { total: 1, limit: 20, offset: 0 }, items: [] };
      (fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
        ok: true,
        json: async () => fixture,
      });

      const result = await getShastras();
      expect((fetch as ReturnType<typeof vi.fn>).mock.calls[0][0]).toBe(`${BASE}/v1/shastras`);
      expect(result).toEqual(fixture);
    });

    it('appends query params when provided', async () => {
      (fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
        ok: true,
        json: async () => ({ pagination: { total: 0, limit: 10, offset: 0 }, items: [] }),
      });

      await getShastras({ q: 'test', anuyoga: 'dravya', limit: 10, offset: 5 });
      const url = (fetch as ReturnType<typeof vi.fn>).mock.calls[0][0] as string;
      expect(url).toContain('q=test');
      expect(url).toContain('anuyoga=dravya');
      expect(url).toContain('limit=10');
      expect(url).toContain('offset=5');
    });

    it('throws ApiError on error', async () => {
      (fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
        ok: false,
        status: 500,
        json: async () => ({ error: 'server error' }),
      });

      await expect(getShastras()).rejects.toThrow(ApiError);
      await expect(getShastras()).rejects.toMatchObject({ status: 500 });
    });
  });

  describe('getShastra', () => {
    it('calls correct URL and returns typed data', async () => {
      const fixture = {
        id: '1',
        natural_key: 'tattvaartha-sutra',
        title: [{ lang: 'hi', script: 'devanagari', text: 'तत्त्वार्थसूत्र' }],
      };
      (fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
        ok: true,
        json: async () => fixture,
      });

      const result = await getShastra('tattvaartha-sutra');
      expect((fetch as ReturnType<typeof vi.fn>).mock.calls[0][0]).toBe(
        `${BASE}/v1/shastras/tattvaartha-sutra`
      );
      expect(result).toEqual(fixture);
    });

    it('encodes Devanagari nk', async () => {
      (fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
        ok: true,
        json: async () => ({}),
      });

      await getShastra('आत्मा');
      const url = (fetch as ReturnType<typeof vi.fn>).mock.calls[0][0] as string;
      expect(url).toContain('%E0%A4%86%E0%A4%A4%E0%A5%8D%E0%A4%AE%E0%A4%BE');
    });

    it('throws ApiError on 404', async () => {
      (fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
        ok: false,
        status: 404,
        json: async () => ({ error: 'not found' }),
      });

      await expect(getShastra('missing')).rejects.toThrow(ApiError);
      await expect(getShastra('missing')).rejects.toMatchObject({ status: 404 });
    });
  });

  describe('getShastraTeekas', () => {
    it('returns array response', async () => {
      const fixture = [
        { id: '1', natural_key: 'teeka-1', teekakar: 'Author One' },
      ];
      (fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
        ok: true,
        json: async () => fixture,
      });

      const result = await getShastraTeekas('tattvaartha-sutra');
      expect((fetch as ReturnType<typeof vi.fn>).mock.calls[0][0]).toBe(
        `${BASE}/v1/shastras/tattvaartha-sutra/teekas`
      );
      expect(result).toEqual(fixture);
    });

    it('throws ApiError on error', async () => {
      (fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
        ok: false,
        status: 404,
        json: async () => ({ error: 'not found' }),
      });

      await expect(getShastraTeekas('missing')).rejects.toThrow(ApiError);
    });
  });
});
