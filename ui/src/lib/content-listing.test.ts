import { describe, expect, it } from 'vitest';
import { buildPageHref, getHindiText, paginatedMeta } from './content-listing';

describe('content listing helpers', () => {
  it('returns Hindi text when present', () => {
    expect(
      getHindiText(
        [
          { lang: 'en', script: 'latin', text: 'Soul' },
          { lang: 'hi', script: 'devanagari', text: 'आत्मा' },
        ],
        'fallback'
      )
    ).toBe('आत्मा');
  });

  it('falls back to first available text when Hindi is missing', () => {
    expect(
      getHindiText([{ lang: 'sa', script: 'devanagari', text: 'जीवः' }], 'fallback')
    ).toBe('जीवः');
  });

  it('builds page href with limit and computed offset', () => {
    expect(buildPageHref('/topics', 3, 12)).toContain('offset=24');
  });

  it('computes pagination flags', () => {
    expect(paginatedMeta({ total: 52, limit: 10, offset: 20 })).toEqual({
      page: 3,
      totalPages: 6,
      hasPrevious: true,
      hasNext: true,
    });
  });
});
