'use client';

import { useState, type ReactNode } from 'react';
import { cn } from '@/lib/utils';
import { PanelActionsMenu } from './PanelActionsMenu';

export interface TabbedPanelItem {
  key: string;
  label: string;
  content: ReactNode;
  actionsSourceNk?: string;
  actionsSourceLabel?: string;
}

interface TabbedPanelProps {
  title?: string;
  items: TabbedPanelItem[];
  emptyMessage?: string;
  bodyClassName?: string;
  showActions?: boolean;
  notice?: ReactNode;
}

export function TabbedPanel({ title, items, emptyMessage, bodyClassName, showActions, notice }: TabbedPanelProps) {
  const [active, setActive] = useState(0);

  if (items.length === 0) {
    if (!emptyMessage) return null;
    return (
      <section className="rounded-[var(--radius-md)] border border-border bg-surface p-5 shadow-node">
        {title && <h3 className="mb-3 font-serif-hindi text-base font-semibold">{title}</h3>}
        <p className="text-sm text-foreground-muted">{emptyMessage}</p>
      </section>
    );
  }

  const current = items[Math.min(active, items.length - 1)];

  return (
    <section className="rounded-[var(--radius-md)] border border-border bg-surface shadow-node overflow-hidden">
      {(title || (showActions && current.actionsSourceNk)) && (
        <div className="flex items-start justify-between gap-2 px-5 pt-5 pb-3">
          {title ? (
            <div className="flex flex-wrap items-center gap-2">
              <h3 className="font-serif-hindi text-base font-semibold text-foreground">{title}</h3>
              {notice}
            </div>
          ) : <span />}
          {showActions && current.actionsSourceNk && (
            <PanelActionsMenu
              sourceNk={current.actionsSourceNk}
              sourceLabel={current.actionsSourceLabel ?? current.label}
            />
          )}
        </div>
      )}

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

      {items.length === 1 && title && (
        <p className="px-5 pb-1 text-xs text-foreground-muted">{current.label}</p>
      )}
      <div className={cn('px-5 py-4', bodyClassName)}>{current.content}</div>
    </section>
  );
}
