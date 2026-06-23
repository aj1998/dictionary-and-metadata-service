import type { DefinitionReference, ExtractMatch } from '@/lib/types';

// Mirrors `reference.entity_keywords.gatha` in parser_configs/jainkosh.yaml.
// Refs whose resolved fields name any of these keywords describe a gatha-like
// target inside a shastra and therefore qualify for a fallback shastra link
// when the matcher has not produced a response.
export const GATHA_ENTITY_KEYWORDS = ['गाथा', 'श्लोक', 'सूत्र', 'दोहक', 'वार्तिक'] as const;

export type GathaEntityField = { field: string; value: string };

// Field names emitted by the parser can be prefixed with the shastra name —
// e.g. परमात्मप्रकाशगाथा, कषायपाहुड़-गाथा. Returns true when the field ends with
// any of the canonical gatha keywords.
export function isGathaEntityField(field: string): boolean {
  return (GATHA_ENTITY_KEYWORDS as readonly string[]).some(
    (k) => field === k || field.endsWith(k),
  );
}

// Strip the shastra-name prefix (and trailing hyphen, if any) from a field
// label so the modal displays just the canonical keyword (e.g.
// "परमात्मप्रकाशगाथा" → "गाथा", "कषायपाहुड़-गाथा" → "गाथा"). Non-gatha fields
// are returned unchanged.
export function displayFieldLabel(field: string): string {
  for (const k of GATHA_ENTITY_KEYWORDS) {
    if (field === k) return k;
    if (field.endsWith(k)) return k;
  }
  return field;
}

// Returns the first resolved field whose name is a gatha entity keyword.
export function getRefGathaEntity(ref: DefinitionReference): GathaEntityField | null {
  for (const f of ref.resolved_fields) {
    if (isGathaEntityField(f.field) && f.value) {
      return { field: f.field, value: f.value };
    }
  }
  return null;
}

// Builds a shastra/gatha deep-link URL without a match natural key. Used by
// the grey fallback link when the matcher returned no response for a ref that
// names a gatha entity in a known shastra.
//
// The gatha segment is the gatha's natural key, formatted as
// `<shastra>:<field>:<value>` (e.g. `समयसार:गाथा:1`). Both segments are
// URL-encoded for safe transport of Devanagari characters and the `:`
// separator.
export function buildShastraGathaHref(shastraNk: string, field: string, value: string): string {
  const gathaNk = `${shastraNk}:${field}:${value}`;
  return `/shastras/${encodeURIComponent(shastraNk)}/gathas/${encodeURIComponent(gathaNk)}`;
}

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
 * Returns /shastras/<shastra-nk>/gathas/<gatha-number>?match=<key>[&match=<key>…]
 *
 * `extraMatchKeys` carries sibling match natural-keys that target other panels
 * of the *same* gatha (e.g. the verse match plus the अन्वयार्थ/शब्दार्थ match),
 * so the reading page can highlight all of them at once.
 */
export function buildGathaHref(match: ExtractMatch, extraMatchKeys: string[] = []): string {
  const targetNk = match.target.natural_key;
  // shastra natural key is the first segment before the first ":"
  const shastraNk = match.target.shastra_natural_key ?? targetNk.split(':')[0] ?? '';
  // Prefer the owning-gatha natural key for non-gatha targets (kalash, kalash teeka, etc.)
  // so the link lands on the gatha page that actually contains that element in
  // "विशेष देखें". Fall back to the legacy heuristic when the matcher didn't
  // populate `gatha_natural_key`.
  const gathaNkOrNumber =
    match.target.gatha_natural_key ?? extractGathaNumberFromTargetNk(targetNk);
  const keys = [match.natural_key, ...extraMatchKeys.filter((k) => k !== match.natural_key)];
  const query = keys.map((k) => `match=${encodeURIComponent(k)}`).join('&');
  return (
    `/shastras/${encodeURIComponent(shastraNk)}/gathas/${encodeURIComponent(gathaNkOrNumber)}` +
    `?${query}`
  );
}
