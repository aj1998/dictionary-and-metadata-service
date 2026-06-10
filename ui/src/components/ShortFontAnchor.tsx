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
      <PopoverContent>
        <div className="text-xs text-foreground-muted mb-1">
          टिप्पणी
        </div>
        <div className="font-serif-hindi text-[length:var(--font-size-body)] whitespace-pre-wrap">
          {entry.meaning}
        </div>
      </PopoverContent>
    </Popover>
  );
}
