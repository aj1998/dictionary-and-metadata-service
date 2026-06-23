import { cn } from '@/lib/utils';
import { normalizeNFC } from '@/lib/format/devanagari';
import { splitHighlight } from '@/lib/highlight';
import type { HighlightRange } from '@/lib/highlight';
import { teekaMarkdownToHtml } from '@/lib/format/teeka-markdown';
import { parseBhaavarthSegments } from '@/lib/format/bhaavarth-segments';
import { injectHighlightAndShortFont, postProcessHighlightHtml } from '@/lib/format/bhaavarth-highlight';
import {
  getSegmentEntries,
  injectShortFontSentinels,
  postProcessShortFontHtml,
} from '@/lib/format/bhaavarth-shortfont';
import { ShabdaArthSection } from '@/components/ShabdaArthSection';
import { ShortFontHtml } from '@/components/ShortFontHtml';
import { panelAccentRootStyle, panelAccentTitleStyle, type PanelAccent } from '@/lib/panel-accent';
import type { BhaavarthShortFontEntry } from '@/lib/types';

export interface BhaavarthPanelProps {
  label?: string;
  text: string;
  naturalKey?: string;
  highlight?: HighlightRange;
  className?: string;
  variant?: 'prose' | 'verse';
  notice?: import('react').ReactNode;
  accent?: PanelAccent;
  shortFontEntries?: BhaavarthShortFontEntry[];
  style?: import('react').CSSProperties;
}

export function BhaavarthPanel({ label, text, naturalKey, highlight, className, variant = 'prose', notice, accent, shortFontEntries, style: styleProp }: BhaavarthPanelProps) {
  const nfcText = normalizeNFC(text);
  const split = highlight ? splitHighlight(nfcText, highlight) : null;
  const segments = variant === 'prose' ? parseBhaavarthSegments(nfcText) : null;

  if (highlight && !split) {
    console.warn('[BhaavarthPanel] highlight range out of bounds', { naturalKey, highlight, textLen: nfcText.length });
  }

  return (
    <section
      data-match-target={naturalKey}
      className={cn(
        'rounded-[var(--radius-md)] border border-border bg-surface p-5 shadow-node',
        className
      )}
      style={{ ...panelAccentRootStyle(accent), ...styleProp }}
    >
      {(label || notice) && (
        <div className="mb-2 flex flex-wrap items-center gap-2">
          {label && <p className="text-xs font-medium" style={accent ? panelAccentTitleStyle(accent) : { color: 'var(--foreground-muted)' }}>{label}</p>}
          {notice}
        </div>
      )}
      {split && variant !== 'prose' ? (
        <p className="whitespace-pre-wrap font-serif-hindi text-[length:var(--font-size-body)] leading-[1.85] text-foreground">
          {split.before}
          <mark className="rounded bg-[var(--accent-soft)] text-[var(--accent)]">{split.matched}</mark>
          {split.after}
        </p>
      ) : variant === 'verse' ? (
        <p className="whitespace-pre-wrap font-serif-hindi text-[length:var(--font-size-body)] leading-[1.85] text-foreground">
          {nfcText}
        </p>
      ) : (
        <div className="space-y-4">
          {segments!.map((segment, index) => {
            if (segment.kind === 'chips') {
              if (segment.items.length === 1) {
                const rawSlice = nfcText.slice(segment.start, segment.end);
                return (
                  <div
                    key={`html-${index}`}
                    className="font-serif-hindi text-[length:var(--font-size-body)] leading-[1.85] text-foreground teeka-content"
                    dangerouslySetInnerHTML={{ __html: teekaMarkdownToHtml(rawSlice) }}
                  />
                );
              }
              const anvayarth = segment.items.map((entry) => entry.meaning).join(' ');
              return (
                <section key={`chips-${index}`} className="rounded-[var(--radius-md)] border border-border bg-[var(--background)] p-4">
                  <ShabdaArthSection
                    entries={segment.items.map((e) => ({ word: e.word, meaning: e.meaning }))}
                    anvayarth={anvayarth}
                  />
                </section>
              );
            }

            const overlapsHighlight = highlight
              && highlight.start < segment.end
              && highlight.end > segment.start;

            const sfEntries = shortFontEntries?.length
              ? getSegmentEntries(shortFontEntries, segment.start, segment.end)
              : [];

            if (overlapsHighlight) {
              const localStart = Math.max(0, highlight.start - segment.start);
              const localEnd = Math.min(segment.text.length, highlight.end - segment.start);
              // Splice the highlight sentinel — and any shortfont sentinels — into
              // the RAW markdown text, then run markdown→HTML so the matched span
              // stays formatted (italic glosses, emphasis) instead of leaking raw
              // markers like `*((…))*`, AND keeps its clickable shortfont anchors.
              const injected = injectHighlightAndShortFont(
                segment.text,
                sfEntries.map((e) => ({ localStart: e.localStart, localEnd: e.localEnd, entryIdx: e.entryIdx })),
                localStart,
                localEnd,
              );
              const rendered = teekaMarkdownToHtml(injected);
              const html = postProcessHighlightHtml(postProcessShortFontHtml(rendered));
              if (sfEntries.length > 0) {
                return (
                  <ShortFontHtml
                    key={`highlight-${index}`}
                    html={html}
                    entries={shortFontEntries!}
                    className="font-serif-hindi text-[length:var(--font-size-body)] leading-[1.85] text-foreground teeka-content"
                  />
                );
              }
              return (
                <div
                  key={`highlight-${index}`}
                  className="font-serif-hindi text-[length:var(--font-size-body)] leading-[1.85] text-foreground teeka-content"
                  dangerouslySetInnerHTML={{ __html: html }}
                />
              );
            }

            if (sfEntries.length > 0) {
              const injected = injectShortFontSentinels(segment.text, sfEntries);
              const rawHtml = teekaMarkdownToHtml(injected);
              const processedHtml = postProcessShortFontHtml(rawHtml);
              return (
                <ShortFontHtml
                  key={`html-${index}`}
                  html={processedHtml}
                  entries={shortFontEntries!}
                  className="font-serif-hindi text-[length:var(--font-size-body)] leading-[1.85] text-foreground teeka-content"
                />
              );
            }

            return (
              <div
                key={`html-${index}`}
                className="font-serif-hindi text-[length:var(--font-size-body)] leading-[1.85] text-foreground teeka-content"
                dangerouslySetInnerHTML={{ __html: teekaMarkdownToHtml(segment.text) }}
              />
            );
          })}
        </div>
      )}
    </section>
  );
}
