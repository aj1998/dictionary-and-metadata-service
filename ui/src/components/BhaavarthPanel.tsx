import { cn } from '@/lib/utils';
import { normalizeNFC } from '@/lib/format/devanagari';
import { splitHighlight } from '@/lib/highlight';
import type { HighlightRange } from '@/lib/highlight';

export interface BhaavarthPanelProps {
  label?: string;
  text: string;
  naturalKey?: string;
  highlight?: HighlightRange;
  className?: string;
}

export function BhaavarthPanel({ label, text, naturalKey, highlight, className }: BhaavarthPanelProps) {
  const nfcText = normalizeNFC(text);
  const split = highlight ? splitHighlight(nfcText, highlight) : null;

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
      <p className="whitespace-pre-wrap font-serif-hindi text-[length:var(--font-size-body)] leading-[1.85] text-foreground">
        {split ? (
          <>
            {split.before}
            <mark className="rounded bg-[var(--accent-soft)] text-[var(--accent)]">{split.matched}</mark>
            {split.after}
          </>
        ) : (
          nfcText
        )}
      </p>
    </section>
  );
}
