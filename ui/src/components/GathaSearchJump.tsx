'use client';

import { useRouter } from '@/i18n/navigation';
import { useState } from 'react';

interface Props {
  shastraNk: string;
  totalGathas: number;
}

export function GathaSearchJump({ shastraNk, totalGathas }: Props) {
  const router = useRouter();
  const [value, setValue] = useState('');

  function handleJump() {
    const num = parseInt(value.trim(), 10);
    if (!num || num < 1) return;
    const gathaNk = `${shastraNk}:गाथा:${num}`;
    router.push(`/shastras/${encodeURIComponent(shastraNk)}/gathas/${encodeURIComponent(gathaNk)}`);
  }

  const hasValue = value.trim().length > 0;

  return (
    <div className="flex items-center gap-2 rounded-[var(--radius-md)] border border-border-strong bg-surface px-3 py-2 shadow-node">
      <span className="font-serif-hindi text-sm font-semibold text-foreground whitespace-nowrap">गाथा पर जाएँ</span>
      <input
        type="number"
        min={1}
        max={totalGathas || undefined}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => e.key === 'Enter' && handleJump()}
        placeholder="नं."
        className="w-20 rounded-[var(--radius-sm)] border border-border-strong bg-surface px-2 py-1.5 text-sm text-center text-foreground placeholder:text-foreground-muted focus:border-accent focus:outline-none"
      />
      <button
        onClick={handleJump}
        disabled={!hasValue}
        className="rounded-[var(--radius-sm)] bg-accent px-3 py-1.5 text-sm font-semibold text-white transition-opacity hover:bg-accent/90 disabled:opacity-50"
      >
        खोलें →
      </button>
    </div>
  );
}
