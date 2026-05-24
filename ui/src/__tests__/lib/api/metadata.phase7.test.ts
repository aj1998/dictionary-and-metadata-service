import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
import { getShastraGathas } from '@/lib/api/metadata';

const BASE = 'http://localhost:3000/api/metadata';

describe('metadata phase7 API', () => {
  beforeEach(() => vi.stubGlobal('fetch', vi.fn()));
  afterEach(() => vi.unstubAllGlobals());

  it('calls shastra gathas endpoint with pagination params', async () => {
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: true,
      json: async () => ({ pagination: { total: 0, limit: 24, offset: 0 }, items: [] }),
    });

    await getShastraGathas('tattvartha', { limit: 24, offset: 0 });
    const url = (fetch as ReturnType<typeof vi.fn>).mock.calls[0][0] as string;
    expect(url).toBe(`${BASE}/v1/shastras/tattvartha/gathas?limit=24&offset=0`);
  });
});
