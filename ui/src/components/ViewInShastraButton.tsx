'use client';

import { useState } from 'react';
import { ExternalLink } from '@/lib/icons';
import { getExtractMatch } from '@/lib/api/data';
import { buildGathaHref } from '@/lib/gatha-content';
import type { ExtractMatch } from '@/lib/types';

interface ViewInShastraButtonProps {
  match_natural_keys: string[];
}

interface MatchEntry {
  natural_key: string;
  href: string;
  label: string;
}

function buildLabel(match: ExtractMatch): string {
  const parts = match.target.natural_key.split(':');
  const shastra = parts[0] ?? '';
  const gathaIdx = parts.indexOf('गाथा');
  const gatha = gathaIdx !== -1 ? parts[gathaIdx + 1] : '';
  return gatha ? `${shastra} गाथा ${gatha}` : shastra;
}

export function ViewInShastraButton({ match_natural_keys }: ViewInShastraButtonProps) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);
  const [entries, setEntries] = useState<MatchEntry[] | null>(null);

  const handleClick = async () => {
    if (loading) return;
    setLoading(true);
    setError(false);
    try {
      const matches = await Promise.all(match_natural_keys.map((nk) => getExtractMatch(nk)));
      const valid = matches.filter((m) => m.match.status === 'matched');
      if (valid.length === 0) {
        showError();
        return;
      }
      if (valid.length === 1) {
        window.open(buildGathaHref(valid[0]), '_blank', 'noopener,noreferrer');
        return;
      }
      setEntries(valid.map((m) => ({ natural_key: m.natural_key, href: buildGathaHref(m), label: buildLabel(m) })));
    } catch {
      showError();
    } finally {
      setLoading(false);
    }
  };

  const showError = () => {
    setError(true);
    setTimeout(() => setError(false), 2000);
  };

  if (entries) {
    return (
      <div className="mt-2 flex flex-wrap gap-1.5">
        {entries.map((e) => (
          <a
            key={e.natural_key}
            href={e.href}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 rounded-[var(--radius-sm)] bg-accent px-2.5 py-0.5 font-serif-hindi text-xs font-semibold text-white transition-colors hover:bg-accent-hover"
          >
            <ExternalLink className="size-3 shrink-0" />
            {e.label}
          </a>
        ))}
      </div>
    );
  }

  return (
    <div className="mt-2">
      {error ? (
        <span className="font-serif-hindi text-xs text-rose-500">शास्त्र में नहीं मिला</span>
      ) : (
        <button
          type="button"
          disabled={loading}
          onClick={handleClick}
          className="inline-flex items-center gap-1 rounded-[var(--radius-sm)] bg-accent px-2.5 py-0.5 font-serif-hindi text-xs font-semibold text-white transition-colors hover:bg-accent-hover disabled:opacity-60"
        >
          <ExternalLink className="size-3 shrink-0" />
          {loading ? '…' : 'शास्त्र में देखें'}
        </button>
      )}
    </div>
  );
}
