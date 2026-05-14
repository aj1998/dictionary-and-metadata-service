'use client';

import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { Link } from '@/i18n/navigation';

export interface TaggedTermPopoverProps {
  termHi: string;
  meaningHi?: string;
  meaningEn?: string;
  topicNk?: string;
}

export function TaggedTermPopover({ termHi, meaningHi, meaningEn, topicNk }: TaggedTermPopoverProps) {
  return (
    <Popover>
      <PopoverTrigger
        aria-haspopup="dialog"
        className="cursor-pointer rounded-[var(--radius-sm)] underline decoration-accent decoration-2 underline-offset-2 transition-colors hover:bg-accent-soft"
      >
        {termHi}
      </PopoverTrigger>
      <PopoverContent
        role="dialog"
        aria-modal="false"
        className="w-80 rounded-[var(--radius-md)] border border-border bg-surface p-4 text-foreground"
      >
        <div className="space-y-2">
          <h4 className="font-serif-hindi text-[length:var(--font-size-h3)] font-semibold">{termHi}</h4>
          {meaningHi && <p className="font-serif-hindi text-sm">{meaningHi}</p>}
          {meaningEn && <p className="font-sans text-xs text-foreground-muted">{meaningEn}</p>}
          {topicNk && (
            <Link href={`/topics/${topicNk}`} className="inline-block text-sm font-medium text-accent">
              विषय खोलें →
            </Link>
          )}
        </div>
      </PopoverContent>
    </Popover>
  );
}
