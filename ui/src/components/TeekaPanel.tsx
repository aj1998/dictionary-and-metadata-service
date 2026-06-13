'use client';

import { useState, type ReactNode } from 'react';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils';
import { teekaMarkdownToHtml } from '@/lib/format/teeka-markdown';
import { splitHighlight } from '@/lib/highlight';
import type { HighlightRange } from '@/lib/highlight';
import { normalizeNFC } from '@/lib/format/devanagari';
import { PanelActionsMenu } from './PanelActionsMenu';
import { panelAccentRootStyle, panelAccentHeaderStyle, panelAccentTitleStyle, type PanelAccent } from '@/lib/panel-accent';

export interface TeekaPanelItem {
  key: string;
  label: string;
  content: string;
  naturalKey?: string;
  actionsSourceNk?: string;
  highlight?: HighlightRange;
}

interface TeekaPanelProps {
  items: TeekaPanelItem[];
  showActions?: boolean;
  notice?: ReactNode;
  accent?: PanelAccent;
}


export function TeekaPanel({ items, showActions, notice, accent }: TeekaPanelProps) {
  const tR = useTranslations('reader');
  const teekaTitle = tR('teeka');
  const initialActive = items.findIndex((item) => item.highlight != null);
  const [active, setActive] = useState(initialActive >= 0 ? initialActive : 0);

  if (items.length === 0) {
    return (
      <section className="rounded-[var(--radius-md)] border border-border bg-surface shadow-node overflow-hidden" style={panelAccentRootStyle(accent)}>
        <div className={cn('px-5 py-3', accent ? 'border-b' : '')} style={panelAccentHeaderStyle(accent)}>
          <h3 className="font-serif-hindi text-base font-semibold" style={panelAccentTitleStyle(accent)}>{teekaTitle}</h3>
        </div>
        <div className="p-5"><p className="text-sm text-foreground-muted">{teekaTitle} {tR('shabdarth_unavailable').includes('unavailable') ? 'unavailable.' : 'उपलब्ध नहीं है।'}</p></div>
      </section>
    );
  }

  const current = items[active] ?? items[0];
  const hasAnyHighlight = items.some((it) => it.highlight != null);

  return (
    <section
      className="rounded-[var(--radius-md)] border border-border bg-surface shadow-node overflow-hidden"
      style={panelAccentRootStyle(accent)}
    >
      <div className={cn('flex items-start justify-between gap-2 px-5 py-3', accent ? 'border-b' : '')} style={panelAccentHeaderStyle(accent)}>
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="font-serif-hindi text-base font-semibold" style={panelAccentTitleStyle(accent)}>{teekaTitle}</h3>
          {notice}
        </div>
        {showActions && (current.actionsSourceNk ?? current.naturalKey ?? current.key) && (
          <PanelActionsMenu
            sourceNk={current.actionsSourceNk ?? current.naturalKey ?? current.key}
            sourceLabel={current.label}
          />
        )}
      </div>

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
                item.highlight != null && i !== active && 'text-accent',
              )}
            >
              {item.label}
            </button>
          ))}
        </div>
      )}

      {items.length === 1 && (
        <p className="px-5 pt-3 pb-1 text-xs text-foreground-muted">{current.label}</p>
      )}

      <div
        data-match-target={current.naturalKey}
        className="px-5 py-4 overflow-y-auto max-h-[55vh] font-serif-hindi text-sm leading-8 text-foreground teeka-content"
        /* content is from internal DB, not user input */
        dangerouslySetInnerHTML={{
          __html: (() => {
            const nfc = normalizeNFC(current.content);
            const split = current.highlight ? splitHighlight(nfc, current.highlight) : null;
            if (!split) return teekaMarkdownToHtml(nfc);
            return (
              teekaMarkdownToHtml(split.before) +
              `<mark class="rounded bg-[var(--accent-soft)] text-[var(--accent)]">${split.matched}</mark>` +
              teekaMarkdownToHtml(split.after)
            );
          })(),
        }}
      />
    </section>
  );
}
