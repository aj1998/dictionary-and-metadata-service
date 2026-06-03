import { describe, expect, it } from 'vitest';
import { extractBracketTerms, splitTeekaByBracketTerms, extractGathaNumberFromTargetNk, buildGathaHref } from '@/lib/gatha-content';
import type { ExtractMatch } from '@/lib/types';

describe('gatha content helpers', () => {
  it('extracts unique bracketed terms', () => {
    const text = 'यह [जीव] और [अजीव] तथा पुनः [जीव] है';
    expect(extractBracketTerms(text)).toEqual(['जीव', 'अजीव']);
  });

  it('splits teeka into tagged and plain chunks', () => {
    const parts = splitTeekaByBracketTerms('तत्त्व [सम्यग्दर्शन] मार्ग');
    expect(parts).toEqual([
      { type: 'text', value: 'तत्त्व ' },
      { type: 'term', value: 'सम्यग्दर्शन' },
      { type: 'text', value: ' मार्ग' },
    ]);
  });
});

describe('extractGathaNumberFromTargetNk', () => {
  it('extracts gatha number from a teeka-style key', () => {
    expect(extractGathaNumberFromTargetNk('samaysaar:amritchandra:गाथा:42:sanskrit')).toBe('42');
  });

  it('extracts gatha number from a prakrit-style key', () => {
    expect(extractGathaNumberFromTargetNk('samaysaar:गाथा:1:prakrit')).toBe('1');
  });

  it('falls back to last numeric segment when no गाथा present', () => {
    expect(extractGathaNumberFromTargetNk('someshastra:section:007')).toBe('007');
  });

  it('returns empty string when no numeric segment found', () => {
    expect(extractGathaNumberFromTargetNk('no:numbers:here')).toBe('');
  });
});

describe('buildGathaHref', () => {
  function makeMatch(targetNk: string, matchNk: string): ExtractMatch {
    return {
      natural_key: matchNk,
      target: { collection: 'gatha_teeka_sanskrit', natural_key: targetNk, lang: 'san' },
      match: { status: 'matched', char_start: 10, char_end: 50 },
    };
  }

  it('builds the href with shastra nk, gatha number, and match param', () => {
    const href = buildGathaHref(makeMatch('samaysaar:amritchandra:गाथा:42:sanskrit', 'match:abc:1'));
    expect(href).toContain('/shastras/samaysaar/gathas/42');
    expect(href).toContain('?match=match%3Aabc%3A1');
  });

  it('URL-encodes the match natural key', () => {
    const href = buildGathaHref(makeMatch('niyamsaar:गाथा:10:prakrit', 'match:x:y:z'));
    expect(href).toContain('?match=match%3Ax%3Ay%3Az');
  });

  it('uses shastra from the first colon-separated segment', () => {
    const href = buildGathaHref(makeMatch('pravachansaar:teeka:गाथा:5:hindi', 'mk'));
    expect(href).toContain('/shastras/pravachansaar/');
  });
});
