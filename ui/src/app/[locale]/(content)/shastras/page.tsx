import { Link } from '@/i18n/navigation';
import { getShastras } from '@/lib/api/metadata';
import { getGathasByShastraId } from '@/lib/api/data';
import { getHindiText, paginatedMeta } from '@/lib/content-listing';
import { toDevanagariNumerals } from '@/lib/format/devanagari';
import { getLocale, getTranslations } from 'next-intl/server';
import type { AuthorSummary } from '@/lib/types';

function getAuthorName(author: AuthorSummary | string | null | undefined): string {
  if (!author) return 'अज्ञात';
  if (typeof author === 'string') return author;
  return getHindiText(author.display_name, author.natural_key);
}

export const revalidate = 60;

type PageProps = {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
};

const PAGE_SIZE = 9;

function first(value: string | string[] | undefined): string {
  if (Array.isArray(value)) return value[0] ?? '';
  return value ?? '';
}

export default async function ShastrasPage({ searchParams }: PageProps) {
  const query = await searchParams;
  const q = first(query.q).trim();
  const anuyoga = first(query.anuyoga).trim();
  const page = Math.max(1, Number.parseInt(first(query.page), 10) || 1);
  const offset = (page - 1) * PAGE_SIZE;
  const [tS, tP, locale] = await Promise.all([
    getTranslations('shastras'),
    getTranslations('pagination'),
    getLocale(),
  ]);
  const isHi = locale === 'hi';
  const num = (n: number) => (isHi ? toDevanagariNumerals(n) : String(n));

  const shastras = await getShastras({ q: q || undefined, anuyoga: anuyoga || undefined, limit: PAGE_SIZE, offset });
  const meta = paginatedMeta(shastras.pagination);

  const gathaCounts = await Promise.all(
    shastras.items.map((s) =>
      getGathasByShastraId(s.id, { limit: 1, offset: 0 })
        .then((r) => r.pagination.total)
        .catch(() => 0)
    )
  );

  const makeHref = (nextPage: number) => {
    const params = new URLSearchParams();
    if (q) params.set('q', q);
    if (anuyoga) params.set('anuyoga', anuyoga);
    params.set('page', String(nextPage));
    return `/shastras?${params.toString()}`;
  };

  return (
    <div className="space-y-5">
      <form className="sticky top-[72px] z-10 rounded-[var(--radius-md)] border border-border bg-surface p-4 shadow-node">
        <div className="grid grid-cols-1 gap-3 md:grid-cols-4">
          <input name="q" defaultValue={q} placeholder={tS('search_within')} className="h-10 rounded-[var(--radius-md)] border border-border bg-background px-3 text-sm" />
          <select name="anuyoga" defaultValue={anuyoga} className="h-10 rounded-[var(--radius-md)] border border-border bg-background px-3 text-sm">
            <option value="">{tS('all_anuyoga')}</option>
            <option value="charananuyoga">चर्यानुयोग</option>
            <option value="dravyanuyoga">द्रव्यानुयोग</option>
            <option value="kathanuyoga">कथानुयोग</option>
          </select>
          <div className="h-10 rounded-[var(--radius-md)] border border-border bg-background px-3 text-sm leading-10 text-foreground-muted">{tS('sort_label')}</div>
          <button type="submit" className="h-10 rounded-[var(--radius-md)] bg-accent px-4 text-sm font-semibold text-white">{isHi ? 'लागू करें' : 'Apply'}</button>
        </div>
      </form>

      <section className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
        {shastras.items.map((item, i) => (
          <article key={item.id} className="rounded-[var(--radius-md)] border border-border bg-surface p-5 shadow-node">
            <h2 className="font-serif-hindi text-[length:var(--font-size-h3)] font-semibold">{getHindiText(item.title, item.natural_key)}</h2>
            <p className="mt-1 text-sm text-foreground-muted">{getAuthorName(item.author)}</p>
            <div className="mt-2 flex flex-wrap gap-2">
              {(item.anuyogas ?? []).slice(0, 3).map((tag) => (
                <span key={tag} className="rounded-full bg-accent-soft px-2 py-1 text-xs text-accent">{tag}</span>
              ))}
            </div>
            <div className="mt-4 flex items-center justify-between">
              <span className="font-serif-hindi text-[length:var(--font-size-h2)] font-semibold text-accent">
                {num(gathaCounts[i] ?? 0)}
                <span className="ml-2 text-xs font-normal text-foreground-muted">{tS('gathas')}</span>
              </span>
              <Link href={`/shastras/${item.natural_key}`} className="rounded-[var(--radius-sm)] border border-accent px-3 py-1 text-sm font-medium text-accent">{tS('open')}</Link>
            </div>
          </article>
        ))}
      </section>

      <div className="flex items-center justify-center gap-3 text-sm">
        {meta.hasPrevious ? <Link href={makeHref(meta.page - 1)} className="rounded border border-border px-3 py-1">{tP('prev')}</Link> : <span className="rounded border border-border px-3 py-1 text-foreground-subtle">{tP('prev')}</span>}
        <span>{tP('page')} {num(meta.page)} / {num(meta.totalPages)}</span>
        {meta.hasNext ? <Link href={makeHref(meta.page + 1)} className="rounded border border-border px-3 py-1">{tP('next')}</Link> : <span className="rounded border border-border px-3 py-1 text-foreground-subtle">{tP('next')}</span>}
      </div>
    </div>
  );
}
