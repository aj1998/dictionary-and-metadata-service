'use client';

import { useState, useCallback, useRef, useEffect } from 'react';
import { cn } from '@/lib/utils';
import type { BhaavarthShortFontEntry } from '@/lib/types';

interface ShortFontHtmlProps {
  html: string;
  entries: BhaavarthShortFontEntry[];
  className?: string;
}

interface PopoverState {
  entry: BhaavarthShortFontEntry;
  top: number;
  left: number;
}

/**
 * Renders bhaavarth HTML that contains `<button data-sf-idx="N">` anchors injected
 * by the shortfont pipeline. On click it shows an inline styled popover with the meaning.
 */
export function ShortFontHtml({ html, entries, className }: ShortFontHtmlProps) {
  const [popover, setPopover] = useState<PopoverState | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const popoverRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!popover) return;
    const handler = (e: MouseEvent) => {
      const target = e.target as HTMLElement;
      if (popoverRef.current?.contains(target)) return;
      if (target.closest('[data-sf-idx]')) return;
      setPopover(null);
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [popover]);

  const handleClick = useCallback((e: React.MouseEvent<HTMLDivElement>) => {
    const btn = (e.target as HTMLElement).closest('[data-sf-idx]') as HTMLElement | null;
    if (!btn) return;
    e.stopPropagation();

    const idx = parseInt(btn.getAttribute('data-sf-idx') ?? '', 10);
    const entry = entries[idx];
    if (!entry) return;

    if (popover?.entry === entry) {
      setPopover(null);
      return;
    }

    const containerRect = containerRef.current?.getBoundingClientRect();
    const btnRect = btn.getBoundingClientRect();
    if (!containerRect) return;

    setPopover({
      entry,
      top: btnRect.bottom - containerRect.top + 4,
      left: Math.max(0, btnRect.left - containerRect.left),
    });
  }, [entries, popover]);

  return (
    <div ref={containerRef} className={cn('relative', className)} onClick={handleClick}>
      <div dangerouslySetInnerHTML={{ __html: html }} />
      {popover && (
        <div
          ref={popoverRef}
          role="dialog"
          aria-modal="false"
          className="absolute z-50 max-w-sm rounded-[var(--radius-md)] border border-border bg-surface p-4 shadow-node"
          style={{ top: popover.top, left: popover.left }}
        >
          <p className="text-xs text-foreground-muted mb-1">
            टिप्पणी
          </p>
          <p className="font-serif-hindi text-[length:var(--font-size-body)] whitespace-pre-wrap">
            {popover.entry.meaning}
          </p>
        </div>
      )}
    </div>
  );
}
