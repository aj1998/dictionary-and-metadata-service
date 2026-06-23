import { describe, expect, it } from 'vitest';
import { extractBracketTerms, splitTeekaByBracketTerms, extractGathaNumberFromTargetNk, buildGathaHref, GATHA_ENTITY_KEYWORDS, getRefGathaEntity, buildShastraGathaHref } from '@/lib/gatha-content';
import type { DefinitionReference, ExtractMatch } from '@/lib/types';

function makeRef(overrides: Partial<DefinitionReference> = {}): DefinitionReference {
  return {
    text: '',
    inline_reference: false,
    needs_manual_match: false,
    is_teeka: false,
    teeka_name: '',
    shastra_name: null,
    match_method: null,
    resolved_fields: [],
    ...overrides,
  };
}

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

  it('appends sibling match keys as repeated match params', () => {
    const href = buildGathaHref(
      makeMatch('samaysaar:गाथा:42:sanskrit', 'match:verse'),
      ['match:anvayartha', 'match:verse'], // dup of primary is de-duped
    );
    expect(href).toContain('?match=match%3Averse');
    expect(href).toContain('&match=match%3Aanvayartha');
    // primary key only once
    expect(href.match(/match%3Averse/g)?.length).toBe(1);
  });
});

describe('GATHA_ENTITY_KEYWORDS', () => {
  it('mirrors parser_configs/jainkosh.yaml reference.entity_keywords.gatha', () => {
    expect([...GATHA_ENTITY_KEYWORDS]).toEqual(['गाथा', 'श्लोक', 'सूत्र', 'दोहक', 'वार्तिक']);
  });
});

describe('getRefGathaEntity', () => {
  it('returns the matching field for गाथा', () => {
    const ref = makeRef({ resolved_fields: [{ field: 'गाथा', value: '42' }] });
    expect(getRefGathaEntity(ref)).toEqual({ field: 'गाथा', value: '42' });
  });

  it('returns the matching field for श्लोक', () => {
    const ref = makeRef({ resolved_fields: [{ field: 'श्लोक', value: '7' }] });
    expect(getRefGathaEntity(ref)).toEqual({ field: 'श्लोक', value: '7' });
  });

  it('returns the matching field for सूत्र / दोहक / वार्तिक', () => {
    for (const kw of ['सूत्र', 'दोहक', 'वार्तिक']) {
      const ref = makeRef({ resolved_fields: [{ field: kw, value: '1' }] });
      expect(getRefGathaEntity(ref)).toEqual({ field: kw, value: '1' });
    }
  });

  it('returns the first matching field when multiple are present', () => {
    const ref = makeRef({
      resolved_fields: [
        { field: 'अधिकार', value: 'X' },
        { field: 'गाथा', value: '10' },
        { field: 'श्लोक', value: '20' },
      ],
    });
    expect(getRefGathaEntity(ref)).toEqual({ field: 'गाथा', value: '10' });
  });

  it('returns null when no gatha entity keyword is present', () => {
    const ref = makeRef({ resolved_fields: [{ field: 'पृष्ठ', value: '12' }] });
    expect(getRefGathaEntity(ref)).toBeNull();
  });

  it('returns null when a matching field has an empty value', () => {
    const ref = makeRef({ resolved_fields: [{ field: 'गाथा', value: '' }] });
    expect(getRefGathaEntity(ref)).toBeNull();
  });

  it('returns null for refs with no resolved_fields', () => {
    expect(getRefGathaEntity(makeRef())).toBeNull();
  });
});

describe('buildShastraGathaHref', () => {
  it('builds /shastras/<shastra>/gathas/<shastra>:<field>:<value> with URL encoding', () => {
    expect(buildShastraGathaHref('samaysaar', 'गाथा', '42')).toBe(
      `/shastras/samaysaar/gathas/${encodeURIComponent('samaysaar:गाथा:42')}`,
    );
  });

  it('produces the natural-key gatha segment for Devanagari shastra names', () => {
    // Mirrors the format the user pinned:
    // /shastras/<समयसार>/gathas/<समयसार:गाथा:1>
    const href = buildShastraGathaHref('समयसार', 'गाथा', '1');
    expect(href).toBe(
      `/shastras/${encodeURIComponent('समयसार')}/gathas/${encodeURIComponent('समयसार:गाथा:1')}`,
    );
  });

  it('encodes the `:` separator and Devanagari numerals inside the gatha segment', () => {
    const href = buildShastraGathaHref('समयसार', 'गाथा', '१०');
    expect(href).toContain(encodeURIComponent('समयसार:गाथा:१०'));
    expect(href).not.toContain(':गाथा:'); // raw `:` must be percent-encoded as %3A
  });
});
