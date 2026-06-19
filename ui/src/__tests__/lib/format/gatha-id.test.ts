import { describe, it, expect } from 'vitest';
import { compactFromResolvedFields, primaryGathaFieldName, uniqueLeadingIdValues } from '@/lib/format/gatha-id';
import type { DefinitionReference } from '@/lib/types';

function makeRef(
  fields: Array<{ field: string; value: string }>,
  overrides: Partial<DefinitionReference> = {},
): DefinitionReference {
  return {
    text: '',
    inline_reference: false,
    needs_manual_match: false,
    is_teeka: false,
    teeka_name: '',
    shastra_name: 'समयसार',
    match_method: null,
    resolved_fields: fields,
    ...overrides,
  };
}

describe('compactFromResolvedFields', () => {
  it('builds a compound compact from leading id fields up to the gatha keyword', () => {
    const ref = makeRef([
      { field: 'अधिकार', value: '1' },
      { field: 'परमात्मप्रकाशगाथा', value: '9' },
      { field: 'पृष्ठ', value: '12' },
    ]);
    expect(compactFromResolvedFields(ref)?.compact).toBe('1,9');
  });

  it('drops the teeka volume field पुस्तक for teeka refs (श्लोकवार्तिक → parent तत्त्वार्थसूत्र)', () => {
    // श्लोकवार्तिक ref: पुस्तक selects the teeka's printed volume and is NOT part
    // of the parent तत्त्वार्थसूत्र gatha identifier (अध्याय,तत्त्वार्थसूत्रसूत्र).
    const ref = makeRef(
      [
        { field: 'पुस्तक', value: '2' },
        { field: 'अध्याय', value: '1' },
        { field: 'तत्त्वार्थसूत्रसूत्र', value: '7' },
        { field: 'श्लोकवार्तिकवार्तिक', value: '9' },
        { field: 'पृष्ठ', value: '529' },
        { field: 'पंक्ति', value: '27' },
      ],
      { is_teeka: true, teeka_name: 'श्लोकवार्तिक', shastra_name: 'तत्त्वार्थसूत्र' },
    );
    // Must be "1,7" (अध्याय,सूत्र), not "2,1,7" — the parent route only accepts 2 values.
    expect(compactFromResolvedFields(ref)?.compact).toBe('1,7');
  });

  it('keeps पुस्तक for non-teeka shastras where it is the identifier (e.g. धवला)', () => {
    const ref = makeRef([
      { field: 'पुस्तक', value: '1' },
      { field: 'धवलासूत्र', value: '5' },
      { field: 'पृष्ठ', value: '3' },
    ]);
    expect(compactFromResolvedFields(ref)?.compact).toBe('1,5');
  });
});

describe('primaryGathaFieldName', () => {
  it('picks only the first gatha-keyword field, not later sub-locators (राजवार्तिक)', () => {
    // अध्याय:7 · सूत्र:12 · वार्तिक:2 · पृष्ठ:539 · पंक्ति:8 — the book link must
    // hang off सूत्र only, NOT off the trailing वार्तिक sub-locator.
    const ref = makeRef(
      [
        { field: 'अध्याय', value: '7' },
        { field: 'तत्त्वार्थसूत्रसूत्र', value: '12' },
        { field: 'राजवार्तिकवार्तिक', value: '2' },
        { field: 'पृष्ठ', value: '539' },
        { field: 'पंक्ति', value: '8' },
      ],
      { is_teeka: true, teeka_name: 'राजवार्तिक', shastra_name: 'तत्त्वार्थसूत्र' },
    );
    expect(primaryGathaFieldName(ref)).toBe('तत्त्वार्थसूत्रसूत्र');
  });

  it('returns null when the ref names no gatha entity', () => {
    const ref = makeRef([{ field: 'पृष्ठ', value: '5' }]);
    expect(primaryGathaFieldName(ref)).toBeNull();
  });

  it('returns the plain गाथा field for a legacy ref', () => {
    const ref = makeRef([{ field: 'गाथा', value: '71' }]);
    expect(primaryGathaFieldName(ref)).toBe('गाथा');
  });
});

describe('uniqueLeadingIdValues', () => {
  it('returns all distinct leading values numerically sorted', () => {
    const shastra = 'तत्त्वार्थसूत्र';
    const nks = [
      `${shastra}:अध्याय:1:तत्त्वार्थसूत्रसूत्र:1`,
      `${shastra}:अध्याय:10:तत्त्वार्थसूत्रसूत्र:1`,
      `${shastra}:अध्याय:2:तत्त्वार्थसूत्रसूत्र:1`,
      `${shastra}:अध्याय:1:तत्त्वार्थसूत्रसूत्र:2`,
    ];
    const result = uniqueLeadingIdValues(shastra, nks);
    expect(result?.fieldName).toBe('अध्याय');
    expect(result?.values).toEqual(['1', '2', '10']);
  });
});
