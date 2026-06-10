'use client';

import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import type { BhaavarthShortFontEntry } from '@/lib/types';

interface ShortFontAnchorProps {
  entry: BhaavarthShortFontEntry;
}

export function ShortFontAnchor({ entry }: ShortFontAnchorProps) {
  return (
    <Popover>
      <PopoverTrigger
        aria-haspopup="dialog"
        className="sf-anchor"
      >
        {entry.anchor_text}
      </PopoverTrigger>
      <PopoverContent
        side="top"
        align="center"
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
