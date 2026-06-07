import { BreadcrumbBar } from '@/components/BreadcrumbBar';
import { MiniGraphPreview } from '@/components/MiniGraphPreview';
import { TopicTreeBrowser, type TopicTreeItem } from '@/components/TopicTreeBrowser';
import { Link } from '@/i18n/navigation';
import { getTopic } from '@/lib/api/data';
import { getTopicNeighbors } from '@/lib/api/navigation';
import { getHindiText } from '@/lib/content-listing';

export const revalidate = 60;

type PageProps = { params: Promise<{ nk: string }> };

export default async function TopicDetailPage({ params }: PageProps) {
  const { nk: rawNk } = await params;
  const nk = decodeURIComponent(rawNk);

  const [topic, neighborResponse] = await Promise.all([
    getTopic(nk),
    getTopicNeighbors(nk).catch((error) => {
      console.error('Failed to fetch topic neighbors', { nk, error });
      return { topic_natural_key: nk, neighbors: [] };
    }),
  ]);

  const titleHi = getHindiText(topic.display_text, topic.natural_key);

  const initialItems: TopicTreeItem[] = neighborResponse.neighbors
    .filter((n) => n.edge_type === 'PART_OF' && n.edge_direction === 'inbound')
    .map((n) => ({ natural_key: n.natural_key, display_text: n.display_text_hi }));

  const relatedTo = neighborResponse.neighbors.filter((n) => n.edge_type === 'RELATED_TO');

  return (
    <div className="grid grid-cols-1 gap-6 xl:grid-cols-[1fr_320px]">
      <div className="space-y-5">
        <BreadcrumbBar segments={[{ label: 'विषय', href: '/topics' }, { label: titleHi }]} />

        <section className="rounded-[var(--radius-md)] border border-border bg-surface p-5 shadow-node">
          <h1 className="font-serif-hindi text-[length:var(--font-size-h1)] font-semibold">{titleHi}</h1>
          <div className="mt-3 flex flex-wrap gap-2 text-sm">
            {topic.parent_keyword && <span className="rounded-full bg-accent-soft px-3 py-1 text-accent">{topic.parent_keyword.display_text}</span>}
            <span className="rounded-full bg-surface-muted px-3 py-1">{topic.source}</span>
          </div>
        </section>

        <section className="rounded-[var(--radius-md)] border border-border bg-surface p-5 shadow-node">
          <h2 className="font-serif-hindi text-[length:var(--font-size-h2)] font-semibold">उप-विषय</h2>
          <div className="mt-3">
            {initialItems.length > 0 ? (
              <TopicTreeBrowser initialItems={initialItems} />
            ) : (
              <p className="text-sm text-foreground-muted">कोई उप-विषय नहीं</p>
            )}
          </div>
        </section>

        <section className="rounded-[var(--radius-md)] border border-border bg-surface p-5 shadow-node">
          <h2 className="font-serif-hindi text-[length:var(--font-size-h2)] font-semibold">ग्राफ पड़ोसी</h2>
          <div className="mt-3">
            <div className="rounded border border-border p-3">
              <h3 className="text-sm font-semibold text-foreground-muted">RELATED_TO</h3>
              <div className="mt-2 space-y-2">
                {relatedTo.length === 0 && <p className="text-sm text-foreground-muted">कोई नहीं</p>}
                {relatedTo.slice(0, 10).map((neighbor) => (
                  <Link key={neighbor.natural_key} href={`/graph?node=${encodeURIComponent(neighbor.natural_key)}`} className="block rounded bg-surface-muted px-2 py-1 text-sm hover:bg-accent-soft">
                    {neighbor.display_text_hi}
                  </Link>
                ))}
              </div>
            </div>
          </div>
        </section>
      </div>

      <aside className="space-y-4 xl:sticky xl:top-[90px] xl:self-start">
        <Link href={`/graph?node=${encodeURIComponent(topic.natural_key)}`} className="block rounded border border-accent px-3 py-2 text-center text-sm text-accent hover:bg-accent-soft">
          ग्राफ में खोलें →
        </Link>
        <MiniGraphPreview nk={topic.natural_key} />
      </aside>
    </div>
  );
}
