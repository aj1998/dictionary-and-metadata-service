import { cn } from '@/lib/utils';

export interface GathaPanelProps {
  lang: 'prakrit' | 'sanskrit' | 'hindi-harigeet';
  text: string;
  className?: string;
}

export const GATHA_PANEL_ACCENTS: Record<GathaPanelProps['lang'], string> = {
  prakrit: 'border-l-3 border-l-[color:color-mix(in_oklab,var(--cat-shastra)_40%,transparent)]',
  sanskrit: 'border-l-0',
  'hindi-harigeet': 'border-l-3 border-l-[color:color-mix(in_oklab,var(--accent)_40%,transparent)]',
};

export function GathaPanel({ lang, text, className }: GathaPanelProps) {
  return (
    <section
      className={cn(
        'rounded-[var(--radius-md)] border border-border bg-surface p-5 shadow-node',
        GATHA_PANEL_ACCENTS[lang],
        className
      )}
    >
      <p className="whitespace-pre-wrap font-serif-hindi text-[length:var(--font-size-h2)] leading-[1.7] text-foreground">
        {text}
      </p>
    </section>
  );
}
