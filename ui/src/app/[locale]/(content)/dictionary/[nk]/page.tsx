import { BreadcrumbBar } from '@/components/BreadcrumbBar';
import { MiniGraphPreview } from '@/components/MiniGraphPreview';
import { Link } from '@/i18n/navigation';
import { getKeyword } from '@/lib/api/data';

export const revalidate = 60;

type PageProps = { params: Promise<{ nk: string }> };

export default async function KeywordDetailPage({ params }: PageProps) {
  const { nk: rawNk } = await params;
  const nk = decodeURIComponent(rawNk);
  const keyword = await getKeyword(nk);

  const aliases = keyword.aliases.map((alias) => alias.alias_text).filter(Boolean);

  return (
    <div className="space-y-5">
      <BreadcrumbBar segments={[{ label: 'शब्दकोश', href: '/dictionary' }, { label: keyword.display_text }]} />

      <section className="rounded-[var(--radius-md)] border border-border bg-surface p-5 shadow-node">
        <h1 className="font-serif-hindi text-[length:var(--font-size-h1)] font-semibold">{keyword.display_text}</h1>
        <p className="mt-2 text-sm text-foreground-muted">{keyword.natural_key}</p>
        {aliases.length > 0 && <p className="mt-2 text-sm">aliases: {aliases.join(', ')}</p>}
        <div className="mt-4 flex flex-wrap gap-3">
          {keyword.source_url && <a href={keyword.source_url} target="_blank" rel="noreferrer" className="rounded border border-border px-3 py-1 text-sm">स्रोत ↗</a>}
          <Link href={`/graph?node=${encodeURIComponent(keyword.natural_key)}`} className="rounded border border-accent px-3 py-1 text-sm text-accent">ग्राफ में खोलें →</Link>
        </div>
      </section>

      <section className="rounded-[var(--radius-md)] border border-border bg-surface p-5 shadow-node">
        <h2 className="font-serif-hindi text-[length:var(--font-size-h2)] font-semibold">सिद्धांतकोष से</h2>
        <pre className="mt-3 whitespace-pre-wrap rounded bg-background p-4 text-sm">{JSON.stringify(keyword.definition, null, 2) || 'परिभाषा उपलब्ध नहीं है।'}</pre>
      </section>

      <section className="grid grid-cols-1 gap-5 xl:grid-cols-[1fr_320px]">
        <div className="rounded-[var(--radius-md)] border border-border bg-surface p-5 shadow-node">
          <h2 className="font-serif-hindi text-[length:var(--font-size-h2)] font-semibold">ग्राफ संबंध</h2>
          <div className="mt-3 space-y-2 text-sm">
            {['IS_A', 'PART_OF', 'RELATED_TO'].map((kind) => (
              <Link key={kind} href={`/graph?node=${encodeURIComponent(keyword.natural_key)}`} className="block rounded border border-border px-3 py-2 hover:bg-surface-muted">
                {kind} →
              </Link>
            ))}
          </div>
        </div>
        <MiniGraphPreview nk={keyword.natural_key} />
      </section>
    </div>
  );
}
