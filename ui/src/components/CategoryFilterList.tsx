'use client';

import { Switch } from '@/components/ui/switch';
import { Separator } from '@/components/ui/separator';
import { cn } from '@/lib/utils';
import type { EntityKind } from '@/lib/types';

export const CATEGORY_DATA: Array<{
  kind: EntityKind;
  labelHi: string;
  labelEn: string;
  catVar: string;
}> = [
  { kind: 'shastra',     labelHi: 'शास्त्र',    labelEn: 'Shastra',     catVar: 'var(--cat-shastra)' },
  { kind: 'gatha',       labelHi: 'गाथा',       labelEn: 'Gatha',       catVar: 'var(--cat-gatha)' },
  { kind: 'gatha_teeka', labelHi: 'गाथा टीका',  labelEn: 'GathaTeeka',  catVar: 'var(--cat-gatha-teeka)' },
  { kind: 'teeka',       labelHi: 'टीका',       labelEn: 'Teeka',       catVar: 'var(--cat-teeka)' },
  { kind: 'bhaavarth',   labelHi: 'भावार्थ',    labelEn: 'Bhaavarth',   catVar: 'var(--cat-bhaavarth)' },
  { kind: 'kalash',      labelHi: 'कलश',        labelEn: 'Kalash',      catVar: 'var(--cat-kalash)' },
  { kind: 'page',        labelHi: 'पृष्ठ',      labelEn: 'Page',        catVar: 'var(--cat-page)' },
  { kind: 'topic',       labelHi: 'विषय',       labelEn: 'Topic',       catVar: 'var(--cat-topic)' },
  { kind: 'keyword',     labelHi: 'कीवर्ड',     labelEn: 'Keyword',     catVar: 'var(--cat-keyword)' },
  { kind: 'publication', labelHi: 'प्रकाशन',    labelEn: 'Publication', catVar: 'var(--cat-publication)' },
];

const LAYOUT_OPTIONS = [
  { value: 'force', labelHi: 'बल', labelEn: 'Force', enabled: true },
  { value: 'radial', labelHi: 'रेडियल', labelEn: 'Radial', enabled: true },
  { value: 'hierarchical', labelHi: 'पदानुक्रम', labelEn: 'Hierarchical', enabled: true },
] as const;

export interface CategoryFilterListProps {
  visibility: Record<EntityKind, boolean>;
  onToggle(kind: EntityKind): void;
  depth: number;
  onDepthChange(depth: number): void;
  layout: 'force' | 'radial' | 'hierarchical';
  onLayoutChange(layout: 'force' | 'radial' | 'hierarchical'): void;
  onReset(): void;
  className?: string;
}

export function CategoryFilterList({ visibility, onToggle, depth, onDepthChange, layout, onLayoutChange, onReset, className }: CategoryFilterListProps) {
  return (
    <fieldset className={cn('m-0 border-0 p-0', className)}>
      <legend className="sr-only">विषय</legend>
      <div className="px-4 py-4">
        <div className="mb-3 flex items-baseline gap-2">
          <h2 className="text-[length:var(--font-size-h3)] font-semibold text-foreground">विषय</h2>
          <span className="text-[length:var(--font-size-xs)] uppercase tracking-[0.04em] text-foreground-muted">(CATEGORIES)</span>
        </div>
        <div className="flex flex-col gap-3">
          {CATEGORY_DATA.map(({ kind, labelHi, labelEn, catVar }) => (
            <div key={kind} className="flex items-center gap-2">
              <div aria-hidden="true" className="h-3.5 w-3.5 shrink-0 rounded-[var(--radius-sm)]" style={{ backgroundColor: catVar }} />
              <span className="flex-1 text-[length:var(--font-size-body)] font-medium text-foreground">{labelHi}</span>
              <span className="text-[length:var(--font-size-sm)] text-foreground-muted">({labelEn})</span>
              <Switch checked={visibility[kind]} onCheckedChange={() => onToggle(kind)} aria-label={`${labelHi} दिखाएं`} />
            </div>
          ))}
        </div>

        <Separator className="my-4" />

        <div className="mb-4">
          <h3 className="mb-2 text-[length:var(--font-size-sm)] font-semibold text-foreground">लेआउट / Layout</h3>
          <div className="flex flex-col gap-1.5">
            {LAYOUT_OPTIONS.map(({ value, labelHi, labelEn, enabled }) => (
              <label key={value} className={cn('flex items-center gap-2 rounded px-1 py-0.5', enabled ? 'cursor-pointer' : 'cursor-not-allowed opacity-40')}>
                <input
                  type="radio"
                  name="graph-layout"
                  value={value}
                  checked={layout === value}
                  onChange={() => onLayoutChange(value)}
                  disabled={!enabled}
                  className="accent-accent"
                />
                <span className="text-[length:var(--font-size-sm)] text-foreground">{labelHi}</span>
                <span className="text-[length:var(--font-size-xs)] text-foreground-muted">/ {labelEn}</span>
              </label>
            ))}
          </div>
        </div>

        <div className="mb-5">
          <h3 className="mb-2 text-[length:var(--font-size-sm)] font-semibold text-foreground">गहराई / Depth</h3>
          <div className="flex items-center gap-3">
            <button type="button" aria-label="गहराई घटाएं" onClick={() => onDepthChange(Math.max(1, depth - 1))} disabled={depth <= 1} className={cn('flex h-7 w-7 items-center justify-center rounded border border-border text-[length:var(--font-size-body)] text-foreground transition-colors hover:bg-surface-muted', 'disabled:cursor-not-allowed disabled:opacity-40')}>−</button>
            <span className="w-4 text-center text-[length:var(--font-size-body)] font-semibold text-foreground">{depth}</span>
            <button type="button" aria-label="गहराई बढ़ाएं" onClick={() => onDepthChange(Math.min(4, depth + 1))} disabled={depth >= 4} className={cn('flex h-7 w-7 items-center justify-center rounded border border-border text-[length:var(--font-size-body)] text-foreground transition-colors hover:bg-surface-muted', 'disabled:cursor-not-allowed disabled:opacity-40')}>+</button>
          </div>
        </div>

        <button type="button" onClick={onReset} className="text-[length:var(--font-size-sm)] font-medium text-accent hover:underline">Reset graph</button>
      </div>
    </fieldset>
  );
}
