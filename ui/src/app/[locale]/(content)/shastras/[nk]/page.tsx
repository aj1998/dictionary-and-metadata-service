import { BreadcrumbBar } from '@/components/BreadcrumbBar';
import { GathaSearchJump } from '@/components/GathaSearchJump';
import { StatTileRow } from '@/components/StatTileRow';
import { GathaTile } from '@/components/ListCards';
import { getShastra, getShastraTeekas } from '@/lib/api/metadata';
import { getGathasByShastraId } from '@/lib/api/data';
import { getHindiText } from '@/lib/content-listing';
import { gathaCompactFromNk, gathaTileLabel, uniqueLeadingIdValues } from '@/lib/format/gatha-id';
import { getTranslations } from 'next-intl/server';
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

  const [shastra, t] = await Promise.all([getShastra(nk), getTranslations('shastras')]);

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

  // Fetch the full gatha set to derive the complete अधिकार/अध्याय list for the
  // search-jump dropdown. A fixed window (e.g. 200) is unsafe: gathas come back
  // string-sorted by natural_key, so "10" sorts before "2" and a truncated
  // window silently drops middle adhyayas (तत्त्वार्थसूत्र has 349 gathas across
  // 10 अध्याय — a 200-row window showed only 1,2,3,4,5,10). Bound the request by
  // the real total (capped to keep huge legacy shastras in check; those are
  // single-id and don't populate the dropdown anyway).
  const adhikaarWindow = Math.min(Math.max(gathas.pagination.total, 1), 2000);
  const gathasAll = await getGathasByShastraId(shastra.id, { limit: adhikaarWindow, offset: 0 }).catch(() => ({
    pagination: { total: 0, limit: adhikaarWindow, offset: 0 },
    items: [],
  }));

  const adhikaarList = uniqueLeadingIdValues(
    shastra.natural_key,
    gathasAll.items.map((g) => g.natural_key),
  );

  const titleHi = getHindiText(shastra.title, shastra.natural_key);

  return (
    <div className="space-y-5">
        <BreadcrumbBar segments={[{ label: t('title'), href: '/shastras' }, { label: titleHi }]} />

        <section className="grid grid-cols-1 gap-4 rounded-[var(--radius-md)] border border-border bg-surface p-5 shadow-node md:grid-cols-[1fr_320px]">
          <div>
            <h1 className="font-serif-hindi text-[length:var(--font-size-h1)] font-semibold">{titleHi}</h1>
            <div className="mt-2 flex flex-wrap gap-2 text-sm">
              {shastra.author && <span className="rounded-full bg-surface-muted px-3 py-1">{getAuthorName(shastra.author)}</span>}
              {(shastra.anuyogas ?? []).map((tag) => <span key={tag} className="rounded-full bg-accent-soft px-3 py-1 text-accent">{tag}</span>)}
              {shastra.source_url && <a href={shastra.source_url} target="_blank" rel="noreferrer" className="rounded-full border border-accent px-3 py-1 text-accent">{t('source_external')}</a>}
            </div>
          </div>
          <StatTileRow
            tiles={[
              { count: gathas.pagination.total, label: t('gathas') },
              { count: teekas.length, label: t('teekas') },
              { count: 0, label: t('pages') },
            ]}
          />
        </section>

        <section className="rounded-[var(--radius-md)] border border-border bg-surface p-5 shadow-node">
          <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
            <h2 className="font-serif-hindi text-[length:var(--font-size-h2)] font-semibold">{t('gathas')}</h2>
            <GathaSearchJump
              shastraNk={nk}
              totalGathas={gathas.pagination.total}
              adhikaarField={adhikaarList?.fieldName ?? null}
              adhikaarValues={adhikaarList?.values ?? []}
            />
          </div>
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
            {gathas.items.map((gatha) => {
              const compact = gathaCompactFromNk(shastra.natural_key, gatha.natural_key);
              const compoundLabel = gathaTileLabel(shastra.natural_key, gatha.natural_key, gatha.gatha_number);
              const isCompound = compact.includes(',');
              return (
                <GathaTile
                  key={gatha.id}
                  kind="gatha"
                  titleHi={isCompound ? compoundLabel : `${t('gatha_label')} ${compact}`}
                  meta={getHindiText(gatha.heading, gatha.natural_key)}
                  href={`/shastras/${encodeURIComponent(nk)}/gathas/${encodeURIComponent(compact)}`}
                />
              );
            })}
          </div>
        </section>

        <section className="rounded-[var(--radius-md)] border border-border bg-surface p-5 shadow-node">
          <h2 className="font-serif-hindi text-[length:var(--font-size-h2)] font-semibold">{t('teekas')}</h2>
          <div className="mt-3 overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-left text-foreground-muted">
                  <th className="pb-2">{t('col_teekakar')}</th>
                  <th className="pb-2">{t('col_publisher')}</th>
                  <th className="pb-2">{t('col_year')}</th>
                  <th className="pb-2">{t('col_language')}</th>
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
