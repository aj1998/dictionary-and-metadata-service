import { cn } from '@/lib/utils';

export interface GathaPanelProps {
  lang: 'prakrit' | 'sanskrit' | 'hindi-harigeet';
  text: string;
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
};

export function GathaPanel({ lang, text, className }: GathaPanelProps) {
  const cfg = LANG_CONFIG[lang];
  return (
    <section
      className={cn(
        'rounded-[var(--radius-md)] border border-border bg-surface p-5 shadow-node',
        cfg.border,
        className
      )}
    >
      <span className={cn('mb-3 inline-block rounded-full px-2 py-0.5 text-xs font-medium', cfg.badge)}>
        {cfg.label}
      </span>
      <p className="whitespace-pre-wrap font-serif-hindi text-[length:var(--font-size-h2)] leading-[1.85] text-foreground">
        {text}
      </p>
    </section>
  );
}
