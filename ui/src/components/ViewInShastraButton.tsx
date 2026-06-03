'use client';

import { useEffect, useState } from 'react';
import { ExternalLink } from '@/lib/icons';
import { cn } from '@/lib/utils';
import { getExtractMatch } from '@/lib/api/data';
import { buildGathaHref } from '@/lib/gatha-content';
import type { DefinitionReference, ExtractMatch } from '@/lib/types';

export interface MatchEntry {
  natural_key: string;
  shastra_nk: string;
  gatha_nk: string;
  status: ExtractMatch['match']['status'];
  href: string;
  label: string;
}

function buildLabel(match: ExtractMatch): string {
  const parts = match.target.natural_key.split(':');
  const shastra = match.target.shastra_natural_key ?? parts[0] ?? '';
  const gathaIdx = parts.indexOf('गाथा');
  const gatha = gathaIdx !== -1 ? parts[gathaIdx + 1] : '';
  return gatha ? `${shastra} गाथा ${gatha}` : shastra;
}

function shastraNkOf(match: ExtractMatch): string {
  return match.target.shastra_natural_key ?? match.target.natural_key.split(':')[0] ?? '';
}

function gathaNkOf(match: ExtractMatch): string {
  return match.target.gatha_natural_key ?? '';
}

// Returns the entry that corresponds to this ref. We correlate primarily by
// shastra (Devanagari natural_key === ref.shastra_name) and, when the ref has
// a gatha number, further narrow to the entry whose gatha matches.
//
// Entries with status === 'target_missing' are filtered out — we only surface
// links for targets that actually exist in the DB (matched OR unmatched).
export function findMatchForRef(
  ref: DefinitionReference,
  entries: MatchEntry[] | null,
): MatchEntry | undefined {
  if (!entries || !ref.shastra_name) return undefined;
  const candidates = entries.filter(
    (e) => e.status !== 'target_missing' && e.shastra_nk === ref.shastra_name,
  );
  if (candidates.length === 0) return undefined;
  const refGatha = ref.resolved_fields.find((f) => f.field === 'गाथा')?.value;
  if (refGatha) {
    const byGatha = candidates.find((e) => e.gatha_nk.endsWith(`:${refGatha}`) || e.gatha_nk === refGatha);
    if (byGatha) return byGatha;
  }
  return candidates[0];
}

interface UseMatchEntriesResult {
  entries: MatchEntry[] | null;
  loading: boolean;
  error: boolean;
}

// Auto-loads extract-match entries for the given natural keys. Returns null
// while loading or on error so callers can render nothing in those states.
export function useMatchEntries(match_natural_keys: string[] | undefined): UseMatchEntriesResult {
  const [entries, setEntries] = useState<MatchEntry[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);

  const key = match_natural_keys?.join('|') ?? '';
  useEffect(() => {
    if (!match_natural_keys || match_natural_keys.length === 0) return;
    let cancelled = false;
    setLoading(true);
    setError(false);
    (async () => {
      try {
        const matches = await Promise.all(match_natural_keys.map((nk) => getExtractMatch(nk)));
        if (cancelled) return;
        setEntries(
          matches.map((m) => ({
            natural_key: m.natural_key,
            shastra_nk: shastraNkOf(m),
            gatha_nk: gathaNkOf(m),
            status: m.match.status,
            href: buildGathaHref(m),
            label: buildLabel(m),
          })),
        );
      } catch {
        if (!cancelled) setError(true);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  return { entries, loading, error };
}

interface MatchLinkProps {
  entry: MatchEntry;
}

export function MatchLink({ entry }: MatchLinkProps) {
  const matched = entry.status === 'matched';
  return (
    <a
      href={entry.href}
      target="_blank"
      rel="noopener noreferrer"
      className={cn(
        'inline-flex items-center transition-colors',
        matched
          ? 'text-blue-600 hover:text-blue-700'
          : 'text-foreground-subtle hover:text-foreground-muted',
      )}
      aria-label={`शास्त्र में देखें — ${entry.label}${matched ? '' : ' (मिलान नहीं)'}`}
      title={matched ? entry.label : `${entry.label} — मिलान नहीं`}
    >
      <ExternalLink className="size-4 shrink-0" />
    </a>
  );
}
