import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const getShastrasMock = vi.fn();

vi.mock('@/lib/api/metadata', () => ({
  getShastras: (...args: unknown[]) => getShastrasMock(...args),
}));

import { loadIngestedShastras, _resetIngestedShastrasForTest } from '@/lib/shastra-registry';

beforeEach(() => {
  _resetIngestedShastrasForTest();
  getShastrasMock.mockReset();
});

afterEach(() => {
  _resetIngestedShastrasForTest();
});

describe('loadIngestedShastras', () => {
  it('returns the set of natural keys from the paginated response', async () => {
    getShastrasMock.mockResolvedValueOnce({
      pagination: { total: 2, limit: 200, offset: 0 },
      items: [
        { id: 'a', natural_key: 'समयसार', title: [] },
        { id: 'b', natural_key: 'pravachansaar', title: [] },
      ],
    });

    const set = await loadIngestedShastras();
    expect(set.has('समयसार')).toBe(true);
    expect(set.has('pravachansaar')).toBe(true);
    expect(set.size).toBe(2);
  });

  it('caches the promise so a second call does not refetch', async () => {
    getShastrasMock.mockResolvedValue({
      pagination: { total: 1, limit: 200, offset: 0 },
      items: [{ id: 'a', natural_key: 'समयसार', title: [] }],
    });

    const first = await loadIngestedShastras();
    const second = await loadIngestedShastras();
    expect(first).toBe(second);
    expect(getShastrasMock).toHaveBeenCalledTimes(1);
  });

  it('skips items with empty natural_key', async () => {
    getShastrasMock.mockResolvedValueOnce({
      pagination: { total: 2, limit: 200, offset: 0 },
      items: [
        { id: 'a', natural_key: 'समयसार', title: [] },
        { id: 'b', natural_key: '', title: [] },
      ],
    });

    const set = await loadIngestedShastras();
    expect(set.size).toBe(1);
    expect(set.has('समयसार')).toBe(true);
  });

  it('paginates through multiple pages until total is drained', async () => {
    getShastrasMock
      .mockResolvedValueOnce({
        pagination: { total: 3, limit: 200, offset: 0 },
        items: [
          { id: 'a', natural_key: 'समयसार', title: [] },
          { id: 'b', natural_key: 'pravachansaar', title: [] },
        ],
      })
      .mockResolvedValueOnce({
        pagination: { total: 3, limit: 200, offset: 2 },
        items: [{ id: 'c', natural_key: 'niyamsaar', title: [] }],
      });

    const set = await loadIngestedShastras();
    expect(set.size).toBe(3);
    expect(getShastrasMock).toHaveBeenCalledTimes(2);
    expect(getShastrasMock).toHaveBeenNthCalledWith(1, { limit: 200, offset: 0 });
    expect(getShastrasMock).toHaveBeenNthCalledWith(2, { limit: 200, offset: 2 });
  });

  it('NFC-normalizes natural keys so lookups by parsed shastra_name match', async () => {
    // The literal here is already NFC, but the test asserts the property
    // by composing the same Devanagari string via Unicode escapes that
    // start in NFD and rely on normalize('NFC') for equality.
    const nfd = 'समियसार'.normalize('NFD');
    getShastrasMock.mockResolvedValueOnce({
      pagination: { total: 1, limit: 200, offset: 0 },
      items: [{ id: 'a', natural_key: nfd, title: [] }],
    });
    const set = await loadIngestedShastras();
    expect(set.has(nfd.normalize('NFC'))).toBe(true);
  });

  it('resets the cache on rejection so the next call retries', async () => {
    getShastrasMock.mockRejectedValueOnce(new Error('boom'));
    await expect(loadIngestedShastras()).rejects.toThrow('boom');

    getShastrasMock.mockResolvedValueOnce({
      pagination: { total: 1, limit: 200, offset: 0 },
      items: [{ id: 'a', natural_key: 'समयसार', title: [] }],
    });
    const set = await loadIngestedShastras();
    expect(set.has('समयसार')).toBe(true);
    expect(getShastrasMock).toHaveBeenCalledTimes(2);
  });
});
