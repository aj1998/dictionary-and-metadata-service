import type { LangText, Paginated } from '@/lib/types';

export function getHindiText(texts: LangText[] | undefined, fallback: string): string {
  if (!texts || texts.length === 0) return fallback;
  return texts.find((text) => text.lang === 'hi' || text.lang === 'hin')?.text ?? texts[0]?.text ?? fallback;
}

export function buildPageHref(basePath: string, page: number, limit: number): string {
  const offset = Math.max(0, (page - 1) * limit);
  const query = new URLSearchParams({ page: String(page), limit: String(limit), offset: String(offset) });
  return `${basePath}?${query.toString()}`;
}

export function paginatedMeta(pagination: Paginated<unknown>['pagination']) {
  const page = Math.floor(pagination.offset / pagination.limit) + 1;
  const totalPages = Math.max(1, Math.ceil(pagination.total / pagination.limit));
  return {
    page,
    totalPages,
    hasPrevious: page > 1,
    hasNext: page < totalPages,
  };
}

// Hindi particles / stopwords that carry no search meaning on their own. Used
// to keep multi-token search expansion from matching common connectives — e.g.
// the "की" in "द्रव्यों की स्वतंत्रता" would otherwise substring-match nearly
// every topic.
const SEARCH_STOPWORDS = new Set([
  'की', 'के', 'का', 'को', 'कि', 'व', 'में', 'से', 'पर', 'और', 'है', 'हैं',
  'तथा', 'या', 'एवं', 'हेतु', 'एक',
]);

/**
 * Split a query into meaningful search tokens: whitespace-separated, with Hindi
 * particle stopwords and very short (< 3 grapheme) tokens removed.
 */
export function meaningfulTokens(q: string): string[] {
  return q
    .split(/\s+/)
    .filter(Boolean)
    .filter((tok) => !SEARCH_STOPWORDS.has(tok) && [...tok].length >= 3);
}
