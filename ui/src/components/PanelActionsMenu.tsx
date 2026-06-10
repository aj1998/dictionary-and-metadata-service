'use client';

import { useState } from 'react';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { MoreHorizontal, Tag, Sparkles, Network } from '@/lib/icons';
import { useReaderActions } from './ReaderActionsContext';
import { Link } from '@/i18n/navigation';

interface PanelActionsMenuProps {
  sourceNk: string;
  sourceLabel: string;
}

export function PanelActionsMenu({ sourceNk, sourceLabel }: PanelActionsMenuProps) {
  const [open, setOpen] = useState(false);
  const { open: openRight } = useReaderActions();

  const handle = (kind: 'topics' | 'keywords') => {
    openRight({ kind, sourceNk, sourceLabel });
    setOpen(false);
  };

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger
        aria-label="क्रियाएँ"
        title="और क्रियाएँ"
        className="group inline-flex h-8 w-8 items-center justify-center rounded-[var(--radius-sm)] shadow-sm transition-all hover:scale-105 hover:shadow-md"
        style={{
          backgroundColor: 'color-mix(in srgb, var(--panel-accent, var(--accent)) 70%, white)',
          color: '#fff',
        }}
      >
        <MoreHorizontal className="h-4 w-4 transition-transform group-hover:rotate-90" strokeWidth={2.5} />
      </PopoverTrigger>
      <PopoverContent align="end" side="bottom" sideOffset={6} className="w-56 p-1">
        <button
          onClick={() => handle('topics')}
          className="flex w-full items-center gap-2 rounded-[var(--radius-sm)] px-3 py-2 text-sm text-left hover:bg-surface-muted"
        >
          <Tag className="h-4 w-4 text-[var(--cat-topic)]" strokeWidth={1.5} />
          <span className="font-serif-hindi">उल्लिखित विषय देखें</span>
        </button>
        <button
          onClick={() => handle('keywords')}
          className="flex w-full items-center gap-2 rounded-[var(--radius-sm)] px-3 py-2 text-sm text-left hover:bg-surface-muted"
        >
          <Sparkles className="h-4 w-4 text-[var(--cat-keyword)]" strokeWidth={1.5} />
          <span className="font-serif-hindi">परिभाषित शब्द देखें</span>
        </button>
        <Link
          href={`/graph?node=${encodeURIComponent(sourceNk)}`}
          target="_blank"
          onClick={() => setOpen(false)}
          className="flex w-full items-center gap-2 rounded-[var(--radius-sm)] px-3 py-2 text-sm text-left hover:bg-surface-muted"
        >
          <Network className="h-4 w-4 text-[var(--cat-gatha)]" strokeWidth={1.5} />
          <span className="font-serif-hindi">ग्राफ में खोलें</span>
        </Link>
      </PopoverContent>
    </Popover>
  );
}
