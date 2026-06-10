'use client';

import { useState } from 'react';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { Info, ChevronRight, ExternalLink } from '@/lib/icons';
import { Link } from '@/i18n/navigation';

function deriveBreadcrumb(topicNk: string): string[] {
  return topicNk
    .split(':')
    .map((seg) => seg.replace(/-/g, ' ').trim())
    .filter(Boolean);
}

export function TopicPathInfo({
  topicNk,
  dictionaryHref,
}: {
  topicNk: string;
  dictionaryHref?: string;
}) {
  const [open, setOpen] = useState(false);
  const crumbs = deriveBreadcrumb(topicNk);
  if (crumbs.length === 0) return null;
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger
        type="button"
        aria-label="पूरा पथ देखें"
        className="inline-flex size-7 items-center justify-center rounded-full border border-border text-foreground-muted hover:bg-accent-soft hover:text-accent"
      >
        <Info className="size-4" strokeWidth={1.75} />
      </PopoverTrigger>
      <PopoverContent align="start" side="bottom" sideOffset={6} className="max-w-[360px] p-3">
        <div className="font-serif-hindi flex flex-wrap items-center gap-1 text-sm">
          {crumbs.map((c, i) => (
            <span key={i} className="inline-flex items-center gap-1">
              <span className={i === crumbs.length - 1 ? 'font-semibold text-foreground' : 'text-foreground-muted'}>
                {c}
              </span>
              {i < crumbs.length - 1 && (
                <ChevronRight className="size-3 text-foreground-subtle" strokeWidth={1.75} />
              )}
            </span>
          ))}
        </div>
        {dictionaryHref && (
          <Link
            href={dictionaryHref}
            target="_blank"
            rel="noopener noreferrer"
            className="mt-3 inline-flex items-center gap-1.5 text-sm font-medium text-accent hover:underline"
          >
            शब्दकोश में देखें
            <ExternalLink className="size-3.5" strokeWidth={1.75} />
          </Link>
        )}
      </PopoverContent>
    </Popover>
  );
}
