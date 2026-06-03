import { cn } from '@/lib/utils';
import { normalizeNFC } from '@/lib/format/devanagari';
import { splitHighlight } from '@/lib/highlight';
import type { HighlightRange } from '@/lib/highlight';
import { teekaMarkdownToHtml } from '@/lib/format/teeka-markdown';

export interface GathaPanelProps {
  lang: 'prakrit' | 'sanskrit' | 'hindi-harigeet' | 'sanskrit-teeka';
  text: string;
  naturalKey?: string;
  highlight?: HighlightRange;
  label?: string;
  className?: string;
}

const LANG_CONFIG: Record<GathaPanelProps['lang'], { label: string; border: string; badge: string }> = {
  prakrit: {
    label: 'प्राकृत',
    border: 'border-l-4 border-l-amber-500',
    badge: 'bg-amber-50 text-amber-700 border border-amber-200',
  },
  sanskrit: {
    label: 'संस्कृत',
    border: 'border-l-4 border-l-indigo-500',
    badge: 'bg-indigo-50 text-indigo-700 border border-indigo-200',
  },
  'hindi-harigeet': {
    label: 'छंद',
    border: 'border-l-4 border-l-teal-500',
    badge: 'bg-teal-50 text-teal-700 border border-teal-200',
  },
  'sanskrit-teeka': {
    label: 'संस्कृत टीका',
    border: 'border-l-4 border-l-violet-500',
    badge: 'bg-violet-50 text-violet-700 border border-violet-200',
  },
};

export function GathaPanel({ lang, text, naturalKey, highlight, label, className }: GathaPanelProps) {
  const cfg = LANG_CONFIG[lang];
  const nfcText = normalizeNFC(text);
  const split = highlight ? splitHighlight(nfcText, highlight) : null;

  if (highlight && !split) {
    console.warn('[GathaPanel] highlight range out of bounds', { naturalKey, highlight, textLen: nfcText.length });
  }

  return (
    <section
      data-match-target={naturalKey}
      className={cn(
        'rounded-[var(--radius-md)] border border-border bg-surface p-5 shadow-node',
        cfg.border,
        className
      )}
    >
      <span className={cn('mb-3 inline-block rounded-full px-2 py-0.5 text-xs font-medium', cfg.badge)}>
        {label ?? cfg.label}
      </span>
      {split ? (
        <p className="whitespace-pre-wrap font-serif-hindi text-[length:var(--font-size-h2)] leading-[1.85] text-foreground">
          {split.before}
          <mark className="rounded bg-[var(--accent-soft)] text-[var(--accent)]">{split.matched}</mark>
          {split.after}
        </p>
      ) : lang === 'sanskrit-teeka' ? (
        <div
          className="font-serif-hindi text-[length:var(--font-size-body)] leading-[1.85] text-foreground teeka-content"
          dangerouslySetInnerHTML={{ __html: teekaMarkdownToHtml(nfcText) }}
        />
      ) : (
        <p className="whitespace-pre-wrap font-serif-hindi text-[length:var(--font-size-h2)] leading-[1.85] text-foreground">
          {nfcText}
        </p>
      )}
    </section>
  );
}
