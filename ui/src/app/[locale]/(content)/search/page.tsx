import { Link } from '@/i18n/navigation';
import { BookOpen, ScrollText, Sparkles, Tag } from '@/lib/icons';
import { getKeywords, getTopics } from '@/lib/api/data';
import { getShastras } from '@/lib/api/metadata';
import { TopicNavAction } from '@/components/TopicNavAction';
import { normalizeNFC, toDevanagariNumerals } from '@/lib/format/devanagari';
import { getLocale, getTranslations } from 'next-intl/server';
import type { KeywordSummary, ShastraSummary, TopicSummary } from '@/lib/types';

export const revalidate = 0;

type PageProps = {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
};

function first(value: string | string[] | undefined): string {
  if (Array.isArray(value)) return value[0] ?? '';
  return value ?? '';
}

const LIMIT = 8;

function norm(s: string): string {
  return normalizeNFC(s).trim().toLowerCase();
}

function topicLeafName(t: TopicSummary): string {
  const hi = t.display_text.find((r) => r.lang === 'hi')?.text?.trim();
  if (hi && !hi.includes(':')) return hi;
  const segments = (hi && hi.includes(':') ? hi : t.natural_key).split(':');
  const last = segments[segments.length - 1] ?? t.natural_key;
  return last.replace(/-/g, ' ');
}

function shastraHi(s: ShastraSummary): string {
  return s.title.find((r) => r.lang === 'hi')?.text ?? s.natural_key;
}

async function fetchKeywords(q: string): Promise<KeywordSummary[]> {
  try {
    const r = await getKeywords({ q, limit: LIMIT });
    return r.items ?? [];
  } catch (e) {
    console.error('search: keywords failed', e);
    return [];
  }
}
async function fetchTopics(q: string): Promise<TopicSummary[]> {
  try {
    const r = await getTopics({ q, limit: LIMIT });
    return r.items ?? [];
  } catch (e) {
    console.error('search: topics failed', e);
    return [];
  }
}
async function fetchShastras(q: string): Promise<ShastraSummary[]> {
  try {
    const r = await getShastras({ q, limit: LIMIT });
    return r.items ?? [];
  } catch (e) {
    console.error('search: shastras failed', e);
    return [];
  }
}

export default async function SearchPage({ searchParams }: PageProps) {
  const query = await searchParams;
  const q = first(query.q).trim();
  const [t, locale] = await Promise.all([getTranslations('search'), getLocale()]);
  const isHi = locale === 'hi';
  const fontHi = isHi ? 'font-serif-hindi' : 'font-sans';

  const [keywords, topics, shastras] = q
    ? await Promise.all([fetchKeywords(q), fetchTopics(q), fetchShastras(q)])
    : [[], [], []];

  const nq = norm(q);
  const exactKeyword = keywords.find((k) => norm(k.display_text) === nq);
  const exactTopic = topics.find((tp) => norm(topicLeafName(tp)) === nq);
  const exactShastra = shastras.find((s) => norm(shastraHi(s)) === nq);
  const anyExact = exactKeyword ?? exactTopic ?? exactShastra;

  const hasAny = keywords.length + topics.length + shastras.length > 0;

  return (
    <div className="space-y-6">
      <div className="rounded-[var(--radius-md)] border border-border bg-surface p-6 shadow-node">
        <form className="mx-auto flex max-w-3xl gap-3">
          <input
            autoFocus
            name="q"
            defaultValue={q}
            placeholder={t('placeholder')}
            className="h-14 flex-1 rounded-full border border-border bg-background px-5 text-base outline-none focus:border-accent focus:ring-2 focus:ring-[var(--ring)]"
          />
          <button
            type="submit"
            className="inline-flex h-14 items-center justify-center rounded-full bg-accent px-6 font-semibold text-white hover:bg-accent-hover"
          >
            {t('button')}
          </button>
        </form>

        {!q && (
          <p className="mt-6 text-center text-sm text-foreground-muted">{t('hint')}</p>
        )}

        {q && !hasAny && (
          <p className="mt-6 text-center text-sm text-foreground-muted">{t('empty')}</p>
        )}

        {q && anyExact && (
          <div className="mt-6 rounded-[var(--radius-md)] border border-accent/40 bg-accent-soft p-4">
            <p className="text-xs font-semibold uppercase tracking-wide text-accent">{t('exact_match')}</p>
            <div className="mt-2">
              {exactKeyword && (
                <Link href={`/dictionary/${exactKeyword.natural_key}`} className={`${fontHi} text-[length:var(--font-size-h2)] font-semibold text-foreground hover:text-accent`}>
                  {exactKeyword.display_text}
                </Link>
              )}
              {!exactKeyword && exactTopic && (
                <TopicNavAction topicNk={exactTopic.natural_key} displayText={topicLeafName(exactTopic)} variant="inline" />
              )}
              {!exactKeyword && !exactTopic && exactShastra && (
                <Link href={`/shastras/${exactShastra.natural_key}`} className={`${fontHi} text-[length:var(--font-size-h2)] font-semibold text-foreground hover:text-accent`}>
                  {shastraHi(exactShastra)}
                </Link>
              )}
            </div>
          </div>
        )}
      </div>

      {q && hasAny && (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
          <SectionCard
            title={t('section_keywords')}
            icon={<BookOpen className="size-4" strokeWidth={1.5} />}
            viewAllHref={`/dictionary?q=${encodeURIComponent(q)}`}
            viewAllLabel={t('view_all')}
            empty={t('no_section_results')}
            count={keywords.length}
            fontHi={fontHi}
          >
            {keywords.map((k) => (
              <Link
                key={k.id}
                href={`/dictionary/${k.natural_key}`}
                className="block rounded-[var(--radius-sm)] border border-border bg-background px-3 py-2 text-sm hover:bg-accent-soft hover:border-accent/30"
              >
                <span className={`${fontHi} font-medium`}>{k.display_text}</span>
              </Link>
            ))}
          </SectionCard>

          <SectionCard
            title={t('section_topics')}
            icon={<Tag className="size-4" strokeWidth={1.5} />}
            viewAllHref={`/topics?q=${encodeURIComponent(q)}`}
            viewAllLabel={t('view_all')}
            empty={t('no_section_results')}
            count={topics.length}
            fontHi={fontHi}
          >
            {topics.map((tp) => {
              const name = topicLeafName(tp);
              const hasExtracts = tp.extract_count > 0 || !!tp.topic_path;
              const parentKw = tp.parent_keyword?.natural_key;
              const href = parentKw
                ? `/dictionary/${parentKw}?topic=${encodeURIComponent(tp.natural_key)}`
                : null;
              return (
                <div
                  key={tp.id}
                  className="flex items-center justify-between gap-2 rounded-[var(--radius-sm)] border border-border bg-background px-3 py-2 text-sm hover:bg-accent-soft hover:border-accent/30"
                >
                  {href ? (
                    <Link href={href} className={`${fontHi} min-w-0 flex-1 truncate font-medium text-foreground hover:text-accent`}>
                      {name}
                    </Link>
                  ) : (
                    <span className={`${fontHi} min-w-0 flex-1 truncate font-medium`}>{name}</span>
                  )}
                  <div className="flex shrink-0 items-center gap-2">
                    {hasExtracts && (
                      <TopicNavAction
                        topicNk={tp.natural_key}
                        displayText={name}
                        isLeaf={true}
                        parentKeywordNk={parentKw}
                        variant="inline"
                        className="inline-flex items-center gap-1 text-xs font-medium text-accent hover:underline"
                      />
                    )}
                    {tp.extract_count > 0 && (
                      <span className="rounded-full bg-accent-soft px-2 py-0.5 font-mono text-xs text-accent">
                        {isHi ? toDevanagariNumerals(tp.extract_count) : tp.extract_count}
                      </span>
                    )}
                  </div>
                </div>
              );
            })}
          </SectionCard>

          <SectionCard
            title={t('section_shastras')}
            icon={<ScrollText className="size-4" strokeWidth={1.5} />}
            viewAllHref={`/shastras?q=${encodeURIComponent(q)}`}
            viewAllLabel={t('view_all')}
            empty={t('no_section_results')}
            count={shastras.length}
            fontHi={fontHi}
          >
            {shastras.map((s) => (
              <Link
                key={s.id}
                href={`/shastras/${s.natural_key}`}
                className="block rounded-[var(--radius-sm)] border border-border bg-background px-3 py-2 text-sm hover:bg-accent-soft hover:border-accent/30"
              >
                <span className={`${fontHi} font-medium`}>{shastraHi(s)}</span>
              </Link>
            ))}
          </SectionCard>
        </div>
      )}
    </div>
  );
}

function SectionCard({
  title,
  icon,
  children,
  viewAllHref,
  viewAllLabel,
  empty,
  count,
  fontHi,
}: {
  title: string;
  icon: React.ReactNode;
  children: React.ReactNode;
  viewAllHref: string;
  viewAllLabel: string;
  empty: string;
  count: number;
  fontHi: string;
}) {
  return (
    <section className="flex flex-col rounded-[var(--radius-md)] border border-border bg-surface p-5 shadow-node">
      <header className="mb-3 flex items-center justify-between">
        <h2 className={`${fontHi} flex items-center gap-2 text-[length:var(--font-size-h3)] font-semibold`}>
          <span className="text-accent">{icon}</span>
          {title}
        </h2>
        {count > 0 && (
          <Link href={viewAllHref} className="text-xs font-medium text-accent hover:underline">
            {viewAllLabel}
          </Link>
        )}
      </header>
      {count === 0 ? (
        <div className="flex flex-1 items-center justify-center py-6 text-center text-xs text-foreground-muted">
          <span className="flex items-center gap-2"><Sparkles className="size-3.5" strokeWidth={1.5} />{empty}</span>
        </div>
      ) : (
        <div className="space-y-2">{children}</div>
      )}
    </section>
  );
}
