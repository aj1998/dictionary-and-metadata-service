import { BreadcrumbBar } from '@/components/BreadcrumbBar';
import { BhaavarthPanel } from '@/components/BhaavarthPanel';
import { GathaPanel } from '@/components/GathaPanel';
import { GathaReaderLayout } from '@/components/GathaReaderLayout';
import { HighlightScrollIntoView } from '@/components/HighlightScrollIntoView';
import { PanelActionsMenu } from '@/components/PanelActionsMenu';
import { TabbedPanel } from '@/components/TabbedPanel';
import type { TabbedPanelItem } from '@/components/TabbedPanel';
import { ShabdaArthSection } from '@/components/ShabdaArthSection';
import { TeekaPanel } from '@/components/TeekaPanel';
import { TopicNavAction } from '@/components/TopicNavAction';
import type { TeekaPanelItem } from '@/components/TeekaPanel';
import { notFound } from 'next/navigation';
import { Link } from '@/i18n/navigation';
import { getExtractMatch, getGatha } from '@/lib/api/data';
import { ApiError } from '@/lib/api/_fetch';
import { getKeywordTopics } from '@/lib/api/navigation';
import { getHindiText } from '@/lib/content-listing';
import { normalizeNFC, toDevanagariNumerals } from '@/lib/format/devanagari';
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
    getGatha(gathaNk, { include: ['teeka_mapping', 'teeka_bhaavarth', 'teeka_sanskrit', 'kalashas'] }).catch((err) => {
      if (err instanceof ApiError && err.status === 404) notFound();
      throw err;
    }),
    getKeywordTopics(gathaNk).catch(() => ({ keyword_natural_key: gathaNk, topics: [] })),
    matchNk
      ? getExtractMatch(matchNk).catch(() => null)
      : Promise.resolve(null),
  ]);

  const shastraPrefix = gatha.shastra.natural_key;
  const gathaNumStr = gatha.gatha_number;

  // Derive canonical Neo4j GathaTeeka nk: `{sn}:{tn}:गाथा:टीका:{g}`
  function gathaTeekaNeo4jNk(teekaNk: string | undefined): string {
    const tn = teekaNk && teekaNk.startsWith(`${shastraPrefix}:`)
      ? teekaNk.slice(shastraPrefix.length + 1)
      : 'टीका';
    return `${shastraPrefix}:${tn}:गाथा:टीका:${gathaNumStr}`;
  }

  // Derive canonical Neo4j GathaTeekaBhaavarth nk: `{sn}:{tn}:{publisher_id}:गाथा:टीका:भावार्थ:{g}`
  function gathaTeekaBhaavarthNeo4jNk(bh: { gatha_teeka_natural_key: string; publisher_id?: string }): string {
    // gatha_teeka_natural_key format: `{sn}:{tn}:{g}` from NJ envelope
    const parts = bh.gatha_teeka_natural_key.split(':');
    const tn = parts.length >= 3 ? parts.slice(1, -1).join(':') : 'टीका';
    const pid = bh.publisher_id ?? 'pub';
    return `${shastraPrefix}:${tn}:${pid}:गाथा:टीका:भावार्थ:${gathaNumStr}`;
  }

  const teekaMapping = Array.isArray(gatha.teeka_mapping) ? gatha.teeka_mapping : [];
  const primaryMapping = teekaMapping[0] ?? null;

  // Derive a short teeka name from the teeka natural_key (e.g. "समयसार:आत्मख्याति" → "आत्मख्याति")
  function teekaShortName(teekaKn: string): string {
    const parts = teekaKn.split(':');
    return parts.length >= 2 ? parts[1] : teekaKn;
  }
  const teekaBhaavarth = Array.isArray(gatha.teeka_bhaavarth) ? gatha.teeka_bhaavarth : [];
  const teekaSanskrit = Array.isArray(gatha.teeka_sanskrit) ? gatha.teeka_sanskrit : [];
  const kalashas: GathaKalash[] = Array.isArray(gatha.kalashas) ? gatha.kalashas : [];
  const topics = topicsResult.topics;

  const gathaNum = parseInt(gatha.gatha_number, 10);
  const shastraNk = gatha.shastra.natural_key;
  const prevNk = gathaNum > 1 ? `${shastraNk}:गाथा:${gathaNum - 1}` : null;
  const nextNk = `${shastraNk}:गाथा:${gathaNum + 1}`;

  const match = extractMatch as ExtractMatch | null;

  // Combined-page notice — shown in shared-content panels when this gatha was ingested
  // from a multi-gatha page (e.g. 020-021-022.html). `is_related` holds the sibling numbers.
  const isRelated: string[] = primaryMapping?.is_related ?? [];
  const combinedGathaNotice = isRelated.length > 0 ? (() => {
    const allNums = [gathaNumStr, ...isRelated]
      .map((n) => parseInt(n, 10))
      .filter((n) => !isNaN(n))
      .sort((a, b) => a - b);
    const devList = allNums.map((n) => toDevanagariNumerals(n)).join(', ');
    const chip = (postposition: 'का' | 'की') => (
      <span key={`combined-${postposition}`} className="inline-flex items-center gap-1 rounded-full border border-border bg-surface-muted px-2.5 py-0.5 font-serif-hindi text-[11px] text-foreground-muted">
        गाथा {devList} {postposition} संयुक्त
      </span>
    );
    return { ka: chip('का'), ki: chip('की') };
  })() : null;

  // Per-teeka combined-page notice keyed by teeka_natural_key. Non-primary teekas
  // (e.g. तात्पर्यवृत्ति) get the teeka short name prepended.
  const noticeByTeeka = new Map<string, import('react').ReactNode>();
  teekaMapping.forEach((m, idx) => {
    const rel = m.is_related ?? [];
    if (rel.length === 0) return;
    const allNums = [gathaNumStr, ...rel]
      .map((n) => parseInt(n, 10))
      .filter((n) => !isNaN(n))
      .sort((a, b) => a - b);
    const devList = allNums.map((n) => toDevanagariNumerals(n)).join(', ');
    const prefix = idx === 0 ? '' : `${teekaShortName(m.teeka_natural_key)} `;
    noticeByTeeka.set(
      m.teeka_natural_key,
      <span key={`combined-${m.teeka_natural_key}`} className="inline-flex items-center gap-1 rounded-full border border-border bg-surface-muted px-2.5 py-0.5 font-serif-hindi text-[11px] text-foreground-muted">
        {prefix}गाथा {devList} का संयुक्त
      </span>
    );
  });

  // टीका sidebar — tabs of sanskrit teeka text
  const teekaItems: TeekaPanelItem[] = teekaSanskrit.map((ts) => {
    const content = joinedLangText(ts.text);
    return {
      key: ts.natural_key,
      label: ts.teeka_natural_key ?? ts.natural_key,
      content,
      naturalKey: ts.natural_key,
      // Canonical Neo4j GathaTeeka nk used by the panel actions menu.
      actionsSourceNk: gathaTeekaNeo4jNk(ts.teeka_natural_key),
      highlight: highlightFor(match, ts.natural_key, content),
    };
  });

  // Bhaavarth tabs — render in right sidebar as a tabbed window.
  // Secondary-kalash entries are filtered out server-side.
  const bhaavarthItems: TabbedPanelItem[] = teekaBhaavarth.map((bh) => {
    const bText = getHindiText(bh.text, bh.natural_key);
    // bh.gatha_teeka_natural_key is `{sn}:{tn}:{g}` — strip the gatha suffix to get teeka_natural_key.
    const teekaNk = bh.gatha_teeka_natural_key.split(':').slice(0, -1).join(':');
    return {
      key: bh.natural_key,
      label: bh.publication_natural_key ?? bh.natural_key,
      actionsSourceNk: gathaTeekaBhaavarthNeo4jNk(bh),
      actionsSourceLabel: bh.publication_natural_key ?? bh.natural_key,
      notice: noticeByTeeka.get(teekaNk),
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

  // For each secondary-teeka kalash, its siblings are all OTHER secondary kalashes
  // with the same teeka shown on this page (they come from the same combined-page).
  // When siblings exist, the bhaavarth gets a "{teeka} गाथा N, M, ... का संयुक्त" chip.
  const secondaryKalashNotice = (kalash: GathaKalash): import('react').ReactNode => {
    if (!kalash.is_secondary) return null;
    const siblings = kalashas.filter(
      (k) => k.is_secondary && k.teeka_natural_key === kalash.teeka_natural_key && k.kalash_number !== kalash.kalash_number,
    );
    if (siblings.length === 0) return null;
    const allNums = [kalash.kalash_number, ...siblings.map((s) => s.kalash_number)]
      .map((n) => parseInt(n, 10))
      .filter((n) => !isNaN(n))
      .sort((a, b) => a - b);
    const devList = allNums.map((n) => toDevanagariNumerals(n)).join(', ');
    const tn = teekaShortName(kalash.teeka_natural_key);
    return (
      <span className="inline-flex items-center gap-1 rounded-full border border-border bg-surface-muted px-2.5 py-0.5 font-serif-hindi text-[11px] text-foreground-muted">
        {tn} गाथा {devList} का संयुक्त
      </span>
    );
  };

  // Kalash/secondary-gatha tabs — render in left column as a tabbed window
  const kalashItems: TabbedPanelItem[] = kalashas.map((kalash) => {
    const prefix = kalash.is_secondary ? 'गाथा' : 'कलश';
    const teeka = teekaShortName(kalash.teeka_natural_key);
    const label = `${prefix}:${teeka}:${kalash.kalash_number}`;
    const bhaavarthNotice = secondaryKalashNotice(kalash);
    return {
    key: kalash.natural_key,
    label,
    actionsSourceNk: kalash.natural_key,
    actionsSourceLabel: label,
    content: (
      <div className="space-y-3">
        {kalash.is_secondary ? (
          <>
            {kalash.prakrit && (
              <BhaavarthPanel
                label="गाथा प्राकृत"
                variant="verse"
                text={joinedLangText(kalash.prakrit.text)}
                naturalKey={kalash.prakrit.natural_key}
                highlight={highlightFor(match, kalash.prakrit.natural_key, joinedLangText(kalash.prakrit.text))}
              />
            )}
            {kalash.sanskrit && (
              <BhaavarthPanel
                label="टीका संस्कृत"
                variant="verse"
                text={joinedLangText(kalash.sanskrit.text)}
                naturalKey={kalash.sanskrit.natural_key}
                highlight={highlightFor(match, kalash.sanskrit.natural_key, joinedLangText(kalash.sanskrit.text))}
              />
            )}
          </>
        ) : (
          <>
            {kalash.sanskrit && (
              <BhaavarthPanel
                label="कलश संस्कृत"
                variant="verse"
                text={joinedLangText(kalash.sanskrit.text)}
                naturalKey={kalash.sanskrit.natural_key}
                highlight={highlightFor(match, kalash.sanskrit.natural_key, joinedLangText(kalash.sanskrit.text))}
              />
            )}
            {kalash.hindi && (
              <BhaavarthPanel
                label="कलश हिन्दी"
                variant="verse"
                text={joinedLangText(kalash.hindi.text)}
                naturalKey={kalash.hindi.natural_key}
                highlight={highlightFor(match, kalash.hindi.natural_key, joinedLangText(kalash.hindi.text))}
              />
            )}
            {kalash.word_meanings && kalash.word_meanings.entries.length > 0 && (
              <section className="rounded-[var(--radius-md)] border border-border bg-surface p-5 shadow-node">
                <h2 className="mb-3 font-serif-hindi text-[length:var(--font-size-h3)] font-semibold">शब्दार्थ</h2>
                <ShabdaArthSection
                  entries={[...kalash.word_meanings.entries]
                    .sort((a, b) => a.position - b.position)
                    .map((e) => ({ word: e.source_word, meaning: e.meaning, position: e.position }))}
                  anvayarth={[...kalash.word_meanings.entries]
                    .sort((a, b) => a.position - b.position)
                    .map((e) => e.meaning)
                    .join(' ')}
                />
              </section>
            )}
          </>
        )}
        {kalash.bhaavarth.map((bh) => {
          // Secondary kalasha whose number matches the current gatha: bhaavarth is already
          // shown in the right-panel हिन्दी भावार्थ tabs, so skip it here to avoid duplication.
          if (kalash.is_secondary && kalash.kalash_number === gathaNumStr) return null;
          const bText = joinedLangText(bh.text);
          return (
            <BhaavarthPanel
              key={bh.natural_key}
              label={kalash.is_secondary ? 'भावार्थ' : 'कलश भावार्थ'}
              notice={bhaavarthNotice}
              text={bText}
              naturalKey={bh.natural_key}
              highlight={highlightFor(match, bh.natural_key, bText)}
            />
          );
        })}
      </div>
    ),
    };
  });

  // Determine scroll target natural key if we have a matched highlight
  const scrollTargetNk =
    match?.match.status === 'matched' ? match.target.natural_key : null;

  const mainColumn = (
    <div key="main" className="space-y-4">
        <section className="rounded-[var(--radius-md)] border border-border bg-surface p-4 shadow-node">
          <BreadcrumbBar
            segments={[
              { label: 'शास्त्र', href: '/shastras' },
              { label: nk, href: `/shastras/${nk}` },
              { label: `गाथा ${gatha.gatha_number || number}` },
            ]}
          />
        </section>

        {/* Gatha heading */}
        {gatha.heading?.length > 0 && (
          <div className="rounded-[var(--radius-md)] border border-border bg-surface-muted px-5 py-3 border-l-4 border-l-border-strong">
            <p className="font-serif-hindi text-[length:var(--font-size-h3)] font-semibold text-foreground leading-relaxed">
              {getHindiText(gatha.heading, gathaNk)}
            </p>
          </div>
        )}

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
          <div className="mb-3 flex items-start justify-between gap-2">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="font-serif-hindi text-[length:var(--font-size-h3)] font-semibold">शब्दार्थ</h2>
              {combinedGathaNotice?.ka}
            </div>
            <PanelActionsMenu sourceNk={gathaNk} sourceLabel={`गाथा ${gatha.gatha_number || number}`} />
          </div>
          {primaryMapping?.tagged_terms.length ? (
            <ShabdaArthSection
              entries={primaryMapping.tagged_terms.map((t) => ({
                word: t.source_word,
                meaning: t.meaning,
                position: t.position,
                startOffset: t.start_offset,
                endOffset: t.end_offset,
              }))}
              anvayarth={primaryMapping.full_anyavaarth ?? primaryMapping.tagged_terms.map((t) => t.meaning).join(' ')}
            />
          ) : primaryMapping?.full_anyavaarth ? (
            <div>
              <p className="mb-1 text-xs font-medium text-foreground-muted">अन्वयार्थ</p>
              <p className="font-serif-hindi text-sm leading-8 text-foreground">{primaryMapping.full_anyavaarth}</p>
            </div>
          ) : (
            <p className="text-sm text-foreground-muted">शब्दार्थ उपलब्ध नहीं है।</p>
          )}
        </section>

        {/* संबंधित — kalash/secondary-gatha tabbed panel */}
        {kalashItems.length > 0 && (
          <TabbedPanel title="संबंधित" items={kalashItems} showActions />
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
  );

  const sidebar = (
      <aside key="sidebar" className="space-y-4 lg:sticky lg:top-[90px] lg:self-start lg:max-h-[calc(100vh-110px)] lg:overflow-y-auto">
        <TeekaPanel key="teeka" items={teekaItems} showActions notice={combinedGathaNotice?.ki} />
        {bhaavarthItems.length > 0 && (
          <TabbedPanel key="bhaavarth" title="हिन्दी भावार्थ" items={bhaavarthItems} showActions notice={combinedGathaNotice?.ka} />
        )}
        {topics.length > 0 && (
          <section key="topics" className="rounded-[var(--radius-md)] border border-border bg-surface p-4 shadow-node">
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

      </aside>
  );

  return (
    <>
      {scrollTargetNk && <HighlightScrollIntoView naturalKey={scrollTargetNk} />}
      <GathaReaderLayout main={mainColumn} sidebar={sidebar} />
    </>
  );
}
