import { Link } from '@/i18n/navigation';
import { getKeywords, getKeywordsLetters, getKeywordsRecent } from '@/lib/api/data';
import { toDevanagariNumerals } from '@/lib/format/devanagari';
import { getLocale, getTranslations } from 'next-intl/server';
import type { KeywordSummary } from '@/lib/types';

export const revalidate = 60;

type PageProps = {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
};

function first(value: string | string[] | undefined): string {
  if (Array.isArray(value)) return value[0] ?? '';
  return value ?? '';
}

export default async function DictionaryPage({ searchParams }: PageProps) {
  const sp = await searchParams;
  const q = first(sp.q).trim();

  const [letters, recentKeywords, t, tSearch, locale] = await Promise.all([
    getKeywordsLetters(),
    getKeywordsRecent(),
    getTranslations('dictionary'),
    getTranslations('search'),
    getLocale(),
  ]);
  const isHi = locale === 'hi';
  const num = (n: number) => (isHi ? toDevanagariNumerals(n) : String(n));

  let matches: KeywordSummary[] = [];
  let searchError = '';
  if (q) {
    try {
      const r = await getKeywords({ q, limit: 30 });
      matches = r.items ?? [];
    } catch (e) {
      console.error('dictionary search failed', e);
      searchError = tSearch('error');
    }
  }

  return (
    <div className="grid grid-cols-1 gap-6 xl:grid-cols-[1fr_320px]">
      <section className="rounded-[var(--radius-md)] border border-border bg-surface p-5 shadow-node">
        <h1 className={`${isHi ? 'font-serif-hindi' : 'font-sans'} text-[length:var(--font-size-h1)] font-semibold`}>{t('title')}</h1>

        <form className="mt-4 flex gap-2" role="search">
          <input
            name="q"
            defaultValue={q}
            placeholder={t('search_within')}
            className="h-11 flex-1 rounded-full border border-border bg-background px-4 text-sm outline-none focus:border-accent focus:ring-2 focus:ring-[var(--ring)]"
          />
          <button
            type="submit"
            className="inline-flex h-11 items-center justify-center rounded-full bg-accent px-5 text-sm font-semibold text-white hover:bg-accent-hover"
          >
            {tSearch('button')}
          </button>
        </form>

        {q && searchError && (
          <p className="mt-4 rounded border border-danger/30 bg-danger/10 p-3 text-sm text-danger">{searchError}</p>
        )}

        {q && !searchError && (
          <div className="mt-5">
            {matches.length === 0 ? (
              <p className="text-sm text-foreground-muted">{tSearch('empty')}</p>
            ) : (
              <ul className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
                {matches.map((k) => (
                  <li key={k.id}>
                    <Link
                      href={`/dictionary/${k.natural_key}`}
                      className="block rounded-[var(--radius-sm)] border border-border bg-background px-3 py-2 text-sm hover:bg-accent-soft hover:border-accent/30"
                    >
                      <span className={`${isHi ? 'font-serif-hindi' : 'font-sans'} font-medium`}>{k.display_text}</span>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}

        {!q && (
          <div className="mt-6 grid grid-cols-4 gap-3 md:grid-cols-6 xl:grid-cols-8">
            {letters.map((entry) => (
              <Link
                key={entry.letter}
                href={`/dictionary/letters/${encodeURIComponent(entry.letter)}`}
                className="flex h-24 flex-col items-center justify-center rounded-[var(--radius-md)] border border-border bg-background transition-colors hover:bg-accent-soft"
              >
                <span className="font-serif-hindi text-[length:var(--font-size-display)] font-semibold">{entry.letter}</span>
                <span className="text-xs text-foreground-muted">{num(entry.count)}</span>
              </Link>
            ))}
          </div>
        )}
      </section>

      <aside className="rounded-[var(--radius-md)] border border-border bg-surface p-5 shadow-node">
        <h2 className={`${isHi ? 'font-serif-hindi' : 'font-sans'} text-[length:var(--font-size-h3)] font-semibold`}>{t('recent')}</h2>
        <ul className="mt-3 space-y-2">
          {recentKeywords.slice(0, 10).map((keyword) => (
            <li key={keyword.id}>
              <Link href={`/dictionary/${keyword.natural_key}`} className="block rounded-[var(--radius-sm)] border border-border px-3 py-2 text-sm hover:bg-surface-muted">
                {keyword.display_text}
              </Link>
            </li>
          ))}
        </ul>
      </aside>
    </div>
  );
}
