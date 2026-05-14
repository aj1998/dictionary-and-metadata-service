import { ChevronRight } from '@/lib/icons';
import { Link } from '@/i18n/navigation';
import { getKeywords } from '@/lib/api/data';
import { paginatedMeta } from '@/lib/content-listing';
import { toDevanagariNumerals } from '@/lib/format/devanagari';

export const revalidate = 60;

type PageProps = {
  params: Promise<{ letter: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
};

function first(value: string | string[] | undefined): string {
  if (Array.isArray(value)) return value[0] ?? '';
  return value ?? '';
}

const PAGE_SIZE = 20;

export default async function DictionaryLetterPage({ params, searchParams }: PageProps) {
  const { letter } = await params;
  const query = await searchParams;
  const q = first(query.q).trim();
  const page = Math.max(1, Number.parseInt(first(query.page), 10) || 1);
  const offset = (page - 1) * PAGE_SIZE;

  const list = await getKeywords({ letter, q: q || undefined, limit: PAGE_SIZE, offset });
  const meta = paginatedMeta(list.pagination);

  const makeHref = (nextPage: number) => {
    const paramsBuilder = new URLSearchParams();
    if (q) paramsBuilder.set('q', q);
    paramsBuilder.set('page', String(nextPage));
    return `/dictionary/letters/${encodeURIComponent(letter)}?${paramsBuilder.toString()}`;
  };

  return (
    <div className="rounded-[var(--radius-md)] border border-border bg-surface p-6 shadow-node">
      <h1 className="font-serif-hindi text-[length:var(--font-size-display)] font-semibold">{letter}</h1>
      <p className="mt-1 text-sm text-foreground-muted">{toDevanagariNumerals(list.pagination.total)} शब्द</p>

      <form className="mt-4">
        <input name="q" defaultValue={q} placeholder="इस अक्षर में खोजें" className="h-10 w-full rounded-[var(--radius-md)] border border-border bg-background px-3 text-sm" />
      </form>

      <ul className="mt-5 space-y-3">
        {list.items.map((item) => (
          <li key={item.id}>
            <Link href={`/dictionary/${item.natural_key}`} className="flex items-center justify-between rounded-[var(--radius-md)] border border-border px-4 py-3 hover:bg-surface-muted">
              <div>
                <p className="font-serif-hindi text-[length:var(--font-size-h3)] font-semibold">{item.display_text}</p>
                <p className="text-xs text-foreground-muted">{item.natural_key}</p>
              </div>
              <ChevronRight className="size-4 text-foreground-muted" strokeWidth={1.5} />
            </Link>
          </li>
        ))}
      </ul>

      <div className="mt-6 flex items-center justify-center gap-3 text-sm">
        {meta.hasPrevious ? <Link href={makeHref(meta.page - 1)} className="rounded border border-border px-3 py-1">पिछला</Link> : <span className="rounded border border-border px-3 py-1 text-foreground-subtle">पिछला</span>}
        <span>पृष्ठ {toDevanagariNumerals(meta.page)} / {toDevanagariNumerals(meta.totalPages)}</span>
        {meta.hasNext ? <Link href={makeHref(meta.page + 1)} className="rounded border border-border px-3 py-1">अगला</Link> : <span className="rounded border border-border px-3 py-1 text-foreground-subtle">अगला</span>}
      </div>
    </div>
  );
}
