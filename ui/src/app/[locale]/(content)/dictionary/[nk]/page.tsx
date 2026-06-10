import { BreadcrumbBar } from '@/components/BreadcrumbBar';
import { KeywordDefinitionButton } from '@/components/KeywordDefinitionButton';
import { MiniGraphPreview } from '@/components/MiniGraphPreview';
import { TopicTreeBrowser, type TopicTreeItem } from '@/components/TopicTreeBrowser';
import { Link } from '@/i18n/navigation';
import { getKeyword } from '@/lib/api/data';
import { getKeywordTopics } from '@/lib/api/navigation';
import { getTranslations } from 'next-intl/server';

export const revalidate = 60;

type PageProps = {
  params: Promise<{ nk: string }>;
  searchParams: Promise<{ topic?: string }>;
};

export default async function KeywordDetailPage({ params, searchParams }: PageProps) {
  const { nk: rawNk } = await params;
  const { topic: targetTopic } = await searchParams;
  const nk = decodeURIComponent(rawNk);
  const [keyword, t] = await Promise.all([getKeyword(nk), getTranslations('dictionary')]);

  const aliases = keyword.aliases.map((alias) => alias.alias_text).filter(Boolean);

  const topicsResponse = await getKeywordTopics(keyword.natural_key).catch((error) => {
    console.error('Failed to fetch keyword topics', { nk: keyword.natural_key, error });
    return { keyword_natural_key: keyword.natural_key, topics: [] };
  });
  const initialItems: TopicTreeItem[] = topicsResponse.topics.map((t) => ({
    natural_key: t.natural_key,
    display_text: t.display_text_hi || t.natural_key,
  }));

  return (
    <div className="space-y-5">
      <BreadcrumbBar segments={[{ label: t('title'), href: '/dictionary' }, { label: keyword.display_text }]} />

      <section className="rounded-[var(--radius-md)] border border-border bg-surface p-5 shadow-node">
        <h1 className="font-serif-hindi text-[length:var(--font-size-h1)] font-semibold">{keyword.display_text}</h1>
        <p className="mt-2 text-sm text-foreground-muted">{keyword.natural_key}</p>
        {aliases.length > 0 && <p className="mt-2 text-sm">{t('aliases')}: {aliases.join(', ')}</p>}
        <div className="mt-4 flex flex-wrap gap-3">
          <KeywordDefinitionButton keywordNk={keyword.natural_key} displayText={keyword.display_text} />
          {keyword.source_url && <a href={keyword.source_url} target="_blank" rel="noreferrer" className="rounded border border-border px-3 py-1 text-sm">{t('source')}</a>}
          <Link href={`/graph?node=${encodeURIComponent(keyword.natural_key)}`} className="rounded border border-accent px-3 py-1 text-sm text-accent">{t('open_in_graph')}</Link>
        </div>
      </section>

      <section className="rounded-[var(--radius-md)] border border-border bg-surface p-5 shadow-node">
        <h2 className="font-serif-hindi text-[length:var(--font-size-h2)] font-semibold">{t('topics_section')}</h2>
        <div className="mt-3">
          {initialItems.length > 0 ? (
            <TopicTreeBrowser
              initialItems={initialItems}
              targetTopicNk={targetTopic ? decodeURIComponent(targetTopic) : undefined}
              currentKeywordNk={keyword.natural_key}
            />
          ) : (
            <p className="text-sm text-foreground-muted">{t('no_topics')}</p>
          )}
        </div>
      </section>

      <section className="grid grid-cols-1 gap-5 xl:grid-cols-[1fr_320px]">
        <div className="rounded-[var(--radius-md)] border border-border bg-surface p-5 shadow-node">
          <h2 className="font-serif-hindi text-[length:var(--font-size-h2)] font-semibold">{t('graph_relations')}</h2>
          <div className="mt-3 space-y-2 text-sm">
            <Link href={`/graph?node=${encodeURIComponent(keyword.natural_key)}`} className="block rounded border border-border px-3 py-2 hover:bg-surface-muted">
              RELATED_TO →
            </Link>
          </div>
        </div>
        <MiniGraphPreview nk={keyword.natural_key} />
      </section>
    </div>
  );
}
