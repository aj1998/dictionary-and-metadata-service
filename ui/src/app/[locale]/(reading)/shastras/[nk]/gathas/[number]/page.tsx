import { BreadcrumbBar } from '@/components/BreadcrumbBar';
import { BhaavarthPanel } from '@/components/BhaavarthPanel';
import { GathaReaderLayout } from '@/components/GathaReaderLayout';
import {
  GathaPageBottomNav,
  GathaVerseGroup,
  GathaVerseStateProvider,
} from '@/components/GathaVerseGroup';
import type { GathaVerseEntry } from '@/components/GathaVerseGroup';
import { HighlightScrollIntoView } from '@/components/HighlightScrollIntoView';
import { PanelActionsMenu } from '@/components/PanelActionsMenu';
import { TabbedPanel } from '@/components/TabbedPanel';
import type { TabbedPanelItem } from '@/components/TabbedPanel';
import { ShabdaArthSection } from '@/components/ShabdaArthSection';
import { TeekaPanel } from '@/components/TeekaPanel';
import { TopicNavAction } from '@/components/TopicNavAction';
import type { TeekaPanelItem } from '@/components/TeekaPanel';
import { notFound } from 'next/navigation';
import { getExtractMatch, getGatha, getGathaByPath, getGathaAdjacent } from '@/lib/api/data';
import { ApiError } from '@/lib/api/_fetch';
import { getKeywordTopics } from '@/lib/api/navigation';
import { getHindiText } from '@/lib/content-listing';
import { normalizeNFC, toDevanagariNumerals } from '@/lib/format/devanagari';
import { gathaCompactFromNk, isFullGathaNk, parseGathaSuffix } from '@/lib/format/gatha-id';

const formatGathaRange = (nums: number[], isHi: boolean): string => {
  const fmt = (n: number) => isHi ? toDevanagariNumerals(n) : String(n);
  if (nums.length > 2) {
    return `${fmt(nums[0])}-${fmt(nums[nums.length - 1])}`;
  }
  return nums.map(fmt).join(', ');
};
import { getLocale, getTranslations } from 'next-intl/server';
import type { HighlightRange } from '@/lib/highlight';
import type { ExtractMatch, GathaKalash } from '@/lib/types';

export const revalidate = 60;

type PageProps = { params: Promise<{ nk: string; number: string }>; searchParams: Promise<{ match?: string | string[] }> };

function joinedLangText(rows: Array<{ lang: string; text: string }> | undefined): string {
  if (!rows || rows.length === 0) return '';
  return rows.map((row) => row.text).join('\n');
}

// Returns the highlight range for the first matched extract-match whose target
// equals `targetNk`. Supports multiple simultaneous matches (e.g. the verse +
// its अन्वयार्थ/शब्दार्थ), each highlighting a different panel.
function highlightFor(
  matches: ExtractMatch[],
  targetNk: string,
  text: string
): HighlightRange | undefined {
  const nfcLen = normalizeNFC(text).length;
  for (const match of matches) {
    if (
      match.match.status !== 'matched' ||
      match.target.natural_key !== targetNk ||
      match.match.char_start == null ||
      match.match.char_end == null
    ) {
      continue;
    }
    if (match.match.char_end > nfcLen) {
      console.warn('[GathaPage] highlight char_end out of bounds', {
        targetNk,
        char_end: match.match.char_end,
        textLen: nfcLen,
      });
      continue;
    }
    return { start: match.match.char_start, end: match.match.char_end };
  }
  return undefined;
}

export default async function GathaDetailPage({ params, searchParams }: PageProps) {
  const { nk: rawNk, number: rawNumber } = await params;
  const { match: matchParam } = await searchParams;
  // A gatha page may carry multiple ?match= keys (verse + अन्वयार्थ etc.).
  const matchNks: string[] = Array.isArray(matchParam)
    ? matchParam
    : matchParam
      ? [matchParam]
      : [];
  const nk = decodeURIComponent(rawNk);
  const number = decodeURIComponent(rawNumber);

  // Normalise URL forms:
  //   "1,9"                              → compound compact
  //   "परमात्मप्रकाश:अधिकार:1:गाथा:9" → full compound NK (derive compact)
  //   "समयसार:गाथा:8"                    → legacy full NK
  //   "8"                                 → legacy bare number
  let routeNumber = number;
  if (isFullGathaNk(number, nk)) {
    const suffix = number.slice(nk.length + 1);
    const parsed = parseGathaSuffix(suffix);
    if (parsed.isCompound) routeNumber = parsed.compact;
  }
  const isCompound = routeNumber.includes(',');

  // Resolve gatha NK for topic/extract lookups (always the full natural key).
  let gathaNk: string;
  let gatha: Awaited<ReturnType<typeof getGatha>>;

  if (isCompound) {
    gatha = await getGathaByPath(nk, routeNumber, { include: ['teeka_mapping', 'teeka_bhaavarth', 'teeka_sanskrit', 'kalashas'] }).catch((err) => {
      if (err instanceof ApiError && err.status === 404) notFound();
      throw err;
    });
    gathaNk = gatha.natural_key;
  } else {
    gathaNk = routeNumber.includes(':गाथा:') ? routeNumber : `${nk}:गाथा:${routeNumber}`;
    gatha = await getGatha(gathaNk, { include: ['teeka_mapping', 'teeka_bhaavarth', 'teeka_sanskrit', 'kalashas'] }).catch((err) => {
      if (err instanceof ApiError && err.status === 404) notFound();
      throw err;
    });
  }

  // For compound gathas, fetch adjacent navigation server-side.
  const adjacentLinks = isCompound
    ? await getGathaAdjacent(nk, routeNumber).catch(() => null)
    : null;

  const [topicsResult, extractMatches, tR, tS, locale] = await Promise.all([
    getKeywordTopics(gathaNk).catch(() => ({ keyword_natural_key: gathaNk, topics: [] })),
    Promise.all(matchNks.map((mk) => getExtractMatch(mk).catch(() => null))),
    getTranslations('reader'),
    getTranslations('shastras'),
    getLocale(),
  ]);
  const isHi = locale === 'hi';
  const fmtNum = (n: number) => isHi ? toDevanagariNumerals(n) : String(n);
  const gathaLbl = isHi ? 'गाथा' : tS('gatha_label');

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
  const kalashas: GathaKalash[] = Array.isArray(gatha.kalashas) ? [...gatha.kalashas] : [];
  const topics = topicsResult.topics;

  const shastraNk = gatha.shastra.natural_key;

  const matches = (extractMatches as (ExtractMatch | null)[]).filter(
    (m): m is ExtractMatch => m !== null,
  );
  const matchedTargetNks = new Set(
    matches
      .filter((m) => m.match.status === 'matched')
      .map((m) => m.target.natural_key),
  );

  // अन्वयार्थ (शब्दार्थ panel) highlight — the matcher may match a block's Hindi
  // translation against the primary teeka mapping's full_anyavaarth.
  const anvayarthText = primaryMapping
    ? primaryMapping.full_anyavaarth ?? primaryMapping.tagged_terms.map((t) => t.meaning).join(' ')
    : '';
  const anvayarthHighlight = primaryMapping
    ? highlightFor(matches, primaryMapping.natural_key, anvayarthText) ?? null
    : null;

  // Combined-page notice — shown in shared-content panels when this gatha was ingested
  // from a multi-gatha page (e.g. 020-021-022.html). `is_related` holds the sibling numbers.
  const isRelated: string[] = primaryMapping?.is_related ?? [];

  // For sanyukt (combined) gathas, fetch sibling gathas' verse content so the reader
  // can navigate between प्राकृत/संस्कृत/छंद verses without leaving the शब्दार्थ/टीका context.
  const siblingNums = isRelated.length > 0
    ? [gathaNumStr, ...isRelated]
        .map((n) => parseInt(n, 10))
        .filter((n) => !isNaN(n))
        .sort((a, b) => a - b)
        .map((n) => String(n))
    : [gathaNumStr];
  const siblingGathas = isRelated.length > 0
    ? await Promise.all(
        siblingNums.map((n) =>
          n === gathaNumStr
            ? Promise.resolve(gatha)
            : getGatha(`${shastraNk}:गाथा:${n}`, { include: ['kalashas'] }).catch(() => null),
        ),
      )
    : [gatha];

  // Merge kalashas across sanyukt siblings so the "विशेष देखें" panel appears on every
  // page of a combined-gatha block (not just the page whose own gatha node owns them).
  if (isRelated.length > 0) {
    const seen = new Set(kalashas.map((k) => k.natural_key));
    for (const sg of siblingGathas) {
      if (!sg || sg === gatha) continue;
      const sibKalashas = Array.isArray(sg.kalashas) ? sg.kalashas : [];
      for (const k of sibKalashas) {
        if (seen.has(k.natural_key)) continue;
        seen.add(k.natural_key);
        kalashas.push(k);
      }
    }
    kalashas.sort((a, b) => {
      const an = parseInt(a.kalash_number, 10);
      const bn = parseInt(b.kalash_number, 10);
      if (isNaN(an) || isNaN(bn)) return a.kalash_number.localeCompare(b.kalash_number);
      return an - bn;
    });
  }
  const verseEntries: GathaVerseEntry[] = siblingGathas.map((g, i) => {
    const num = siblingNums[i];
    if (!g) return { number: num };
    const prakritText = joinedLangText(g.prakrit?.text);
    const sanskritText = joinedLangText(g.sanskrit?.text);
    return {
      number: num,
      prakrit: g.prakrit && prakritText
        ? {
            text: prakritText,
            naturalKey: g.prakrit.natural_key,
            highlight: highlightFor(matches,g.prakrit.natural_key, prakritText),
          }
        : undefined,
      sanskrit: g.sanskrit
        ? {
            text: sanskritText,
            naturalKey: g.sanskrit.natural_key,
            highlight: highlightFor(matches,g.sanskrit.natural_key, sanskritText),
          }
        : undefined,
      hindiHarigeet: { text: joinedLangText(g.hindi_chhand?.[0]?.text) },
    };
  });
  const combinedGathaNotice = isRelated.length > 0 ? (() => {
    const allNums = [gathaNumStr, ...isRelated]
      .map((n) => parseInt(n, 10))
      .filter((n) => !isNaN(n))
      .sort((a, b) => a - b);
    const devList = formatGathaRange(allNums, isHi);
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
    const devList = formatGathaRange(allNums, isHi);
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
      highlight: highlightFor(matches,ts.natural_key, content),
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
      hasMatch: matchedTargetNks.has(bh.natural_key),
      actionsSourceNk: gathaTeekaBhaavarthNeo4jNk(bh),
      actionsSourceLabel: bh.publication_natural_key ?? bh.natural_key,
      notice: noticeByTeeka.get(teekaNk),
      content: (
        <BhaavarthPanel
          text={bText}
          naturalKey={bh.natural_key}
          highlight={highlightFor(matches,bh.natural_key, bText)}
          className="border-0 p-0 shadow-none"
          shortFontEntries={bh.shortfont_entries}
        />
      ),
    };
  });

  // For each secondary-teeka kalash bhaavarth, siblings are OTHER secondary kalashes
  // with the same teeka AND whose bhaavarth text matches the current bhaavarth.
  // Only when such siblings exist do we show the "{teeka} गाथा N, M, ... का संयुक्त" chip.
  // (Combined-page siblings can share Prakrit/Sanskrit but still carry distinct bhaavarths —
  // those must NOT be marked as संयुक्त.)
  const normalizeForCompare = (s: string): string => normalizeNFC(s).replace(/\s+/g, ' ').trim();
  const secondaryKalashBhaavarthNotice = (
    kalash: GathaKalash,
    bhText: string,
  ): import('react').ReactNode => {
    if (!kalash.is_secondary) return null;
    const target = normalizeForCompare(bhText);
    if (!target) return null;
    const siblings = kalashas.filter(
      (k) =>
        k.is_secondary &&
        k.teeka_natural_key === kalash.teeka_natural_key &&
        k.kalash_number !== kalash.kalash_number &&
        k.bhaavarth.some((b) => normalizeForCompare(joinedLangText(b.text)) === target),
    );
    if (siblings.length === 0) return null;
    const allNums = [kalash.kalash_number, ...siblings.map((s) => s.kalash_number)]
      .map((n) => parseInt(n, 10))
      .filter((n) => !isNaN(n))
      .sort((a, b) => a - b);
    const devList = formatGathaRange(allNums, isHi);
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
    const kalashNks: string[] = [
      kalash.natural_key,
      kalash.prakrit?.natural_key,
      kalash.sanskrit?.natural_key,
      kalash.hindi?.natural_key,
      ...kalash.bhaavarth.map((b) => b.natural_key),
    ].filter((v): v is string => !!v);
    const hasMatch = kalashNks.some((k) => matchedTargetNks.has(k));
    return {
    key: kalash.natural_key,
    label,
    hasMatch,
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
                highlight={highlightFor(matches,kalash.prakrit.natural_key, joinedLangText(kalash.prakrit.text))}
                className="border-l-4 border-l-green-600"
              />
            )}
            {kalash.sanskrit && (
              <BhaavarthPanel
                label="टीका संस्कृत"
                variant="verse"
                text={joinedLangText(kalash.sanskrit.text)}
                naturalKey={kalash.sanskrit.natural_key}
                highlight={highlightFor(matches,kalash.sanskrit.natural_key, joinedLangText(kalash.sanskrit.text))}
              />
            )}
            {kalash.word_meanings && (kalash.word_meanings.entries.length > 0 || !!kalash.word_meanings.full_anyavaarth) && (
              <section className="rounded-[var(--radius-md)] border border-border bg-surface p-5 shadow-node">
                <h2 className="mb-3 font-serif-hindi text-[length:var(--font-size-h3)] font-semibold">शब्दार्थ</h2>
                {kalash.word_meanings.entries.length > 0 ? (
                  <ShabdaArthSection
                    entries={[...kalash.word_meanings.entries]
                      .sort((a, b) => a.position - b.position)
                      .map((e) => ({ word: e.source_word, meaning: e.meaning, position: e.position, startOffset: e.start_offset ?? undefined, endOffset: e.end_offset ?? undefined }))}
                    anvayarth={
                      kalash.word_meanings.full_anyavaarth
                        || [...kalash.word_meanings.entries]
                          .sort((a, b) => a.position - b.position)
                          .map((e) => e.meaning)
                          .join(' ')
                    }
                  />
                ) : (
                  <p className="font-serif-hindi text-sm leading-8 text-foreground">{kalash.word_meanings.full_anyavaarth}</p>
                )}
              </section>
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
                highlight={highlightFor(matches,kalash.sanskrit.natural_key, joinedLangText(kalash.sanskrit.text))}
                className="border-l-4"
                style={{ borderLeftColor: 'var(--cat-teeka)' }}
              />
            )}
            {kalash.hindi && (
              <BhaavarthPanel
                label="कलश हिन्दी"
                variant="verse"
                text={joinedLangText(kalash.hindi.text)}
                naturalKey={kalash.hindi.natural_key}
                highlight={highlightFor(matches,kalash.hindi.natural_key, joinedLangText(kalash.hindi.text))}
                className="border-l-4"
                style={{ borderLeftColor: 'var(--cat-bhaavarth)' }}
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
              notice={secondaryKalashBhaavarthNotice(kalash, bText)}
              text={bText}
              naturalKey={bh.natural_key}
              highlight={highlightFor(matches,bh.natural_key, bText)}
              shortFontEntries={bh.shortfont_entries}
            />
          );
        })}
      </div>
    ),
    };
  });

  // Targets to pulse — every matched panel. HighlightScrollIntoView scrolls to
  // the first one that resolves to a DOM node and pulses the rest in place.
  const scrollTargetNks = matches
    .filter((m) => m.match.status === 'matched')
    .map((m) => m.target.natural_key);

  // Breadcrumb leaf for compound shastras: one chip per identifier field.
  // For legacy shastras: "गाथा N (teeka)" format unchanged.
  const identifier = gatha.identifier;
  let gathaLeafLabel: string;
  let breadcrumbExtraSegments: Array<{ label: string }> = [];

  if (identifier?.is_compound) {
    // Compound: build per-field chips, e.g. "अधिकार १ › गाथा २"
    breadcrumbExtraSegments = identifier.fields.map((f) => ({
      label: `${f.label} ${fmtNum(parseInt(f.value, 10)) || f.value}`,
    }));
    gathaLeafLabel = breadcrumbExtraSegments.map((s) => s.label).join(' › ');
  } else {
    const canonicalGathaDev = fmtNum(parseInt(gatha.gatha_number, 10));
    const primaryTeekaName = primaryMapping
      ? teekaShortName(primaryMapping.teeka_natural_key)
      : null;
    const primaryTeekaNk = primaryMapping?.teeka_natural_key ?? null;
    const teekaNkFromGathaTeekaKey = (key: string | undefined): string | null => {
      if (!key) return null;
      const parts = key.split(':');
      return parts.length >= 3 ? parts.slice(0, -1).join(':') : null;
    };
    const secondaryTeekaCandidates: Array<string | null> = [
      ...teekaMapping.map((m) => m.teeka_natural_key),
      ...teekaBhaavarth.map((b) => teekaNkFromGathaTeekaKey(b.gatha_teeka_natural_key)),
      ...teekaSanskrit.map((s) => s.teeka_natural_key ?? null),
      ...kalashas.filter((k) => k.is_secondary).map((k) => k.teeka_natural_key),
    ];
    const secondaryTeekaNk =
      secondaryTeekaCandidates.find((k): k is string => !!k && k !== primaryTeekaNk) ?? null;
    const markerDev = gatha.prakrit_verse_marker
      ? fmtNum(parseInt(gatha.prakrit_verse_marker, 10))
      : null;
    const primarySegment = [
      `${gathaLbl} ${canonicalGathaDev}`,
      primaryTeekaName ? `(${primaryTeekaName})` : null,
    ]
      .filter(Boolean)
      .join(' ');
    // Only show the secondary-teeka segment when the source provides an explicit
    // ॥N॥ verse marker for this gatha. A missing marker means the gatha is not
    // independently numbered in the secondary teeka.
    const secondarySegment = secondaryTeekaNk && markerDev
      ? `${gathaLbl} ${markerDev} (${teekaShortName(secondaryTeekaNk)})`
      : null;
    gathaLeafLabel = [primarySegment, secondarySegment].filter(Boolean).join(' | ');
  }

  const mainColumn = (
    <div key="main" className="space-y-4">
        <section className="rounded-[var(--radius-md)] border border-border bg-surface p-4 shadow-node">
          <BreadcrumbBar
            maxLabelLength={120}
            segments={[
              { label: tS('title'), href: '/shastras' },
              { label: nk, href: `/shastras/${nk}` },
              ...(identifier?.is_compound && breadcrumbExtraSegments.length > 0
                ? breadcrumbExtraSegments
                : [{ label: gathaLeafLabel }]),
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

        {/* 1-3. प्राकृत / संस्कृत / छंद — grouped, with sanyukt navigators */}
        <GathaVerseGroup entries={verseEntries} />

        {/* 4. शब्दार्थ — word-by-word meanings + full anvayarth */}
        <section className="rounded-[var(--radius-md)] border bg-surface shadow-node overflow-hidden" style={{ borderColor: 'color-mix(in srgb, var(--cat-keyword) 35%, var(--border))', ['--panel-accent' as string]: 'var(--cat-keyword)' }}>
          <div
            className="flex items-start justify-between gap-2 px-5 py-3 border-b"
            style={{
              backgroundColor: 'color-mix(in srgb, var(--cat-keyword) 12%, transparent)',
              borderBottomColor: 'color-mix(in srgb, var(--cat-keyword) 25%, var(--border))',
            }}
          >
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="font-serif-hindi text-[length:var(--font-size-h3)] font-semibold" style={{ color: 'color-mix(in srgb, var(--cat-keyword) 85%, var(--foreground))' }}>{tR('shabdarth')}</h2>
              {combinedGathaNotice?.ka}
            </div>
            <PanelActionsMenu sourceNk={gathaNk} sourceLabel={`${gathaLbl} ${isCompound ? routeNumber : (gatha.gatha_number || number)}`} />
          </div>
          <div className="p-5">
            {primaryMapping?.tagged_terms.length ? (
              <ShabdaArthSection
                entries={primaryMapping.tagged_terms.map((t) => ({
                  word: t.source_word,
                  meaning: t.meaning,
                  position: t.position,
                  startOffset: t.start_offset,
                  endOffset: t.end_offset,
                }))}
                anvayarth={anvayarthText}
                matchHighlight={anvayarthHighlight}
                naturalKey={primaryMapping.natural_key}
              />
            ) : primaryMapping?.full_anyavaarth ? (
              <div data-match-target={primaryMapping.natural_key}>
                <p className="mb-1 text-xs font-medium text-foreground-muted">{tR('anvayarth')}</p>
                <p className="font-serif-hindi text-sm leading-8 text-foreground">
                  {anvayarthHighlight
                    ? (() => {
                        const nfc = primaryMapping.full_anyavaarth.normalize('NFC');
                        const { start, end } = anvayarthHighlight;
                        if (start < 0 || end > nfc.length || start >= end) return primaryMapping.full_anyavaarth;
                        return (
                          <>
                            {nfc.slice(0, start)}
                            <mark className="rounded bg-[var(--accent-soft)] text-[var(--accent)]">{nfc.slice(start, end)}</mark>
                            {nfc.slice(end)}
                          </>
                        );
                      })()
                    : primaryMapping.full_anyavaarth}
                </p>
              </div>
            ) : (
              <p className="text-sm text-foreground-muted">{tR('shabdarth_unavailable')}</p>
            )}
          </div>
        </section>

        {/* संबंधित — kalash/secondary-gatha tabbed panel */}
        {kalashItems.length > 0 && (
          <TabbedPanel title={tR('related')} items={kalashItems} showActions accent="kalash" />
        )}

        {/* Prev / Next navigation — for compound shastras uses server-fetched adjacent links */}
        <GathaPageBottomNav
          shastraNk={shastraNk}
          shastraDisplayNk={nk}
          gathaLabel={gathaLbl}
          adjacentLinks={adjacentLinks
            ? {
                prev: adjacentLinks.previous?.compact ?? null,
                next: adjacentLinks.next?.compact ?? null,
                prevLabel: adjacentLinks.previous
                  ? adjacentLinks.previous.compact
                  : null,
                nextLabel: adjacentLinks.next
                  ? adjacentLinks.next.compact
                  : null,
              }
            : undefined}
        />
      </div>
  );

  const sidebar = (
      <aside key="sidebar" className="space-y-4 lg:sticky lg:top-[90px] lg:self-start lg:max-h-[calc(100vh-110px)] lg:overflow-y-auto">
        <TeekaPanel key="teeka" items={teekaItems} showActions notice={combinedGathaNotice?.ki} accent="teeka" />
        {bhaavarthItems.length > 0 && (
          <TabbedPanel key="bhaavarth" title={tR('hindi_bhaavarth')} items={bhaavarthItems} showActions notice={combinedGathaNotice?.ka} accent="bhaavarth" />
        )}
        {topics.length > 0 && (
          <section key="topics" className="rounded-[var(--radius-md)] border bg-surface shadow-node overflow-hidden" style={{ borderColor: 'color-mix(in srgb, var(--cat-topic) 35%, var(--border))' }}>
            <div
              className="px-5 py-3 border-b"
              style={{
                backgroundColor: 'color-mix(in srgb, var(--cat-topic) 12%, transparent)',
                borderBottomColor: 'color-mix(in srgb, var(--cat-topic) 25%, var(--border))',
              }}
            >
              <h3 className="font-serif-hindi text-[length:var(--font-size-h3)] font-semibold" style={{ color: 'color-mix(in srgb, var(--cat-topic) 85%, var(--foreground))' }}>{tR('related_topics')}</h3>
            </div>
            <div className="p-4 flex flex-wrap gap-2">
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
      {scrollTargetNks.length > 0 && <HighlightScrollIntoView naturalKeys={scrollTargetNks} />}
      <GathaVerseStateProvider initialNumber={gathaNumStr}>
        <GathaReaderLayout main={mainColumn} sidebar={sidebar} />
      </GathaVerseStateProvider>
    </>
  );
}
