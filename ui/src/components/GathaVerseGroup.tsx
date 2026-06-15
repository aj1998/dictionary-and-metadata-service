'use client';

import { createContext, useContext, useEffect, useMemo, useState } from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import { GathaPanel } from '@/components/GathaPanel';
import { Link } from '@/i18n/navigation';
import { toDevanagariNumerals } from '@/lib/format/devanagari';
import type { HighlightRange } from '@/lib/highlight';

export interface GathaVerseEntry {
  number: string;
  prakrit?: { text: string; naturalKey?: string; highlight?: HighlightRange };
  sanskrit?: { text: string; naturalKey?: string; highlight?: HighlightRange };
  hindiHarigeet?: { text: string };
}

type Ctx = {
  currentNumber: string;
  setCurrentNumber: (n: string) => void;
};

const GathaVerseStateContext = createContext<Ctx | null>(null);

export function GathaVerseStateProvider({
  initialNumber,
  children,
}: {
  initialNumber: string;
  children: React.ReactNode;
}) {
  const [currentNumber, setCurrentNumber] = useState(initialNumber);
  useEffect(() => {
    setCurrentNumber(initialNumber);
  }, [initialNumber]);
  const value = useMemo(() => ({ currentNumber, setCurrentNumber }), [currentNumber]);
  return (
    <GathaVerseStateContext.Provider value={value}>{children}</GathaVerseStateContext.Provider>
  );
}

function useGathaVerseState(): Ctx {
  const ctx = useContext(GathaVerseStateContext);
  if (!ctx) throw new Error('GathaVerseStateProvider missing');
  return ctx;
}

export interface GathaVerseGroupProps {
  entries: GathaVerseEntry[];
}

export function GathaVerseGroup({ entries }: GathaVerseGroupProps) {
  const { currentNumber, setCurrentNumber } = useGathaVerseState();
  const idx = Math.max(
    0,
    entries.findIndex((e) => e.number === currentNumber),
  );
  const total = entries.length;
  const isCombined = total > 1;
  const current = entries[idx] ?? entries[0];
  if (!current) return null;

  const hasPrev = idx > 0;
  const hasNext = idx < total - 1;
  const goPrev = () => hasPrev && setCurrentNumber(entries[idx - 1].number);
  const goNext = () => hasNext && setCurrentNumber(entries[idx + 1].number);

  return (
    <div className="space-y-4">
      {isCombined && (
        <div className="flex items-center justify-end gap-2">
          {hasPrev && (
            <button
              type="button"
              onClick={goPrev}
              aria-label="पिछली गाथा"
              className="flex h-8 w-8 items-center justify-center rounded-full border border-border bg-surface text-foreground-muted hover:border-accent hover:text-accent"
            >
              <ChevronLeft className="h-4 w-4" strokeWidth={1.5} />
            </button>
          )}
          <span className="font-serif-hindi text-xs text-foreground-muted">
            गाथा {toDevanagariNumerals(parseInt(current.number, 10))} ({toDevanagariNumerals(idx + 1)}/{toDevanagariNumerals(total)})
          </span>
          {hasNext && (
            <button
              type="button"
              onClick={goNext}
              aria-label="अगली गाथा"
              className="flex h-8 w-8 items-center justify-center rounded-full border border-border bg-surface text-foreground-muted hover:border-accent hover:text-accent"
            >
              <ChevronRight className="h-4 w-4" strokeWidth={1.5} />
            </button>
          )}
        </div>
      )}

      {current.prakrit ? (
        <GathaPanel
          lang="prakrit"
          text={current.prakrit.text || '—'}
          naturalKey={current.prakrit.naturalKey}
          highlight={current.prakrit.highlight}
        />
      ) : (
        <GathaPanel lang="prakrit" text="—" />
      )}

      {current.sanskrit && (
        <GathaPanel
          lang="sanskrit"
          text={current.sanskrit.text}
          naturalKey={current.sanskrit.naturalKey}
          highlight={current.sanskrit.highlight}
        />
      )}

      {current.hindiHarigeet?.text ? (
        <GathaPanel lang="hindi-harigeet" text={current.hindiHarigeet.text} />
      ) : null}
    </div>
  );
}

type AdjacentLinks = {
  prev: string | null;
  next: string | null;
  prevLabel: string | null;
  nextLabel: string | null;
};

export function GathaPageBottomNav({
  shastraNk,
  shastraDisplayNk,
  gathaLabel,
  adjacentLinks,
}: {
  shastraNk: string;
  shastraDisplayNk: string;
  gathaLabel: string;
  adjacentLinks?: AdjacentLinks;
}) {
  const { currentNumber } = useGathaVerseState();

  // Compound shastras: use server-fetched adjacent links instead of arithmetic.
  if (adjacentLinks) {
    const { prev, next, prevLabel, nextLabel } = adjacentLinks;
    return (
      <div className="flex items-center justify-between gap-3 pt-1">
        {prev ? (
          <Link
            href={`/shastras/${shastraDisplayNk}/gathas/${encodeURIComponent(prev)}`}
            className="flex items-center gap-1 rounded-[var(--radius-md)] border border-border bg-surface px-4 py-2 text-sm hover:border-accent hover:text-accent"
          >
            ← {gathaLabel} {prevLabel ?? prev}
          </Link>
        ) : (
          <span />
        )}
        {next ? (
          <Link
            href={`/shastras/${shastraDisplayNk}/gathas/${encodeURIComponent(next)}`}
            className="flex items-center gap-1 rounded-[var(--radius-md)] border border-border bg-surface px-4 py-2 text-sm hover:border-accent hover:text-accent"
          >
            {gathaLabel} {nextLabel ?? next} →
          </Link>
        ) : (
          <span />
        )}
      </div>
    );
  }

  // Legacy shastras: arithmetic prev/next.
  const num = parseInt(currentNumber, 10);
  if (isNaN(num)) return null;
  const prevNk = num > 1 ? `${shastraNk}:गाथा:${num - 1}` : null;
  const nextNk = `${shastraNk}:गाथा:${num + 1}`;
  return (
    <div className="flex items-center justify-between gap-3 pt-1">
      {prevNk ? (
        <Link
          href={`/shastras/${shastraDisplayNk}/gathas/${encodeURIComponent(prevNk)}`}
          className="flex items-center gap-1 rounded-[var(--radius-md)] border border-border bg-surface px-4 py-2 text-sm hover:border-accent hover:text-accent"
        >
          ← {gathaLabel} {toDevanagariNumerals(num - 1)}
        </Link>
      ) : (
        <span />
      )}
      <Link
        href={`/shastras/${shastraDisplayNk}/gathas/${encodeURIComponent(nextNk)}`}
        className="flex items-center gap-1 rounded-[var(--radius-md)] border border-border bg-surface px-4 py-2 text-sm hover:border-accent hover:text-accent"
      >
        {gathaLabel} {toDevanagariNumerals(num + 1)} →
      </Link>
    </div>
  );
}
