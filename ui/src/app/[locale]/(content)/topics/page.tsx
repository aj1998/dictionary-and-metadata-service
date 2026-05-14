import { Link } from '@/i18n/navigation';
import { getTopics } from '@/lib/api/data';
import { getHindiText, paginatedMeta } from '@/lib/content-listing';
import { toDevanagariNumerals } from '@/lib/format/devanagari';

export const revalidate = 60;

type PageProps = {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
};

function first(value: string | string[] | undefined): string {
  if (Array.isArray(value)) return value[0] ?? '';
  return value ?? '';
}

const PAGE_SIZE = 12;

export default async function TopicsPage({ searchParams }: PageProps) {
  const query = await searchParams;
  const q = first(query.q).trim();
  const source = first(query.source).trim();
  const page = Math.max(1, Number.parseInt(first(query.page), 10) || 1);
  const offset = (page - 1) * PAGE_SIZE;

  const topics = await getTopics({ q: q || undefined, source: source || undefined, limit: PAGE_SIZE, offset });
  const meta = paginatedMeta(topics.pagination);

  const makeHref = (nextPage: number) => {
    const params = new URLSearchParams();
    if (q) params.set('q', q);
    if (source) params.set('source', source);
    params.set('page', String(nextPage));
    return `/topics?${params.toString()}`;
  };

  return (
    <div className="space-y-5">
      <form className="rounded-[var(--radius-md)] border border-border bg-surface p-4 shadow-node">
        <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
          <select name="source" defaultValue={source} className="h-10 rounded-[var(--radius-md)] border border-border bg-background px-3 text-sm">
            <option value="">सभी स्रोत</option>
            <option value="jainkosh">jainkosh</option>
            <option value="nj">nj</option>
            <option value="chat_candidate">chat_candidate</option>
          </select>
          <input name="q" defaultValue={q} placeholder="विषय खोजें" className="h-10 rounded-[var(--radius-md)] border border-border bg-background px-3 text-sm" />
          <button type="submit" className="h-10 rounded-[var(--radius-md)] bg-accent px-4 text-sm font-semibold text-white">लागू करें</button>
        </div>
      </form>

      <section className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
        {topics.items.map((item) => (
          <article key={item.id} className="rounded-[var(--radius-md)] border border-border bg-surface p-5 shadow-node">
            <h2 className="font-serif-hindi text-[length:var(--font-size-h3)] font-semibold">{getHindiText(item.display_text, item.natural_key)}</h2>
            <div className="mt-2 flex items-center justify-between">
              <span className="rounded-full bg-accent-soft px-2 py-1 text-xs text-accent">{item.parent_keyword?.display_text ?? '—'}</span>
              <span className="font-serif-hindi text-[length:var(--font-size-h2)] font-semibold text-foreground-muted">{toDevanagariNumerals(item.is_leaf ? 1 : 0)}</span>
            </div>
            <Link href={`/topics/${item.natural_key}`} className="mt-4 inline-block text-sm font-medium text-accent">विषय खोलें →</Link>
          </article>
        ))}
      </section>

      <div className="flex items-center justify-center gap-3 text-sm">
        {meta.hasPrevious ? <Link href={makeHref(meta.page - 1)} className="rounded border border-border px-3 py-1">पिछला</Link> : <span className="rounded border border-border px-3 py-1 text-foreground-subtle">पिछला</span>}
        <span>पृष्ठ {toDevanagariNumerals(meta.page)} / {toDevanagariNumerals(meta.totalPages)}</span>
        {meta.hasNext ? <Link href={makeHref(meta.page + 1)} className="rounded border border-border px-3 py-1">अगला</Link> : <span className="rounded border border-border px-3 py-1 text-foreground-subtle">अगला</span>}
      </div>
    </div>
  );
}
