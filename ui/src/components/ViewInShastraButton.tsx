'use client';

import { useEffect, useState } from 'react';
import { ExternalLink, BookOpen } from '@/lib/icons';
import { cn } from '@/lib/utils';
import { getExtractMatch } from '@/lib/api/data';
import { buildGathaHref, buildShastraGathaHref, getRefGathaEntity } from '@/lib/gatha-content';
import { buildGathaPathHref, compactFromResolvedFields } from '@/lib/format/gatha-id';
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

// Describes whether/how to surface a link for a given (ref, matchEntry) pair.
// `matched`     → blue link using the resolved match entry.
// `unmatched`   → grey link using the resolved match entry (status === 'unmatched').
// `fallback`    → grey link synthesised from the ref itself when no match entry exists
//                  but the ref names a gatha-entity in a known shastra.
// `none`        → render nothing.
export type RefLinkPlan =
  | { kind: 'matched' | 'unmatched'; href: string; label: string }
  | { kind: 'fallback'; href: string; label: string }
  | { kind: 'none' };

// Decides which link (if any) to render for a ref given the matcher's response.
//
// `ingestedShastras` is the set of shastra natural keys that have actually
// been ingested into the DB (i.e. `/shastras/<nk>` resolves to a real page).
// The fallback grey link is only emitted when the ref's `shastra_name` is in
// this set — otherwise the link would land on a 404. Pass `null` while the
// registry is still loading (or unavailable); the fallback is then suppressed.
export function planRefLink(
  ref: DefinitionReference,
  matchEntry: MatchEntry | undefined,
  ingestedShastras: Set<string> | null = null,
): RefLinkPlan {
  if (matchEntry) {
    return {
      kind: matchEntry.status === 'matched' ? 'matched' : 'unmatched',
      href: matchEntry.href,
      label: matchEntry.label,
    };
  }
  if (!ref.shastra_name) return { kind: 'none' };
  if (!ingestedShastras) return { kind: 'none' };
  // Normalize on lookup so a parsed `ref.shastra_name` with combining-mark
  // variance still matches an NFC-normalized registry entry.
  const shastraNkNFC = ref.shastra_name.normalize('NFC');
  if (!ingestedShastras.has(shastraNkNFC)) return { kind: 'none' };
  // Compound shastras (e.g. परमात्मप्रकाश) need multiple identifier values
  // joined by comma. Detect this when the ref resolves more than one
  // identifier field; fall back to the single-field path otherwise.
  const compound = compactFromResolvedFields(ref);
  if (compound && compound.compact.includes(',')) {
    return {
      kind: 'fallback',
      href: buildGathaPathHref(shastraNkNFC, compound.compact),
      label: `${shastraNkNFC} ${compound.compact}`,
    };
  }
  const entity = getRefGathaEntity(ref);
  if (!entity) return { kind: 'none' };
  return {
    kind: 'fallback',
    href: buildShastraGathaHref(shastraNkNFC, entity.field, entity.value),
    label: `${shastraNkNFC} ${entity.field} ${entity.value}`,
  };
}

interface RefMatchLinkProps {
  ref: DefinitionReference;
  matchEntry: MatchEntry | undefined;
  // When true, the matcher response is still loading for this block; the
  // grey fallback link is suppressed so it doesn't briefly appear before the
  // real (blue/grey) link replaces it.
  loading?: boolean;
  // Set of shastra natural keys that are actually ingested into the DB. The
  // fallback grey link is only rendered when `ref.shastra_name` is in this
  // set — see `planRefLink`.
  ingestedShastras?: Set<string> | null;
}

// Unified link renderer for a ref. Picks blue / grey / grey-fallback / nothing
// based on planRefLink.
export function RefMatchLink({ ref, matchEntry, loading = false, ingestedShastras = null }: RefMatchLinkProps) {
  const plan = planRefLink(ref, matchEntry, ingestedShastras);
  if (plan.kind === 'fallback' && loading) return null;
  if (plan.kind === 'none') return null;
  const matched = plan.kind === 'matched';
  const suffix = plan.kind === 'matched' ? '' : plan.kind === 'fallback' ? ' (शास्त्र में देखें)' : ' (मिलान नहीं)';
  return (
    <a
      href={plan.href}
      target="_blank"
      rel="noopener noreferrer"
      className={cn(
        'inline-flex items-center transition-colors',
        matched
          ? 'text-[var(--cat-page)] hover:text-amber-900'
          : 'text-foreground-subtle hover:text-foreground-muted',
      )}
      aria-label={`शास्त्र में देखें — ${plan.label}${suffix}`}
      title={`${plan.label}${suffix}`}
    >
      <BookOpen className="size-4 shrink-0" />
    </a>
  );
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
          ? 'text-[var(--cat-page)] hover:text-amber-900'
          : 'text-foreground-subtle hover:text-foreground-muted',
      )}
      aria-label={`शास्त्र में देखें — ${entry.label}${matched ? '' : ' (मिलान नहीं)'}`}
      title={matched ? entry.label : `${entry.label} — मिलान नहीं`}
    >
      <BookOpen className="size-4 shrink-0" />
    </a>
  );
}
