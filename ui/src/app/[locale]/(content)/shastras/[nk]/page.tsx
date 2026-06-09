import { BreadcrumbBar } from '@/components/BreadcrumbBar';
import { GathaSearchJump } from '@/components/GathaSearchJump';
import { StatTileRow } from '@/components/StatTileRow';
import { GathaTile } from '@/components/ListCards';
import { getShastra, getShastraTeekas } from '@/lib/api/metadata';
import { getGathasByShastraId } from '@/lib/api/data';
import { getHindiText } from '@/lib/content-listing';
import type { AuthorSummary } from '@/lib/types';

export const revalidate = 60;

type PageProps = { params: Promise<{ nk: string }> };

function getAuthorName(author: AuthorSummary | string | null | undefined): string {
  if (!author) return 'अज्ञात';
  if (typeof author === 'string') return author;
  return getHindiText(author.display_name, author.natural_key);
}

export default async function ShastraDetailPage({ params }: PageProps) {
  const { nk: rawNk } = await params;
  const nk = decodeURIComponent(rawNk);

  const shastra = await getShastra(nk);

  const [teekas, gathas] = await Promise.all([
    getShastraTeekas(nk).catch((error) => {
      console.error('Failed to fetch shastra teekas', { nk, error });
      return [];
    }),
    getGathasByShastraId(shastra.id, { limit: 12, offset: 0 }).catch((error) => {
      console.error('Failed to fetch shastra gathas', { nk, error });
      return { pagination: { total: 0, limit: 12, offset: 0 }, items: [] };
    }),
  ]);

  const titleHi = getHindiText(shastra.title, shastra.natural_key);

  return (
    <div className="space-y-5">
        <BreadcrumbBar segments={[{ label: 'शास्त्र', href: '/shastras' }, { label: titleHi }]} />

        <section className="grid grid-cols-1 gap-4 rounded-[var(--radius-md)] border border-border bg-surface p-5 shadow-node md:grid-cols-[1fr_320px]">
          <div>
            <h1 className="font-serif-hindi text-[length:var(--font-size-h1)] font-semibold">{titleHi}</h1>
            <div className="mt-2 flex flex-wrap gap-2 text-sm">
              {shastra.author && <span className="rounded-full bg-surface-muted px-3 py-1">{getAuthorName(shastra.author)}</span>}
              {(shastra.anuyogas ?? []).map((tag) => <span key={tag} className="rounded-full bg-accent-soft px-3 py-1 text-accent">{tag}</span>)}
              {shastra.source_url && <a href={shastra.source_url} target="_blank" rel="noreferrer" className="rounded-full border border-accent px-3 py-1 text-accent">मूल स्रोत ↗</a>}
            </div>
          </div>
          <StatTileRow
            tiles={[
              { count: gathas.pagination.total, label: 'गाथाएँ' },
              { count: teekas.length, label: 'टीकाएँ' },
              { count: 0, label: 'पृष्ठ' },
            ]}
          />
        </section>

        <section className="rounded-[var(--radius-md)] border border-border bg-surface p-5 shadow-node">
          <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
            <h2 className="font-serif-hindi text-[length:var(--font-size-h2)] font-semibold">गाथाएँ</h2>
            <GathaSearchJump shastraNk={nk} totalGathas={gathas.pagination.total} />
          </div>
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
            {gathas.items.map((gatha) => (
              <GathaTile
                key={gatha.id}
                kind="gatha"
                titleHi={`गाथा ${gatha.gatha_number}`}
                meta={getHindiText(gatha.heading, gatha.natural_key)}
                href={`/shastras/${nk}/gathas/${encodeURIComponent(gatha.natural_key)}`}
              />
            ))}
          </div>
        </section>

        <section className="rounded-[var(--radius-md)] border border-border bg-surface p-5 shadow-node">
          <h2 className="font-serif-hindi text-[length:var(--font-size-h2)] font-semibold">टीकाएँ</h2>
          <div className="mt-3 overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-left text-foreground-muted">
                  <th className="pb-2">टीकाकार</th>
                  <th className="pb-2">प्रकाशक</th>
                  <th className="pb-2">वर्ष</th>
                  <th className="pb-2">भाषा</th>
                </tr>
              </thead>
              <tbody>
                {teekas.map((teeka) => (
                  <tr key={teeka.id} className="border-b border-border/60">
                    <td className="py-2">{getAuthorName(teeka.teekakar)}</td>
                    <td className="py-2">{teeka.publisher ?? '—'}</td>
                    <td className="py-2">{teeka.year ?? '—'}</td>
                    <td className="py-2">{teeka.language ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
    </div>
  );
}
