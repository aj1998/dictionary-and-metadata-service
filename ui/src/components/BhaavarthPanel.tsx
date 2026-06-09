import { cn } from '@/lib/utils';
import { normalizeNFC } from '@/lib/format/devanagari';
import { splitHighlight } from '@/lib/highlight';
import type { HighlightRange } from '@/lib/highlight';
import { teekaMarkdownToHtml } from '@/lib/format/teeka-markdown';
import { parseBhaavarthSegments } from '@/lib/format/bhaavarth-segments';
import { ShabdaArthSection } from '@/components/ShabdaArthSection';

export interface BhaavarthPanelProps {
  label?: string;
  text: string;
  naturalKey?: string;
  highlight?: HighlightRange;
  className?: string;
  variant?: 'prose' | 'verse';
}

export function BhaavarthPanel({ label, text, naturalKey, highlight, className, variant = 'prose' }: BhaavarthPanelProps) {
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
    >
      {label && (
        <p className="mb-2 text-xs font-medium text-foreground-muted">{label}</p>
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
              const anvayarth = segment.items.map((entry) => entry.meaning).join(' ');
              return (
                <section key={`chips-${index}`} className="rounded-[var(--radius-md)] border border-border/70 bg-surface-2/40 p-4">
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

            if (overlapsHighlight) {
              const localStart = Math.max(0, highlight.start - segment.start);
              const localEnd = Math.min(segment.text.length, highlight.end - segment.start);
              const localSplit = splitHighlight(segment.text, { start: localStart, end: localEnd });

              if (localSplit) {
                return (
                  <p key={`highlight-${index}`} className="whitespace-pre-wrap font-serif-hindi text-[length:var(--font-size-body)] leading-[1.85] text-foreground">
                    {localSplit.before}
                    <mark className="rounded bg-[var(--accent-soft)] text-[var(--accent)]">{localSplit.matched}</mark>
                    {localSplit.after}
                  </p>
                );
              }
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
