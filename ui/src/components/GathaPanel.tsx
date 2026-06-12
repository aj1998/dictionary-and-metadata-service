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

type LangConfig = { label: string; colorVar?: string; border: string; badge: string };

const LANG_CONFIG: Record<GathaPanelProps['lang'], LangConfig> = {
  prakrit: {
    label: 'प्राकृत',
    border: 'border-l-4 border-l-green-600',
    badge: 'bg-green-50 text-green-700 border border-green-200',
  },
  sanskrit: {
    label: 'संस्कृत',
    colorVar: '--cat-teeka',
    border: 'border-l-4',
    badge: 'border',
  },
  'hindi-harigeet': {
    label: 'छंद',
    colorVar: '--cat-bhaavarth',
    border: 'border-l-4',
    badge: 'border',
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

  const colorValue = cfg.colorVar ? `var(${cfg.colorVar})` : undefined;

  return (
    <section
      data-match-target={naturalKey}
      className={cn(
        'rounded-[var(--radius-md)] border border-border bg-surface p-5 shadow-node',
        cfg.border,
        className
      )}
      style={colorValue ? { borderLeftColor: colorValue } : undefined}
    >
      <span
        className={cn('mb-3 inline-block rounded-full px-2 py-0.5 text-xs font-medium', cfg.badge)}
        style={colorValue ? {
          backgroundColor: `color-mix(in srgb, ${colorValue} 12%, transparent)`,
          borderColor: `color-mix(in srgb, ${colorValue} 30%, transparent)`,
          color: `color-mix(in srgb, ${colorValue} 85%, var(--foreground))`,
        } : undefined}
      >
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
