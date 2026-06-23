'use client';

import { useState, useCallback, useRef, useEffect, useLayoutEffect } from 'react';
import { cn } from '@/lib/utils';
import type { BhaavarthShortFontEntry } from '@/lib/types';

interface ShortFontHtmlProps {
  html: string;
  entries: BhaavarthShortFontEntry[];
  className?: string;
}

interface PopoverState {
  entry: BhaavarthShortFontEntry;
  btnRect: { top: number; bottom: number; left: number };
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
    // The popover is fixed-positioned from a one-time getBoundingClientRect, so it
    // would drift away from its anchor on scroll. Dismiss it instead of letting it
    // float over unrelated text. Capture phase catches nested scroll containers.
    const close = () => setPopover(null);
    document.addEventListener('mousedown', handler);
    window.addEventListener('scroll', close, true);
    window.addEventListener('resize', close);
    return () => {
      document.removeEventListener('mousedown', handler);
      window.removeEventListener('scroll', close, true);
      window.removeEventListener('resize', close);
    };
  }, [popover]);

  // After mount, measure actual popover height and flip/clamp to viewport.
  useLayoutEffect(() => {
    if (!popover || !popoverRef.current) return;
    const popEl = popoverRef.current;
    const { btnRect } = popover;
    const margin = 8;
    const actualHeight = popEl.offsetHeight;
    const actualWidth = popEl.offsetWidth;

    const spaceBelow = window.innerHeight - btnRect.bottom - margin;
    const spaceAbove = btnRect.top - margin;
    const flipUp = actualHeight > spaceBelow && spaceAbove > spaceBelow;

    const desiredTop = flipUp
      ? btnRect.top - actualHeight - 4
      : btnRect.bottom + 4;
    const clampedTop = Math.max(
      margin,
      Math.min(desiredTop, window.innerHeight - actualHeight - margin),
    );

    const desiredLeft = btnRect.left;
    const clampedLeft = Math.max(
      margin,
      Math.min(desiredLeft, window.innerWidth - actualWidth - margin),
    );

    if (clampedTop !== popover.top || clampedLeft !== popover.left) {
      setPopover((p) => (p ? { ...p, top: clampedTop, left: clampedLeft } : p));
    }
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

    const btnRect = btn.getBoundingClientRect();

    // Initial guess; the useLayoutEffect will measure and reposition.
    setPopover({
      entry,
      btnRect: { top: btnRect.top, bottom: btnRect.bottom, left: btnRect.left },
      top: btnRect.bottom + 4,
      left: btnRect.left,
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
          className="fixed z-50 w-[min(22rem,calc(100vw-2rem))] max-h-[70vh] overflow-y-auto rounded-[var(--radius-md)] border border-border bg-surface p-4 shadow-node"
          style={{ top: popover.top, left: popover.left }}
        >
          <p className="text-xs text-foreground-muted mb-1">
            टिप्पणी
          </p>
          <p
            className="text-xs leading-relaxed whitespace-pre-wrap"
            style={{ fontFamily: '"Noto Sans Devanagari", "Kohinoor Devanagari", "Nirmala UI", sans-serif' }}
          >
            {popover.entry.meaning}
          </p>
        </div>
      )}
    </div>
  );
}
