'use client';

import { useState, type ReactNode } from 'react';
import { cn } from '@/lib/utils';
import { PanelActionsMenu } from './PanelActionsMenu';
import { panelAccentRootStyle, panelAccentHeaderStyle, panelAccentTitleStyle, type PanelAccent } from '@/lib/panel-accent';

export interface TabbedPanelItem {
  key: string;
  label: string;
  content: ReactNode;
  actionsSourceNk?: string;
  actionsSourceLabel?: string;
  notice?: ReactNode;
  /** When true, the tab indicator turns accent-coloured to signal the matcher landed in this tab. */
  hasMatch?: boolean;
}

interface TabbedPanelProps {
  title?: string;
  items: TabbedPanelItem[];
  emptyMessage?: string;
  bodyClassName?: string;
  showActions?: boolean;
  notice?: ReactNode;
  accent?: PanelAccent;
}

export function TabbedPanel({ title, items, emptyMessage, bodyClassName, showActions, notice, accent }: TabbedPanelProps) {
  const initialMatchIdx = items.findIndex((item) => item.hasMatch);
  const [active, setActive] = useState(initialMatchIdx >= 0 ? initialMatchIdx : 0);

  if (items.length === 0) {
    if (!emptyMessage) return null;
    return (
      <section className="rounded-[var(--radius-md)] border border-border bg-surface shadow-node overflow-hidden" style={panelAccentRootStyle(accent)}>
        {title && (
          <div className="px-5 py-3 border-b border-border" style={panelAccentHeaderStyle(accent)}>
            <h3 className="font-serif-hindi text-base font-semibold" style={panelAccentTitleStyle(accent)}>{title}</h3>
          </div>
        )}
        <div className="p-5"><p className="text-sm text-foreground-muted">{emptyMessage}</p></div>
      </section>
    );
  }

  const current = items[Math.min(active, items.length - 1)];

  return (
    <section
      className="rounded-[var(--radius-md)] border border-border bg-surface shadow-node overflow-hidden"
      style={panelAccentRootStyle(accent)}
    >
      {(title || (showActions && current.actionsSourceNk)) && (
        <div
          className={cn('flex items-start justify-between gap-2 px-5 py-3', accent ? 'border-b' : '')}
          style={panelAccentHeaderStyle(accent)}
        >
          {title ? (
            <div className="flex flex-wrap items-center gap-2">
              <h3 className="font-serif-hindi text-base font-semibold" style={panelAccentTitleStyle(accent)}>{title}</h3>
              {current.notice ?? notice}
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
        <div className="flex overflow-x-auto border-b border-border px-5 pt-3 gap-1">
          {items.map((item, i) => (
            <button
              key={item.key}
              onClick={() => setActive(i)}
              className={cn(
                'shrink-0 pb-2 pt-1 px-3 text-xs font-medium border-b-2 transition-colors whitespace-nowrap',
                i === active
                  ? 'border-accent text-accent'
                  : 'border-transparent text-foreground-muted hover:text-foreground',
                item.hasMatch && i !== active && 'text-accent'
              )}
            >
              {item.label}
            </button>
          ))}
        </div>
      )}

      {items.length === 1 && title && (
        <p className="px-5 pt-3 pb-1 text-xs text-foreground-muted">{current.label}</p>
      )}
      <div className={cn('px-5 py-4', bodyClassName)}>{current.content}</div>
    </section>
  );
}
