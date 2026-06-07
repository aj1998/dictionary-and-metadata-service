import { BreadcrumbBar } from '@/components/BreadcrumbBar';
import { BhaavarthPanel } from '@/components/BhaavarthPanel';
import { GathaPanel } from '@/components/GathaPanel';
import { HighlightScrollIntoView } from '@/components/HighlightScrollIntoView';
import { TabbedPanel } from '@/components/TabbedPanel';
import type { TabbedPanelItem } from '@/components/TabbedPanel';
import { TaggedTermPopover } from '@/components/TaggedTermPopover';
import { TeekaPanel } from '@/components/TeekaPanel';
import { TopicNavAction } from '@/components/TopicNavAction';
import type { TeekaPanelItem } from '@/components/TeekaPanel';
import { Link } from '@/i18n/navigation';
import { getExtractMatch, getGatha } from '@/lib/api/data';
import { getKeywordTopics } from '@/lib/api/navigation';
import { getHindiText } from '@/lib/content-listing';
import { normalizeNFC } from '@/lib/format/devanagari';
import type { HighlightRange } from '@/lib/highlight';
import type { ExtractMatch, GathaKalash } from '@/lib/types';

export const revalidate = 60;

type PageProps = { params: Promise<{ nk: string; number: string }>; searchParams: Promise<{ match?: string }> };

function joinedLangText(rows: Array<{ lang: string; text: string }> | undefined): string {
  if (!rows || rows.length === 0) return '';
  return rows.map((row) => row.text).join('\n');
}

function highlightFor(
  match: ExtractMatch | null,
  targetNk: string,
  text: string
): HighlightRange | undefined {
  if (
    !match ||
    match.match.status !== 'matched' ||
    match.target.natural_key !== targetNk ||
    match.match.char_start == null ||
    match.match.char_end == null
  ) {
    return undefined;
  }
  const nfcLen = normalizeNFC(text).length;
  if (match.match.char_end > nfcLen) {
    console.warn('[GathaPage] highlight char_end out of bounds', {
      targetNk,
      char_end: match.match.char_end,
      textLen: nfcLen,
    });
    return undefined;
  }
  return { start: match.match.char_start, end: match.match.char_end };
}

export default async function GathaDetailPage({ params, searchParams }: PageProps) {
  const { nk: rawNk, number: rawNumber } = await params;
  const { match: matchNk } = await searchParams;
  const nk = decodeURIComponent(rawNk);
  const number = decodeURIComponent(rawNumber);
  // `number` may be a plain gatha number ("8") or a full natural key ("समयसार:गाथा:8").
  // Normalize to the gatha natural key the API expects.
  const gathaNk = number.includes(':गाथा:') ? number : `${nk}:गाथा:${number}`;

  const [gatha, topicsResult, extractMatch] = await Promise.all([
    getGatha(gathaNk, { include: ['teeka_mapping', 'teeka_bhaavarth', 'teeka_sanskrit', 'kalashas'] }),
    getKeywordTopics(gathaNk).catch(() => ({ keyword_natural_key: gathaNk, topics: [] })),
    matchNk
      ? getExtractMatch(matchNk).catch(() => null)
      : Promise.resolve(null),
  ]);

  const teekaMapping = Array.isArray(gatha.teeka_mapping) ? gatha.teeka_mapping : [];
  const primaryMapping = teekaMapping[0] ?? null;
  const teekaBhaavarth = Array.isArray(gatha.teeka_bhaavarth) ? gatha.teeka_bhaavarth : [];
  const teekaSanskrit = Array.isArray(gatha.teeka_sanskrit) ? gatha.teeka_sanskrit : [];
  const kalashas: GathaKalash[] = Array.isArray(gatha.kalashas) ? gatha.kalashas : [];
  const topics = topicsResult.topics;

  const gathaNum = parseInt(gatha.gatha_number, 10);
  const shastraNk = gatha.shastra.natural_key;
  const prevNk = gathaNum > 1 ? `${shastraNk}:गाथा:${gathaNum - 1}` : null;
  const nextNk = `${shastraNk}:गाथा:${gathaNum + 1}`;

  const match = extractMatch as ExtractMatch | null;

  // टीका sidebar — tabs of sanskrit teeka text
  const teekaItems: TeekaPanelItem[] = teekaSanskrit.map((ts) => {
    const content = joinedLangText(ts.text);
    return {
      key: ts.natural_key,
      label: ts.teeka_natural_key ?? ts.natural_key,
      content,
      naturalKey: ts.natural_key,
      highlight: highlightFor(match, ts.natural_key, content),
    };
  });

  // Bhaavarth tabs — render in right sidebar as a tabbed window
  const bhaavarthItems: TabbedPanelItem[] = teekaBhaavarth.map((bh) => {
    const bText = getHindiText(bh.text, bh.natural_key);
    return {
      key: bh.natural_key,
      label: bh.publication_natural_key ?? bh.natural_key,
      content: (
        <BhaavarthPanel
          text={bText}
          naturalKey={bh.natural_key}
          highlight={highlightFor(match, bh.natural_key, bText)}
          className="border-0 p-0 shadow-none"
        />
      ),
    };
  });

  // Kalash tabs — render in left column as a tabbed window
  const kalashItems: TabbedPanelItem[] = kalashas.map((kalash) => ({
    key: kalash.natural_key,
    label: `कलश ${kalash.kalash_number}`,
    content: (
      <div className="space-y-3">
        {kalash.sanskrit && (
          <BhaavarthPanel
            label="कलश संस्कृत"
            text={joinedLangText(kalash.sanskrit.text)}
            naturalKey={kalash.sanskrit.natural_key}
            highlight={highlightFor(match, kalash.sanskrit.natural_key, joinedLangText(kalash.sanskrit.text))}
          />
        )}
        {kalash.hindi && (
          <BhaavarthPanel
            label="कलश हिन्दी"
            text={joinedLangText(kalash.hindi.text)}
            naturalKey={kalash.hindi.natural_key}
            highlight={highlightFor(match, kalash.hindi.natural_key, joinedLangText(kalash.hindi.text))}
          />
        )}
        {kalash.bhaavarth.map((bh) => {
          const bText = joinedLangText(bh.text);
          return (
            <BhaavarthPanel
              key={bh.natural_key}
              label="कलश भावार्थ"
              text={bText}
              naturalKey={bh.natural_key}
              highlight={highlightFor(match, bh.natural_key, bText)}
            />
          );
        })}
      </div>
    ),
  }));

  // Determine scroll target natural key if we have a matched highlight
  const scrollTargetNk =
    match?.match.status === 'matched' ? match.target.natural_key : null;

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_400px]">
      {/* Client scroll-into-view — runs once on mount */}
      {scrollTargetNk && <HighlightScrollIntoView naturalKey={scrollTargetNk} />}

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

        {/* 1. प्राकृत गाथा */}
        {gatha.prakrit && (
          <GathaPanel
            lang="prakrit"
            text={joinedLangText(gatha.prakrit.text) || '—'}
            naturalKey={gatha.prakrit.natural_key}
            highlight={highlightFor(match, gatha.prakrit.natural_key, joinedLangText(gatha.prakrit.text))}
          />
        )}
        {!gatha.prakrit && <GathaPanel lang="prakrit" text="—" />}

        {/* 2. संस्कृत छाया */}
        {gatha.sanskrit && (
          <GathaPanel
            lang="sanskrit"
            text={joinedLangText(gatha.sanskrit.text)}
            naturalKey={gatha.sanskrit.natural_key}
            highlight={highlightFor(match, gatha.sanskrit.natural_key, joinedLangText(gatha.sanskrit.text))}
          />
        )}

        {/* 3. हिन्दी हरिगीत */}
        <GathaPanel lang="hindi-harigeet" text={joinedLangText(gatha.hindi_chhand[0]?.text) || '—'} />

        {/* 4. शब्दार्थ — word-by-word meanings + full anvayarth */}
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

        {/* कलश — tabbed panel in left column */}
        {kalashItems.length > 0 && (
          <TabbedPanel title="कलश" items={kalashItems} />
        )}

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
        {/* टीका — sanskrit teeka tabs */}
        <TeekaPanel items={teekaItems} />

        {/* हिन्दी भावार्थ — tabs */}
        {bhaavarthItems.length > 0 && (
          <TabbedPanel title="हिन्दी भावार्थ" items={bhaavarthItems} />
        )}

        {topics.length > 0 && (
          <section className="rounded-[var(--radius-md)] border border-border bg-surface p-4 shadow-node">
            <h3 className="font-serif-hindi text-[length:var(--font-size-h3)] font-semibold">संबंधित विषय</h3>
            <div className="mt-3 flex flex-wrap gap-2">
              {topics.map((topic) => (
                <TopicNavAction
                  key={topic.natural_key}
                  topicNk={topic.natural_key}
                  displayText={topic.display_text_hi || topic.natural_key}
                  variant="inline"
                  className="rounded-full bg-accent-soft px-3 py-1 text-xs text-accent inline-flex items-center gap-1"
                />
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
