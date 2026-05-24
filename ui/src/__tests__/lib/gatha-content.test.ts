import { describe, expect, it } from 'vitest';
import { extractBracketTerms, splitTeekaByBracketTerms } from '@/lib/gatha-content';

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
