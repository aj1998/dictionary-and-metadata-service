import { BreadcrumbBar } from '@/components/BreadcrumbBar';
import { GathaPanel } from '@/components/GathaPanel';
import { TaggedTermPopover } from '@/components/TaggedTermPopover';
import { TeekaPanel } from '@/components/TeekaPanel';
import type { TeekaPanelItem } from '@/components/TeekaPanel';
import { Link } from '@/i18n/navigation';
import { getGatha } from '@/lib/api/data';
import { getKeywordTopics } from '@/lib/api/navigation';
import { getHindiText } from '@/lib/content-listing';

export const revalidate = 60;

type PageProps = { params: Promise<{ nk: string; number: string }> };

function joinedLangText(rows: Array<{ lang: string; text: string }> | undefined): string {
  if (!rows || rows.length === 0) return '';
  return rows.map((row) => row.text).join('\n');
}

export default async function GathaDetailPage({ params }: PageProps) {
  const { nk: rawNk, number: rawNumber } = await params;
  const nk = decodeURIComponent(rawNk);
  const number = decodeURIComponent(rawNumber);

  const [gatha, topicsResult] = await Promise.all([
    getGatha(number, { include: ['teeka_mapping', 'teeka_bhaavarth'] }),
    getKeywordTopics(number).catch(() => ({ keyword_natural_key: number, topics: [] })),
  ]);

  const teekaMapping = Array.isArray(gatha.teeka_mapping) ? gatha.teeka_mapping : [];
  const primaryMapping = teekaMapping[0] ?? null;
  const teekaBhaavarth = Array.isArray(gatha.teeka_bhaavarth) ? gatha.teeka_bhaavarth : [];
  const topics = topicsResult.topics;

  const gathaNum = parseInt(gatha.gatha_number, 10);
  const shastraNk = gatha.shastra.natural_key;
  const prevNk = gathaNum > 1 ? `${shastraNk}:गाथा:${gathaNum - 1}` : null;
  const nextNk = `${shastraNk}:गाथा:${gathaNum + 1}`;

  // Build teeka items for the side panel
  const teekaItems: TeekaPanelItem[] = teekaBhaavarth.length > 0
    ? teekaBhaavarth.map((bh) => ({
        key: bh.natural_key,
        label: bh.publication_natural_key ?? bh.natural_key,
        content: getHindiText(bh.text, bh.natural_key),
      }))
    : primaryMapping
      ? [{
          key: primaryMapping.natural_key,
          label: primaryMapping.teeka_natural_key,
          content: primaryMapping.full_anyavaarth || joinedLangText(primaryMapping.anvayartha),
        }]
      : [];

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_400px]">
      {/* ── Main column ── */}
      <div className="space-y-4">
        <section className="rounded-[var(--radius-md)] border border-border bg-surface p-4 shadow-node">
          <BreadcrumbBar
            segments={[
              { label: 'शास्त्र', href: '/shastras' },
              { label: nk, href: `/shastras/${nk}` },
              { label: `गाथा ${gatha.gatha_number || number}` },
            ]}
          />
        </section>

        <GathaPanel lang="prakrit" text={joinedLangText(gatha.prakrit?.text) || '—'} />

        {/* शब्दार्थ — word-by-word meanings + full anvayarth */}
        <section className="rounded-[var(--radius-md)] border border-border bg-surface p-5 shadow-node">
          <h2 className="mb-3 font-serif-hindi text-[length:var(--font-size-h3)] font-semibold">शब्दार्थ</h2>
          {primaryMapping?.tagged_terms.length ? (
            <div className="flex flex-wrap gap-2 leading-8">
              {primaryMapping.tagged_terms.map((term, index) => (
                <TaggedTermPopover
                  key={`${term.source_word}-${index}`}
                  termHi={term.source_word}
                  meaningHi={term.meaning}
                />
              ))}
            </div>
          ) : (
            <p className="text-sm text-foreground-muted">शब्दार्थ उपलब्ध नहीं है।</p>
          )}

          {primaryMapping?.full_anyavaarth && (
            <div className="mt-4 border-t border-border pt-4">
              <p className="mb-1 text-xs font-medium text-foreground-muted">अन्वयार्थ</p>
              <p className="font-serif-hindi text-sm leading-8 text-foreground">
                {primaryMapping.full_anyavaarth}
              </p>
            </div>
          )}
        </section>

        {gatha.sanskrit && <GathaPanel lang="sanskrit" text={joinedLangText(gatha.sanskrit.text)} />}
        <GathaPanel lang="hindi-harigeet" text={joinedLangText(gatha.hindi_chhand[0]?.text) || '—'} />

        {/* Prev / Next navigation */}
        <div className="flex items-center justify-between gap-3 pt-1">
          {prevNk ? (
            <Link
              href={`/shastras/${nk}/gathas/${encodeURIComponent(prevNk)}`}
              className="flex items-center gap-1 rounded-[var(--radius-md)] border border-border bg-surface px-4 py-2 text-sm hover:border-accent hover:text-accent"
            >
              ← गाथा {gathaNum - 1}
            </Link>
          ) : <span />}
          <Link
            href={`/shastras/${nk}/gathas/${encodeURIComponent(nextNk)}`}
            className="flex items-center gap-1 rounded-[var(--radius-md)] border border-border bg-surface px-4 py-2 text-sm hover:border-accent hover:text-accent"
          >
            गाथा {gathaNum + 1} →
          </Link>
        </div>
      </div>

      {/* ── Sidebar ── */}
      <aside className="space-y-4 lg:sticky lg:top-[90px] lg:self-start lg:max-h-[calc(100vh-110px)] lg:overflow-y-auto">
        {/* टीका — moved here for side-by-side comparison */}
        <TeekaPanel items={teekaItems} />

        {topics.length > 0 && (
          <section className="rounded-[var(--radius-md)] border border-border bg-surface p-4 shadow-node">
            <h3 className="font-serif-hindi text-[length:var(--font-size-h3)] font-semibold">संबंधित विषय</h3>
            <div className="mt-3 flex flex-wrap gap-2">
              {topics.map((topic) => (
                <Link key={topic.natural_key} href={`/topics/${topic.natural_key}`} className="rounded-full bg-accent-soft px-3 py-1 text-xs text-accent">
                  {topic.display_text}
                </Link>
              ))}
            </div>
          </section>
        )}

        <Link
          href={`/graph?node=${encodeURIComponent(`gatha:${gatha.natural_key}`)}`}
          className="block rounded-[var(--radius-md)] bg-accent p-4 text-center font-semibold text-white shadow-node hover:bg-accent-hover transition-colors"
        >
          ग्राफ में खोलें
        </Link>
      </aside>
    </div>
  );
}
