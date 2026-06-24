import { describe, expect, it } from 'vitest';
import { planRefLink, findMatchForRef, type MatchEntry } from '@/components/ViewInShastraButton';
import type { DefinitionReference } from '@/lib/types';

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

function makeEntry(overrides: Partial<MatchEntry> = {}): MatchEntry {
  return {
    natural_key: 'mk:1',
    shastra_nk: 'samaysaar',
    gatha_nk: 'samaysaar:गाथा:42',
    status: 'matched',
    href: '/shastras/samaysaar/gathas/42?match=mk%3A1',
    label: 'samaysaar गाथा 42',
    ...overrides,
  };
}

describe('planRefLink', () => {
  const INGESTED = new Set(['समयसार', 'pravachansaar', 'samaysaar']);

  it('returns matched plan when match entry status is matched (ignores ingested set)', () => {
    const plan = planRefLink(makeRef({ shastra_name: 'samaysaar' }), makeEntry(), null);
    expect(plan.kind).toBe('matched');
    if (plan.kind === 'matched') expect(plan.href).toContain('match=');
  });

  it('returns unmatched plan when match entry status is unmatched', () => {
    const plan = planRefLink(
      makeRef({ shastra_name: 'samaysaar' }),
      makeEntry({ status: 'unmatched' }),
      INGESTED,
    );
    expect(plan.kind).toBe('unmatched');
  });

  it('returns fallback grey link when ref has shastra (in ingested set) + gatha-entity field and no match entry', () => {
    const ref = makeRef({
      shastra_name: 'समयसार',
      resolved_fields: [{ field: 'गाथा', value: '1' }],
    });
    const plan = planRefLink(ref, undefined, INGESTED);
    expect(plan.kind).toBe('fallback');
    if (plan.kind === 'fallback') {
      // /shastras/<समयसार>/gathas/<समयसार:गाथा:1>
      expect(plan.href).toBe(
        `/shastras/${encodeURIComponent('समयसार')}/gathas/${encodeURIComponent('समयसार:गाथा:1')}`,
      );
      expect(plan.label).toContain('समयसार');
      expect(plan.label).toContain('1');
    }
  });

  it('returns fallback for श्लोक / सूत्र / दोहक / वार्तिक entity fields when shastra is ingested', () => {
    for (const kw of ['श्लोक', 'सूत्र', 'दोहक', 'वार्तिक']) {
      const ref = makeRef({
        shastra_name: 'pravachansaar',
        resolved_fields: [{ field: kw, value: '7' }],
      });
      const plan = planRefLink(ref, undefined, INGESTED);
      expect(plan.kind).toBe('fallback');
    }
  });

  it('suppresses fallback when shastra is NOT in the ingested set (no DB page for it)', () => {
    const ref = makeRef({
      shastra_name: 'तत्त्वप्रदीपिका',
      resolved_fields: [{ field: 'गाथा', value: '19' }],
    });
    expect(planRefLink(ref, undefined, INGESTED).kind).toBe('none');
  });

  it('suppresses fallback while the registry is still loading (set = null)', () => {
    const ref = makeRef({
      shastra_name: 'समयसार',
      resolved_fields: [{ field: 'गाथा', value: '1' }],
    });
    expect(planRefLink(ref, undefined, null).kind).toBe('none');
  });

  it('returns none when ref has no shastra_name', () => {
    const ref = makeRef({
      shastra_name: null,
      resolved_fields: [{ field: 'गाथा', value: '42' }],
    });
    expect(planRefLink(ref, undefined, INGESTED).kind).toBe('none');
  });

  it('returns none when shastra is ingested but no gatha-entity field', () => {
    const ref = makeRef({
      shastra_name: 'samaysaar',
      resolved_fields: [{ field: 'पृष्ठ', value: '12' }],
    });
    expect(planRefLink(ref, undefined, INGESTED).kind).toBe('none');
  });

  it('returns none when no match entry and no resolved fields', () => {
    const ref = makeRef({ shastra_name: 'samaysaar' });
    expect(planRefLink(ref, undefined, INGESTED).kind).toBe('none');
  });
});

describe('findMatchForRef', () => {
  it('prefers a matched entry over an unmatched sibling for the same gatha', () => {
    // A single block emits two targets for प्रवचनसार गाथा 23: the matched टीका
    // and an unmatched भावार्थ sibling that happens to appear first.
    const ref = makeRef({
      shastra_name: 'प्रवचनसार',
      resolved_fields: [{ field: 'गाथा', value: '23' }],
    });
    const entries: MatchEntry[] = [
      makeEntry({
        natural_key: 'bh:1',
        shastra_nk: 'प्रवचनसार',
        gatha_nk: 'प्रवचनसार:गाथा:23',
        status: 'unmatched',
      }),
      makeEntry({
        natural_key: 'teeka:1',
        shastra_nk: 'प्रवचनसार',
        gatha_nk: 'प्रवचनसार:गाथा:23',
        status: 'matched',
      }),
    ];
    expect(findMatchForRef(ref, entries)?.natural_key).toBe('teeka:1');
  });

  it('prefers a matched candidate even without a gatha field', () => {
    const ref = makeRef({ shastra_name: 'प्रवचनसार' });
    const entries: MatchEntry[] = [
      makeEntry({ natural_key: 'a', shastra_nk: 'प्रवचनसार', status: 'unmatched' }),
      makeEntry({ natural_key: 'b', shastra_nk: 'प्रवचनसार', status: 'matched' }),
    ];
    expect(findMatchForRef(ref, entries)?.natural_key).toBe('b');
  });
});
