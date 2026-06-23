'use client';

import { useEffect, useState } from 'react';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import type { BhaavarthShortFontEntry } from '@/lib/types';

interface ShortFontAnchorProps {
  entry: BhaavarthShortFontEntry;
}

export function ShortFontAnchor({ entry }: ShortFontAnchorProps) {
  const [open, setOpen] = useState(false);

  // Base UI keeps the popup glued to the viewport rather than the anchor inside
  // nested scroll containers, so the tippani appears to drift on scroll. Dismiss
  // it on any scroll/resize instead of letting it float over unrelated text.
  useEffect(() => {
    if (!open) return;
    const close = () => setOpen(false);
    window.addEventListener('scroll', close, true);
    window.addEventListener('resize', close);
    return () => {
      window.removeEventListener('scroll', close, true);
      window.removeEventListener('resize', close);
    };
  }, [open]);

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger
        aria-haspopup="dialog"
        className="sf-anchor"
      >
        {entry.anchor_text}
      </PopoverTrigger>
      <PopoverContent
        side="top"
        align="center"
        positionMethod="fixed"
        collisionAvoidance={{ side: 'flip', align: 'shift' }}
        className="w-[min(22rem,calc(100vw-2rem))]"
      >
        <div className="text-xs text-foreground-muted mb-1">
          टिप्पणी
        </div>
        <div
          className="text-xs leading-relaxed whitespace-pre-wrap"
          style={{ fontFamily: '"Noto Sans Devanagari", "Kohinoor Devanagari", "Nirmala UI", sans-serif' }}
        >
          {entry.meaning}
        </div>
      </PopoverContent>
    </Popover>
  );
}
