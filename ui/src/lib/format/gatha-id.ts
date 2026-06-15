// Helpers for compound/legacy gatha identifier handling in URLs and labels.
//
// Compound shastras (e.g. परमात्मप्रकाश with gatha_identifier "अधिकार,परमात्मप्रकाशगाथा")
// store gatha natural keys as `<shastra>:<seg1>:<val1>:<seg2>:<val2>` and the
// API exposes a compact comma form `<val1>,<val2>` on `/v1/shastras/{nk}/gathas/{raw}`.
// Legacy shastras use `<shastra>:गाथा:<n>` and a bare `<n>` compact.

import type { DefinitionReference } from '@/lib/types';
import { toDevanagariNumerals } from '@/lib/format/devanagari';

// Field-name suffixes/values that are NOT part of the compound identifier and
// should be skipped when building the compact form from a ref's resolved_fields.
// Mirrors `reference.entity_keywords.{page,kalash,pankti}` in jainkosh.yaml.
const NON_ID_FIELD_NAMES = new Set(['पृष्ठ', 'कलश', 'पंक्ति']);

const GATHA_KEYWORD_SUFFIXES = ['गाथा', 'श्लोक', 'सूत्र', 'दोहक', 'वार्तिक'];

export interface ParsedGathaSuffix {
  isCompound: boolean;
  compact: string;
  segments: Array<{ name: string; value: string }>;
}

// Parse the natural-key suffix of a gatha (the part after `<shastra>:`).
// "गाथा:8"               → { isCompound: false, compact: "8", segments: [{name:"गाथा", value:"8"}] }
// "अधिकार:1:गाथा:9"      → { isCompound: true,  compact: "1,9", segments: [...] }
export function parseGathaSuffix(suffix: string): ParsedGathaSuffix {
  const parts = suffix.split(':');
  const segments: Array<{ name: string; value: string }> = [];
  for (let i = 0; i + 1 < parts.length; i += 2) {
    segments.push({ name: parts[i], value: parts[i + 1] });
  }
  const isCompound = segments.length > 1;
  const compact = isCompound
    ? segments.map((s) => s.value).join(',')
    : segments.map((s) => s.value).join('') || suffix;
  return { isCompound, compact, segments };
}

// Convert a gatha natural_key (full form) to its URL-path compact form.
// For legacy NKs the compact is just the gatha number.
export function gathaCompactFromNk(shastraNk: string, gathaNk: string): string {
  if (!gathaNk.startsWith(`${shastraNk}:`)) return gathaNk;
  const suffix = gathaNk.slice(shastraNk.length + 1);
  return parseGathaSuffix(suffix).compact;
}

// Human label for a gatha in a tile/card. For compound gathas, returns
// "अधिकार १, गाथा १" (Devanagari numerals when numeric). For legacy gathas,
// returns the bare gatha number.
export function gathaTileLabel(
  shastraNk: string,
  gathaNk: string,
  gathaNumber: string,
): string {
  if (!gathaNk.startsWith(`${shastraNk}:`)) return gathaNumber || gathaNk;
  const suffix = gathaNk.slice(shastraNk.length + 1);
  const parsed = parseGathaSuffix(suffix);
  if (!parsed.isCompound) return gathaNumber;
  return parsed.segments
    .map((s) => {
      const n = parseInt(s.value, 10);
      const v = Number.isNaN(n) ? s.value : toDevanagariNumerals(n);
      return `${s.name} ${v}`;
    })
    .join(', ');
}

// Extract the leading adhikaar / identifier list from a set of gatha natural keys.
// Returns the de-duplicated list of values for the first non-gatha-keyword segment
// in declaration order — e.g. for परमात्मप्रकाश returns ["1","2",...] (the अधिकार values).
// Returns [] when no compound structure is detected.
export function uniqueLeadingIdValues(
  shastraNk: string,
  gathaNks: string[],
): { fieldName: string; values: string[] } | null {
  const order: string[] = [];
  const seen = new Set<string>();
  let fieldName: string | null = null;
  for (const nk of gathaNks) {
    if (!nk.startsWith(`${shastraNk}:`)) continue;
    const parsed = parseGathaSuffix(nk.slice(shastraNk.length + 1));
    if (!parsed.isCompound) continue;
    const first = parsed.segments[0];
    if (!first) continue;
    if (!fieldName) fieldName = first.name;
    if (!seen.has(first.value)) {
      seen.add(first.value);
      order.push(first.value);
    }
  }
  if (!fieldName || order.length === 0) return null;
  // Numeric sort when possible.
  order.sort((a, b) => {
    const na = parseInt(a, 10);
    const nb = parseInt(b, 10);
    if (Number.isNaN(na) || Number.isNaN(nb)) return a.localeCompare(b);
    return na - nb;
  });
  return { fieldName, values: order };
}

// Build the reader URL for a gatha given a shastra-relative compact form.
export function buildGathaPathHref(shastraNk: string, compact: string): string {
  return `/shastras/${encodeURIComponent(shastraNk)}/gathas/${encodeURIComponent(compact)}`;
}

// Detect whether a `{number}` URL param is a full natural key (`<shastra>:...`).
export function isFullGathaNk(num: string, shastraNk: string): boolean {
  return num.includes(':') && num.startsWith(`${shastraNk}:`);
}

// From a parser-emitted ref's resolved_fields, derive the compact form that
// the compound API expects. Returns null when there's nothing usable.
// Includes the gatha-keyword field plus any preceding non-page/kalash/pankti
// fields (e.g. अधिकार) in their original order.
export function compactFromResolvedFields(
  ref: DefinitionReference,
): { compact: string; gathaValue: string } | null {
  const usable = ref.resolved_fields.filter(
    (f) => f.value !== '' && f.value != null && !NON_ID_FIELD_NAMES.has(f.field),
  );
  if (usable.length === 0) return null;
  const gathaIdx = usable.findIndex((f) =>
    GATHA_KEYWORD_SUFFIXES.some((s) => f.field.endsWith(s)),
  );
  if (gathaIdx < 0) return null;
  const idFields = usable.slice(0, gathaIdx + 1);
  return {
    compact: idFields.map((f) => String(f.value)).join(','),
    gathaValue: String(usable[gathaIdx].value),
  };
}
