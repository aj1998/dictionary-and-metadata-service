import { Link } from '@/i18n/navigation';
import { getTopics } from '@/lib/api/data';
import { topicsMatch } from '@/lib/api/query';
import { getHindiText, paginatedMeta } from '@/lib/content-listing';
import { toDevanagariNumerals } from '@/lib/format/devanagari';
import { TopicNavAction } from '@/components/TopicNavAction';
import { TopicPathInfo } from '@/components/TopicPathInfo';
import { getLocale, getTranslations } from 'next-intl/server';
import type { TopicMatchItem } from '@/lib/types';

export const revalidate = 60;

type PageProps = {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
};

function first(value: string | string[] | undefined): string {
  if (Array.isArray(value)) return value[0] ?? '';
  return value ?? '';
}

const PAGE_SIZE = 12;

function TopicMatchCard({ item }: { item: TopicMatchItem }) {
  const breadcrumb = item.ancestors_hi.length > 0
    ? item.ancestors_hi.join(' › ') + ' › '
    : '';
  return (
    <article className="rounded-[var(--radius-md)] border border-border bg-surface p-5 shadow-node">
      {breadcrumb && (
        <p className="font-serif-hindi text-xs text-foreground-muted mb-1">{breadcrumb}</p>
      )}
      <h2 className="font-serif-hindi text-[length:var(--font-size-h3)] font-semibold">
        {item.display_text_hi}
      </h2>
      <div className="mt-2 flex items-center justify-end">
        <span className="text-xs text-foreground-muted">
          {(item.similarity * 100).toFixed(0)}% मिलान
        </span>
      </div>
      <div className="mt-4 flex items-center justify-between gap-2">
        <TopicNavAction
          topicNk={item.topic_natural_key}
          displayText={item.display_text_hi}
          isLeaf={item.is_leaf}
        />
        <TopicPathInfo topicNk={item.topic_natural_key} />
      </div>
    </article>
  );
}

export default async function TopicsPage({ searchParams }: PageProps) {
  const query = await searchParams;
  const q = first(query.q).trim();
  const source = first(query.source).trim();
  const includeOther = first(query.include_other) === '1';
  const page = Math.max(1, Number.parseInt(first(query.page), 10) || 1);
  const offset = (page - 1) * PAGE_SIZE;
  const [tT, tP, locale] = await Promise.all([
    getTranslations('topics'),
    getTranslations('pagination'),
    getLocale(),
  ]);
  const isHi = locale === 'hi';
  const num = (n: number) => (isHi ? toDevanagariNumerals(n) : String(n));

  const makeHref = (nextPage: number) => {
    const params = new URLSearchParams();
    if (q) params.set('q', q);
    if (source) params.set('source', source);
    if (includeOther) params.set('include_other', '1');
    params.set('page', String(nextPage));
    return `/topics?${params.toString()}`;
  };

  // Use trigram topics_match when a search query is present
  if (q) {
    let matchItems: TopicMatchItem[] = [];
    let matchError = false;
    try {
      const result = await topicsMatch({
        phrase: q,
        limit: PAGE_SIZE,
        minSimilarity: 0.25,
        includeExtracts: false,
        includeReferences: false,
      });
      matchItems = [...result.matches].sort((a, b) => b.similarity - a.similarity);
    } catch {
      matchError = true;
    }

    return (
      <div className="space-y-5">
        <form className="rounded-[var(--radius-md)] border border-border bg-surface p-4 shadow-node">
          <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
            <select name="source" defaultValue={source} className="h-10 rounded-[var(--radius-md)] border border-border bg-background px-3 text-sm">
              <option value="">{tT('all_sources')}</option>
              <option value="jainkosh">jainkosh</option>
              <option value="nj">nj</option>
              <option value="chat_candidate">chat_candidate</option>
            </select>
            <input name="q" defaultValue={q} placeholder={tT('search_within')} className="h-10 rounded-[var(--radius-md)] border border-border bg-background px-3 text-sm" />
            <button type="submit" className="h-10 rounded-[var(--radius-md)] bg-accent px-4 text-sm font-semibold text-white">{tT('apply')}</button>
          </div>
          <label className="mt-3 inline-flex items-center gap-2 text-sm text-foreground-muted">
            <input type="checkbox" name="include_other" value="1" defaultChecked={includeOther} className="size-4 accent-accent" />
            {tT('show_intermediate')}
          </label>
        </form>

        {matchError && (
          <p className="text-sm text-danger">खोज में त्रुटि हुई। कृपया पुनः प्रयास करें।</p>
        )}

        {!matchError && matchItems.length === 0 && (
          <p className="font-serif-hindi text-foreground-muted text-sm">
            &ldquo;{q}&rdquo; के लिए कोई विषय नहीं मिला।
          </p>
        )}

        <section className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
          {matchItems.map((item) => (
            <TopicMatchCard key={item.topic_natural_key} item={item} />
          ))}
        </section>
      </div>
    );
  }

  // Default: exact/ILIKE listing from data-service
  const topics = await getTopics({
    source: source || undefined,
    limit: PAGE_SIZE,
    offset,
    hasTopicPath: includeOther ? undefined : true,
    isLeaf: includeOther ? undefined : true,
  });
  const meta = paginatedMeta(topics.pagination);

  return (
    <div className="space-y-5">
      <form className="rounded-[var(--radius-md)] border border-border bg-surface p-4 shadow-node">
        <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
          <select name="source" defaultValue={source} className="h-10 rounded-[var(--radius-md)] border border-border bg-background px-3 text-sm">
            <option value="">{tT('all_sources')}</option>
            <option value="jainkosh">jainkosh</option>
            <option value="nj">nj</option>
            <option value="chat_candidate">chat_candidate</option>
          </select>
          <input name="q" defaultValue={q} placeholder={tT('search_within')} className="h-10 rounded-[var(--radius-md)] border border-border bg-background px-3 text-sm" />
          <button type="submit" className="h-10 rounded-[var(--radius-md)] bg-accent px-4 text-sm font-semibold text-white">{tT('apply')}</button>
        </div>
        <label className="mt-3 inline-flex items-center gap-2 text-sm text-foreground-muted">
          <input type="checkbox" name="include_other" value="1" defaultChecked={includeOther} className="size-4 accent-accent" />
          {tT('show_intermediate')}
        </label>
      </form>

      <section className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
        {topics.items.map((item) => (
          <article key={item.id} className="rounded-[var(--radius-md)] border border-border bg-surface p-5 shadow-node">
            <h2 className="font-serif-hindi text-[length:var(--font-size-h3)] font-semibold">{getHindiText(item.display_text, item.natural_key)}</h2>
            <div className="mt-2 flex items-center justify-between">
              <span className="rounded-full bg-accent-soft px-2 py-1 text-xs text-accent">{item.parent_keyword?.display_text ?? '—'}</span>
              <span className="font-serif-hindi text-[length:var(--font-size-h2)] font-semibold text-foreground-muted">{toDevanagariNumerals(item.extract_count ?? 0)}</span>
            </div>
            <div className="mt-4 flex items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                {item.topic_path && item.is_leaf && (
                  <TopicNavAction
                    topicNk={item.natural_key}
                    displayText={getHindiText(item.display_text, item.natural_key)}
                    isLeaf={item.is_leaf}
                    parentKeywordNk={item.parent_keyword?.natural_key}
                  />
                )}
              </div>
              <TopicPathInfo
                topicNk={item.natural_key}
                dictionaryHref={
                  item.parent_keyword?.natural_key
                    ? `/dictionary/${encodeURIComponent(item.parent_keyword.natural_key)}?topic=${encodeURIComponent(item.natural_key)}`
                    : undefined
                }
              />
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
