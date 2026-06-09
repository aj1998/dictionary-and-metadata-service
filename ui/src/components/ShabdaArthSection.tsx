'use client';

import { useState } from 'react';
import { cn } from '@/lib/utils';

export interface ShabdaArthEntry {
  word: string;
  meaning: string;
}

interface ShabdaArthSectionProps {
  entries: ShabdaArthEntry[];
  anvayarth: string;
}

export function ShabdaArthSection({ entries, anvayarth }: ShabdaArthSectionProps) {
  const [activeIndex, setActiveIndex] = useState<number | null>(null);

  const activeMeaning = activeIndex !== null ? entries[activeIndex]?.meaning ?? null : null;

  function handleClick(index: number) {
    setActiveIndex((prev) => (prev === index ? null : index));
  }

  function renderAnvayarth() {
    if (!activeMeaning) return anvayarth;
    const idx = anvayarth.indexOf(activeMeaning);
    if (idx === -1) return anvayarth;
    return (
      <>
        {anvayarth.slice(0, idx)}
        <mark className="rounded bg-[var(--accent-soft)] text-[var(--accent)]">
          {activeMeaning}
        </mark>
        {anvayarth.slice(idx + activeMeaning.length)}
      </>
    );
  }

  return (
    <>
      <div className="flex flex-wrap gap-2 leading-8">
        {entries.map((entry, index) => (
          <button
            key={`${entry.word}-${index}`}
            type="button"
            onClick={() => handleClick(index)}
            className={cn(
              'cursor-pointer rounded-[var(--radius-sm)] font-serif-hindi underline decoration-accent decoration-2 underline-offset-2 transition-colors',
              activeIndex === index
                ? 'bg-accent-soft text-accent'
                : 'hover:bg-accent-soft'
            )}
          >
            {entry.word}
          </button>
        ))}
      </div>
      <div className="mt-4 border-t border-border pt-4">
        <p className="mb-1 text-xs font-medium text-foreground-muted">अन्वयार्थ</p>
        <p className="font-serif-hindi text-sm leading-8 text-foreground">
          {renderAnvayarth()}
        </p>
      </div>
    </>
  );
}
