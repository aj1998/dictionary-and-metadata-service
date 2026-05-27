'use client';

import { useState } from 'react';
import { cn } from '@/lib/utils';

export interface TeekaPanelItem {
  key: string;
  label: string;
  content: string;
}

interface TeekaPanelProps {
  items: TeekaPanelItem[];
}

function markdownToHtml(text: string): string {
  return text
    .replace(/\*\*([^*\n]+)\*\*/g, '<strong>$1</strong>')
    .replace(/(?<!\*)\*([^*\n]+)\*(?!\*)/g, '<em>$1</em>')
    .replace(/\n\n+/g, '<br/><br/>')
    .replace(/\n/g, '<br/>');
}

export function TeekaPanel({ items }: TeekaPanelProps) {
  const [active, setActive] = useState(0);

  if (items.length === 0) {
    return (
      <section className="rounded-[var(--radius-md)] border border-border bg-surface p-5 shadow-node">
        <h3 className="mb-3 font-serif-hindi text-base font-semibold">टीका</h3>
        <p className="text-sm text-foreground-muted">टीका उपलब्ध नहीं है।</p>
      </section>
    );
  }

  const current = items[active];

  return (
    <section className="rounded-[var(--radius-md)] border border-border bg-surface shadow-node overflow-hidden">
      <div className="px-5 pt-5 pb-3">
        <h3 className="font-serif-hindi text-base font-semibold text-foreground">टीका</h3>
      </div>

      {items.length > 1 && (
        <div className="flex overflow-x-auto border-b border-border px-5 gap-1">
          {items.map((item, i) => (
            <button
              key={item.key}
              onClick={() => setActive(i)}
              className={cn(
                'shrink-0 pb-2 pt-1 px-3 text-xs font-medium border-b-2 transition-colors whitespace-nowrap',
                i === active
                  ? 'border-accent text-accent'
                  : 'border-transparent text-foreground-muted hover:text-foreground'
              )}
            >
              {item.label}
            </button>
          ))}
        </div>
      )}

      {items.length === 1 && (
        <p className="px-5 pb-1 text-xs text-foreground-muted">{current.label}</p>
      )}

      <div
        className="px-5 py-4 overflow-y-auto max-h-[55vh] font-serif-hindi text-sm leading-8 text-foreground teeka-content"
        /* content is from internal DB, not user input */
        dangerouslySetInnerHTML={{ __html: markdownToHtml(current.content) }}
      />
    </section>
  );
}
