'use client';

import { cn } from '@/lib/utils';
import { ChevronRight, Maximize2, Pin, BookOpen, ScrollText, BookMarked, BookText, NotebookText, Flower2, FileText, Tag, Sparkles, Building2 } from '@/lib/icons';
import type { EntityKind } from '@/lib/types';

export const EXPAND_ARIA_LABEL = 'इस नोड से ग्राफ़ का विस्तार करें';
export const DETAILS_ARIA_LABEL = 'विवरण देखें';

// Stub-seed topics have a pure-numeric title_hi (their resolve_key number).
// Show the full natural key instead so the card is identifiable.
export function resolveNodeTitle(nk: string, kind: EntityKind, titleHi: string): string {
  if (kind === 'topic' && /^\d+$/.test(titleHi.trim())) return nk;
  return titleHi;
}

export const NODE_KIND_META: Record<
  EntityKind,
  {
    labelHi: string;
    labelEn: string;
    Icon: React.ComponentType<{ size?: number; className?: string; strokeWidth?: number }>;
    catVar: string;
    bandFg: string;
    bandIconBoxBg: string;
  }
> = {
  shastra:     { labelHi: 'शास्त्र',    labelEn: 'Shastra',     Icon: BookOpen,     catVar: 'var(--cat-shastra)',     bandFg: 'var(--cat-shastra-fg)',     bandIconBoxBg: 'rgba(255,255,255,0.18)' },
  gatha:       { labelHi: 'गाथा',      labelEn: 'Gatha',       Icon: ScrollText,   catVar: 'var(--cat-gatha)',       bandFg: 'var(--cat-gatha-fg)',       bandIconBoxBg: 'rgba(0,0,0,0.10)' },
  gatha_teeka: { labelHi: 'गाथा टीका', labelEn: 'GathaTeeka',  Icon: BookText,     catVar: 'var(--cat-gatha-teeka)', bandFg: 'var(--cat-gatha-teeka-fg)', bandIconBoxBg: 'rgba(0,0,0,0.10)' },
  teeka:       { labelHi: 'टीका',      labelEn: 'Teeka',       Icon: BookMarked,   catVar: 'var(--cat-teeka)',       bandFg: 'var(--cat-teeka-fg)',       bandIconBoxBg: 'rgba(255,255,255,0.18)' },
  bhaavarth:   { labelHi: 'भावार्थ',   labelEn: 'Bhaavarth',   Icon: NotebookText, catVar: 'var(--cat-bhaavarth)',   bandFg: 'var(--cat-bhaavarth-fg)',   bandIconBoxBg: 'rgba(255,255,255,0.18)' },
  kalash:      { labelHi: 'कलश',       labelEn: 'Kalash',      Icon: Flower2,      catVar: 'var(--cat-kalash)',      bandFg: 'var(--cat-kalash-fg)',      bandIconBoxBg: 'rgba(255,255,255,0.18)' },
  page:        { labelHi: 'पृष्ठ',     labelEn: 'Page',        Icon: FileText,     catVar: 'var(--cat-page)',        bandFg: 'var(--cat-page-fg)',        bandIconBoxBg: 'rgba(255,255,255,0.18)' },
  topic:       { labelHi: 'विषय',      labelEn: 'Topic',       Icon: Tag,          catVar: 'var(--cat-topic)',       bandFg: 'var(--cat-topic-fg)',       bandIconBoxBg: 'rgba(0,0,0,0.10)' },
  keyword:     { labelHi: 'कीवर्ड',    labelEn: 'Keyword',     Icon: Sparkles,     catVar: 'var(--cat-keyword)',     bandFg: 'var(--cat-keyword-fg)',     bandIconBoxBg: 'rgba(0,0,0,0.10)' },
  publication: { labelHi: 'प्रकाशन',   labelEn: 'Publication', Icon: Building2,    catVar: 'var(--cat-publication)', bandFg: 'var(--cat-publication-fg)', bandIconBoxBg: 'rgba(255,255,255,0.18)' },
};

export interface NodeCardProps {
  id: string;
  kind: EntityKind;
  titleHi: string;
  titleEn?: string;
  selected?: boolean;
  pinned?: boolean;
  faded?: boolean;
  expanded?: boolean;
  onClick?(): void;
  onDoubleClick?(): void;
  onPinToggle?(): void;
  onExpand?(): void;
  className?: string;
}

export function NodeCard({
  id: _id,
  kind,
  titleHi,
  titleEn,
  selected = false,
  pinned = false,
  faded = false,
  expanded = false,
  onClick,
  onDoubleClick,
  onPinToggle,
  onExpand,
  className,
}: NodeCardProps) {
  const { labelHi, labelEn, Icon, catVar, bandFg, bandIconBoxBg } = NODE_KIND_META[kind];

  return (
    <div
      role="button"
      aria-pressed={selected}
      aria-label={`${labelEn}: ${titleHi}${titleEn ? ` (${titleEn})` : ''}`}
      tabIndex={faded ? -1 : 0}
      onClick={onClick}
      onDoubleClick={onDoubleClick}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') onClick?.();
      }}
      style={{ width: 220 }}
      className={cn(
        'relative min-h-[64px] cursor-pointer select-none rounded-[var(--radius-md)] border',
        'transition-[box-shadow,border-color,background-color] duration-[120ms] ease-out',
        selected
          ? 'border-accent bg-accent text-white shadow-[var(--node-shadow-hover)]'
          : [
              'border-node-border bg-node-bg shadow-[var(--node-shadow)]',
              'hover:border-[color-mix(in_srgb,var(--accent)_40%,transparent)]',
              'hover:shadow-[var(--node-shadow-hover)]',
            ],
        faded && 'pointer-events-none opacity-25',
        className,
      )}
    >
      {/* Header band — full-width, tinted with category color when not selected */}
      <div
        className="relative rounded-t-[var(--radius-md)] px-3 pb-2 pt-3"
        style={selected ? undefined : { backgroundColor: catVar, color: bandFg }}
      >
        <div className="flex items-center gap-2">
          {/* Icon box */}
          <div
            className={cn('flex h-6 w-6 shrink-0 items-center justify-center rounded-[var(--radius-sm)]', selected && 'bg-white/20')}
            style={selected ? undefined : { backgroundColor: bandIconBoxBg }}
          >
            <Icon
              size={16}
              strokeWidth={1.5}
              className={selected ? 'text-white' : undefined}
            />
          </div>

          {/* Type labels */}
          <div className="min-w-0 flex-1">
            <div className={cn('text-[14px] font-semibold leading-tight', selected && 'text-white')}>
              {labelHi}
            </div>
            <div className={cn('text-[length:var(--font-size-xs)] leading-tight', selected ? 'text-white/70' : 'opacity-80')}>
              {labelEn}
            </div>
          </div>

          {/* Pin indicator */}
          {pinned && (
            <button
              type="button"
              aria-label="Unpin node"
              onClick={(e) => {
                e.stopPropagation();
                onPinToggle?.();
              }}
              className={cn(
                'absolute right-[72px] top-2 rounded p-0.5',
                selected ? 'text-white/80 hover:text-white' : 'opacity-60 hover:opacity-100',
              )}
            >
              <Pin size={12} strokeWidth={1.5} />
            </button>
          )}

          {/* Expand button */}
          <button
            type="button"
            aria-label={EXPAND_ARIA_LABEL}
            aria-pressed={expanded}
            onClick={(e) => {
              e.stopPropagation();
              onExpand?.();
            }}
            className={cn(
              'flex h-8 w-8 shrink-0 items-center justify-center rounded focus-visible:outline-2 focus-visible:outline-offset-1',
              selected
                ? 'text-white/60 hover:text-white focus-visible:outline-white'
                : [
                    'opacity-70 hover:opacity-100 focus-visible:outline-accent',
                    expanded && 'opacity-100',
                  ],
            )}
          >
            <Maximize2 size={14} strokeWidth={1.5} />
          </button>

          {/* Details button */}
          <button
            type="button"
            aria-label={DETAILS_ARIA_LABEL}
            onClick={(e) => {
              e.stopPropagation();
              onClick?.();
            }}
            className={cn(
              'flex h-8 w-8 shrink-0 items-center justify-center rounded focus-visible:outline-2 focus-visible:outline-offset-1',
              selected
                ? 'text-white/60 hover:text-white focus-visible:outline-white'
                : 'opacity-70 hover:opacity-100 focus-visible:outline-accent',
            )}
          >
            <ChevronRight size={16} strokeWidth={1.5} />
          </button>
        </div>
      </div>

      {/* Separator */}
      <div className={cn('h-px', selected ? 'bg-white/20' : 'bg-border')} />

      {/* Body row */}
      <div className="px-3 pb-3 pt-2">
        <div
          className={cn(
            'line-clamp-2 font-serif-hindi text-[length:var(--font-size-h3)] font-semibold leading-snug',
            selected ? 'text-white' : 'text-foreground',
          )}
        >
          {titleHi}
        </div>
        {titleEn && (
          <div
            className={cn(
              'mt-0.5 truncate text-[length:var(--font-size-xs)]',
              selected ? 'text-white/70' : 'text-foreground-muted',
            )}
          >
            {titleEn}
          </div>
        )}
      </div>
    </div>
  );
}
