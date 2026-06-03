import type { ExtractMatch } from '@/lib/types';

export type TeekaPart = { type: 'text' | 'term'; value: string };

export function extractBracketTerms(text: string): string[] {
  const matches = text.match(/\[([^\]]+)\]/g) ?? [];
  const unique = new Set<string>();
  for (const match of matches) {
    const term = match.slice(1, -1).trim();
    if (term) unique.add(term);
  }
  return [...unique];
}

export function splitTeekaByBracketTerms(text: string): TeekaPart[] {
  const parts: TeekaPart[] = [];
  const pattern = /\[([^\]]+)\]/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = pattern.exec(text)) !== null) {
    const start = match.index;
    const end = pattern.lastIndex;

    if (start > lastIndex) {
      parts.push({ type: 'text', value: text.slice(lastIndex, start) });
    }

    const term = match[1]?.trim();
    if (term) {
      parts.push({ type: 'term', value: term });
    }

    lastIndex = end;
  }

  if (lastIndex < text.length) {
    parts.push({ type: 'text', value: text.slice(lastIndex) });
  }

  return parts;
}

/**
 * Extracts a gatha number from a target natural key.
 * Example: "samaysaar:amritchandra:गाथा:42:sanskrit" → "42"
 * Falls back to the segment after the last ":" that looks like a number.
 */
export function extractGathaNumberFromTargetNk(naturalKey: string): string {
  const gathaSegment = naturalKey.split(':गाथा:')[1];
  if (gathaSegment) {
    const num = gathaSegment.split(':')[0];
    if (num) return num;
  }
  // Fallback: look for a segment that is a pure number
  const parts = naturalKey.split(':');
  for (let i = parts.length - 1; i >= 0; i--) {
    if (/^\d+$/.test(parts[i])) return parts[i];
  }
  return '';
}

/**
 * Builds the deep-link URL for a gatha reading page with the match highlighted.
 * Returns /shastras/<shastra-nk>/gathas/<gatha-number>?match=<match.natural_key>
 */
export function buildGathaHref(match: ExtractMatch): string {
  const targetNk = match.target.natural_key;
  // shastra natural key is the first segment before the first ":"
  const shastraNk = targetNk.split(':')[0] ?? '';
  const gathaNumber = extractGathaNumberFromTargetNk(targetNk);
  return (
    `/shastras/${encodeURIComponent(shastraNk)}/gathas/${encodeURIComponent(gathaNumber)}` +
    `?match=${encodeURIComponent(match.natural_key)}`
  );
}
