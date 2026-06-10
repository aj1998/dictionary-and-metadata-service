'use client';

import { useState } from 'react';
import { cn } from '@/lib/utils';
import { teekaMarkdownToHtml } from '@/lib/format/teeka-markdown';

function renderInlineHtml(raw: string): string {
  return teekaMarkdownToHtml(raw).replace(/^<p[^>]*>/, '').replace(/<\/p>$/, '');
}

export interface ShabdaArthEntry {
  word: string;
  meaning: string;
  position?: number;
  startOffset?: number | null;
  endOffset?: number | null;
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
    if (!activeMeaning || activeIndex === null) {
      return <span dangerouslySetInnerHTML={{ __html: renderInlineHtml(anvayarth) }} />;
    }
    const active = entries[activeIndex];
    if (!active) {
      return <span dangerouslySetInnerHTML={{ __html: renderInlineHtml(anvayarth) }} />;
    }
    let start = -1;
    let end = -1;
    if (
      typeof active.startOffset === 'number' &&
      typeof active.endOffset === 'number' &&
      active.startOffset >= 0 &&
      active.endOffset <= anvayarth.length &&
      active.endOffset > active.startOffset
    ) {
      start = active.startOffset;
      end = active.endOffset;
    } else {
      const sameMeaning = entries
        .map((e, i) => ({ e, i }))
        .filter(({ e }) => e.meaning === activeMeaning);
      sameMeaning.sort((a, b) => (a.e.position ?? a.i) - (b.e.position ?? b.i));
      const rank = Math.max(1, sameMeaning.findIndex(({ i }) => i === activeIndex) + 1);
      let from = 0;
      for (let k = 0; k < rank; k++) {
        start = anvayarth.indexOf(activeMeaning, from);
        if (start === -1) break;
        from = start + activeMeaning.length;
      }
      if (start !== -1) end = start + activeMeaning.length;
    }
    if (start === -1) {
      return <span dangerouslySetInnerHTML={{ __html: renderInlineHtml(anvayarth) }} />;
    }
    const beforeHtml = renderInlineHtml(anvayarth.slice(0, start));
    const middleHtml = renderInlineHtml(anvayarth.slice(start, end));
    const afterHtml = renderInlineHtml(anvayarth.slice(end));
    const combined =
      beforeHtml +
      '<mark class="rounded bg-[var(--accent-soft)] text-[var(--accent)]">' +
      middleHtml +
      '</mark>' +
      afterHtml;
    return <span dangerouslySetInnerHTML={{ __html: combined }} />;
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
        <div className="font-serif-hindi text-sm leading-8 text-foreground teeka-content">
          {renderAnvayarth()}
        </div>
      </div>
    </>
  );
}
