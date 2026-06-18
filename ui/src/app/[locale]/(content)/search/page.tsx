import { Link } from '@/i18n/navigation';
import { BookOpen, ScrollText, Sparkles, Tag } from '@/lib/icons';
import { keywordResolveBatch, topicsMatch } from '@/lib/api/query';
import { getShastras } from '@/lib/api/metadata';
import { TopicNavAction } from '@/components/TopicNavAction';
import { meaningfulTokens } from '@/lib/content-listing';
import { normalizeNFC, toDevanagariNumerals } from '@/lib/format/devanagari';
import { getLocale, getTranslations } from 'next-intl/server';
import type { ShastraSummary, TopicMatchItem } from '@/lib/types';

type KeywordResult = { natural_key: string; display_text: string };

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

function shastraHi(s: ShastraSummary): string {
  return s.title.find((r) => r.lang === 'hi')?.text ?? s.natural_key;
}

/**
 * Build the list of search terms for a query. Always includes the full phrase;
 * for multi-word queries it also adds each meaningful (non-stopword) token, so
 * "विभाव पर्याय" resolves both विभाव and पर्याय while "द्रव्यों की स्वतंत्रता"
 * does not fan out on the particle "की".
 */
function searchTerms(q: string): string[] {
  const tokens = meaningfulTokens(q);
  const terms = tokens.length > 1 ? [q, ...tokens] : [q];
  return Array.from(new Set(terms));
}

async function fetchKeywords(q: string): Promise<KeywordResult[]> {
  try {
    // Query engine keyword resolution (01_keyword_resolve_api): per-token
    // exact → alias → suffix-strip → fuzzy. So "द्रव्यों" resolves to the
    // keyword "द्रव्य" (suffix_strip), and misses surface fuzzy suggestions.
    const tokens = meaningfulTokens(q);
    const { resolutions } = await keywordResolveBatch({
      tokens: tokens.length ? tokens : [q],
      fuzzyTopK: 3,
      minSimilarity: 0.35,
      includeDefinitions: false,
    });
    const seen = new Set<string>();
    const out: KeywordResult[] = [];
    const add = (nk?: string | null) => {
      if (!nk || seen.has(nk)) return;
      seen.add(nk);
      out.push({ natural_key: nk, display_text: nk });
    };
    for (const r of resolutions) {
      if (r.match_kind !== 'none') {
        add(r.keyword_natural_key);
      } else {
        // Unresolved token → show only the single best "did you mean"
        // suggestion. Showing the full fuzzy list floods results with weak
        // phonetic coincidences (e.g. परद्रव्य → पर्याय) alongside the genuine
        // near-match (परद्रव्य → द्रव्य).
        add(r.suggestions?.[0]?.keyword_natural_key);
      }
    }
    return out.slice(0, LIMIT);
  } catch (e) {
    console.error('search: keywords failed', e);
    return [];
  }
}
async function fetchTopics(q: string): Promise<TopicMatchItem[]> {
  try {
    // Same shared backend the /topics page uses (ILIKE leaf-substring +
    // parent-aware trigram). searchTerms() puts the FULL phrase first, then
    // each meaningful token. We preserve that priority when merging: the
    // full-phrase relevance ranking comes first (so the genuinely best match
    // always surfaces), then token-only topics fill the rest — this is how
    // "विभाव पर्याय" still surfaces topics under both विभाव and पर्याय without
    // the common-token substring 1.0s drowning the best phrase match.
    const results = await Promise.all(
      searchTerms(q).map((term) =>
        topicsMatch({
          phrase: term,
          limit: LIMIT,
          minSimilarity: 0.3,
          includeExtracts: false,
          includeReferences: false,
        }),
      ),
    );
    const seen = new Set<string>();
    const ordered: TopicMatchItem[] = [];
    for (const r of results) {
      const sorted = [...r.matches].sort((a, b) => b.similarity - a.similarity);
      for (const item of sorted) {
        if (seen.has(item.topic_natural_key)) continue;
        seen.add(item.topic_natural_key);
        ordered.push(item);
      }
    }
    return ordered.slice(0, LIMIT);
  } catch (e) {
    console.error('search: topics failed', e);
    return [];
  }
}
async function fetchShastras(q: string): Promise<ShastraSummary[]> {
  try {
    // Query engine metadata fuzzy match (03_metadata_fuzzy_match): pg_trgm
    // similarity over name + natural_key, so "समयसर" still finds "समयसार".
    // The default 0.25 cutoff lets concept phrases (e.g. "द्रव्यों की
    // स्वतंत्रता") incidentally match unrelated shastra names like पंचास्तिकाय
    // (~0.36); a 0.4 cutoff drops that noise while real name typos still pass
    // (समयसर→समयसार ≈ 0.44).
    const r = await getShastras({ q, limit: LIMIT, fuzzy: true, minSimilarity: 0.4 });
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
  const exactTopic = topics.find((tp) => norm(tp.display_text_hi) === nq);
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
                <TopicNavAction topicNk={exactTopic.topic_natural_key} displayText={exactTopic.display_text_hi} variant="inline" />
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
                key={k.natural_key}
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
              const name = tp.display_text_hi;
              const extractCount = tp.extract_count;
              const hasExtracts = extractCount > 0;
              const parentKw = tp.topic_natural_key.split(':')[0];
              const href = parentKw
                ? `/dictionary/${parentKw}?topic=${encodeURIComponent(tp.topic_natural_key)}`
                : null;
              return (
                <div
                  key={tp.topic_natural_key}
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
                        topicNk={tp.topic_natural_key}
                        displayText={name}
                        isLeaf={tp.is_leaf}
                        parentKeywordNk={parentKw}
                        variant="inline"
                        className="inline-flex items-center gap-1 text-xs font-medium text-accent hover:underline"
                      />
                    )}
                    {hasExtracts && (
                      <span className="rounded-full bg-accent-soft px-2 py-0.5 font-mono text-xs text-accent">
                        {isHi ? toDevanagariNumerals(extractCount) : extractCount}
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
