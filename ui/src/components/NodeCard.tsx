'use client';

import { cn } from '@/lib/utils';
import { ChevronRight, Maximize2, Pin, BookOpen, ScrollText, Tag, Sparkles } from '@/lib/icons';
import type { EntityKind } from '@/lib/types';

export const EXPAND_ARIA_LABEL = 'इस नोड से ग्राफ़ का विस्तार करें';
export const DETAILS_ARIA_LABEL = 'विवरण देखें';

export const NODE_KIND_META: Record<
  EntityKind,
  {
    labelHi: string;
    labelEn: string;
    Icon: React.ComponentType<{ size?: number; className?: string; strokeWidth?: number }>;
    catVar: string;
  }
> = {
  shastra: { labelHi: 'शास्त्र', labelEn: 'Shastra', Icon: BookOpen,   catVar: 'var(--cat-shastra)' },
  gatha:   { labelHi: 'गाथा',   labelEn: 'Gatha',   Icon: ScrollText, catVar: 'var(--cat-gatha)'   },
  topic:   { labelHi: 'विषय',   labelEn: 'Topic',   Icon: Tag,        catVar: 'var(--cat-topic)'   },
  keyword: { labelHi: 'कीवर्ड',  labelEn: 'Keyword', Icon: Sparkles,   catVar: 'var(--cat-keyword)' },
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
  const { labelHi, labelEn, Icon, catVar } = NODE_KIND_META[kind];

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
      {/* 4 px cat-stripe (hidden when selected — fill replaces it) */}
      {!selected && (
        <div
          className="h-1 rounded-t-[var(--radius-md)]"
          style={{ backgroundColor: catVar }}
        />
      )}

      {/* Header row */}
      <div
        className={cn(
          'relative flex items-center gap-2 px-3 pb-2',
          selected ? 'pt-3' : 'pt-2',
        )}
      >
        {/* Icon box */}
        <div
          className={cn(
            'flex h-6 w-6 shrink-0 items-center justify-center rounded-[var(--radius-sm)]',
            selected ? 'bg-white/20' : 'bg-surface-muted',
          )}
        >
          <Icon
            size={16}
            strokeWidth={1.5}
            className={selected ? 'text-white' : 'text-foreground-muted'}
          />
        </div>

        {/* Type labels */}
        <div className="min-w-0 flex-1">
          <div
            className={cn(
              'text-[length:var(--font-size-sm)] font-semibold leading-tight',
              selected ? 'text-white' : 'text-foreground',
            )}
          >
            {labelHi}
          </div>
          <div
            className={cn(
              'text-[length:var(--font-size-xs)] leading-tight',
              selected ? 'text-white/70' : 'text-foreground-muted',
            )}
          >
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
              selected ? 'text-white/80 hover:text-white' : 'text-foreground-muted hover:text-foreground',
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
                  'text-foreground-subtle hover:text-foreground focus-visible:outline-accent',
                  expanded && 'text-accent',
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
              : 'text-foreground-subtle hover:text-foreground focus-visible:outline-accent',
          )}
        >
          <ChevronRight size={16} strokeWidth={1.5} />
        </button>
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
