import type { LangText, Paginated } from '@/lib/types';

export function getHindiText(texts: LangText[] | undefined, fallback: string): string {
  if (!texts || texts.length === 0) return fallback;
  return texts.find((text) => text.lang === 'hi')?.text ?? texts[0]?.text ?? fallback;
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
