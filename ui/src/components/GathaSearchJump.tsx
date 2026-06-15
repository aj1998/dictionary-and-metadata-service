'use client';

import { useRouter } from '@/i18n/navigation';
import { useState } from 'react';
import { useLocale, useTranslations } from 'next-intl';

interface Props {
  shastraNk: string;
  totalGathas: number;
  // For compound shastras (e.g. परमात्मप्रकाश), the leading identifier field
  // name (e.g. "अधिकार") and the de-duplicated list of values to populate the
  // dropdown. Pass null/empty for legacy single-id shastras.
  adhikaarField?: string | null;
  adhikaarValues?: string[];
}

export function GathaSearchJump({ shastraNk, totalGathas, adhikaarField, adhikaarValues = [] }: Props) {
  const router = useRouter();
  const t = useTranslations('shastras');
  const locale = useLocale();
  const isHi = locale === 'hi';
  const isCompound = !!adhikaarField && adhikaarValues.length > 0;

  const [adhikaar, setAdhikaar] = useState<string>(isCompound ? adhikaarValues[0] : '');
  const [gathaNum, setGathaNum] = useState('');

  function handleJump() {
    const raw = gathaNum.trim();
    if (!raw) return;
    if (isCompound) {
      // Server-side fuzzy matcher resolves zero-padding mismatches (e.g. "1,9"
      // → stored "अधिकार:1:गाथा:009"), so we pass values through as typed.
      const compact = `${adhikaar},${raw}`;
      router.push(`/shastras/${encodeURIComponent(shastraNk)}/gathas/${encodeURIComponent(compact)}`);
      return;
    }
    const compact = raw.replace(/\s+/g, '');
    if (!/^[\d,]+$/.test(compact)) return;
    router.push(`/shastras/${encodeURIComponent(shastraNk)}/gathas/${encodeURIComponent(compact)}`);
  }

  const hasValue = gathaNum.trim().length > 0;

  return (
    <div className="flex flex-wrap items-center gap-2 rounded-[var(--radius-md)] border border-border-strong bg-surface px-3 py-2 shadow-node">
      <span className={`${isHi ? 'font-serif-hindi' : 'font-sans'} text-sm font-semibold text-foreground whitespace-nowrap`}>{isHi ? 'गाथा पर जाएँ' : 'Go to gatha'}</span>
      {isCompound && (
        <>
          <label className={`${isHi ? 'font-serif-hindi' : 'font-sans'} text-xs text-foreground-muted whitespace-nowrap`}>{adhikaarField}</label>
          <select
            value={adhikaar}
            onChange={(e) => setAdhikaar(e.target.value)}
            className="rounded-[var(--radius-sm)] border border-border-strong bg-surface px-2 py-1.5 text-sm text-foreground focus:border-accent focus:outline-none"
          >
            {adhikaarValues.map((v) => (
              <option key={v} value={v}>{v}</option>
            ))}
          </select>
          <span className={`${isHi ? 'font-serif-hindi' : 'font-sans'} text-xs text-foreground-muted whitespace-nowrap`}>{isHi ? 'गाथा' : 'gatha'}</span>
        </>
      )}
      <input
        type="text"
        inputMode="numeric"
        value={gathaNum}
        onChange={(e) => setGathaNum(e.target.value)}
        onKeyDown={(e) => e.key === 'Enter' && handleJump()}
        placeholder={isCompound ? (isHi ? 'नं.' : 'No.') : (isHi ? 'नं. (या 1,9)' : 'No. (or 1,9)')}
        className="w-24 rounded-[var(--radius-sm)] border border-border-strong bg-surface px-2 py-1.5 text-sm text-center text-foreground placeholder:text-foreground-muted focus:border-accent focus:outline-none"
      />
      <button
        onClick={handleJump}
        disabled={!hasValue}
        className="rounded-[var(--radius-sm)] bg-accent px-3 py-1.5 text-sm font-semibold text-white transition-opacity hover:bg-accent/90 disabled:opacity-50"
      >
        {t('open')}
      </button>
      {!isCompound && totalGathas > 0 && null}
    </div>
  );
}
