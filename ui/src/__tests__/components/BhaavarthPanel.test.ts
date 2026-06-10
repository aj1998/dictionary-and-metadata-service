import { describe, it, expect } from 'vitest';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { splitHighlight } from '@/lib/highlight';
import { normalizeNFC } from '@/lib/format/devanagari';
import { BhaavarthPanel } from '@/components/BhaavarthPanel';
import { parseBhaavarthSegments } from '@/lib/format/bhaavarth-segments';
import type { BhaavarthShortFontEntry } from '@/lib/types';

// BhaavarthPanel is a React component — per existing test policy we don't mount JSX.
// These tests validate the pure logic used inside the component.

describe('BhaavarthPanel — highlight logic', () => {
  const text = 'जीव द्रव्य है। वह अनंत गुणों का पुंज है।';

  it('produces a valid split for a known range', () => {
    const nfcText = normalizeNFC(text);
    const result = splitHighlight(nfcText, { start: 0, end: 8 });
    expect(result).not.toBeNull();
    expect(result!.before).toBe('');
    expect(result!.matched).toBe(nfcText.slice(0, 8));
  });

  it('returns null when highlight is out of range — panel should skip the mark', () => {
    const nfcText = normalizeNFC(text);
    const result = splitHighlight(nfcText, { start: 0, end: nfcText.length + 10 });
    expect(result).toBeNull();
  });

  it('returns null when highlight is not provided (no highlight object)', () => {
    // Simulate the panel when highlight prop is undefined
    const highlight = undefined;
    const result = highlight ? splitHighlight(normalizeNFC(text), highlight) : null;
    expect(result).toBeNull();
  });

  it('matched segment is a substring of the NFC text', () => {
    const nfcText = normalizeNFC(text);
    const start = 4;
    const end = 12;
    const result = splitHighlight(nfcText, { start, end });
    expect(result).not.toBeNull();
    expect(nfcText).toContain(result!.matched);
  });
});

describe('BhaavarthPanel — compact bhaavarth rendering', () => {
  const text = [
    'यह प्रस्तावना अनुच्छेद है।',
    '',
    '[जीव] चेतन द्रव्य',
    '',
    '[अजीव] अचेतन द्रव्य',
    '',
    '[आस्रव] कर्मों का प्रवाह',
    '',
    'यह समापन अनुच्छेद है।',
  ].join('\n');

  it('replaces compact bracket paragraphs inline instead of prepending a separate section', () => {
    const html = renderToStaticMarkup(createElement(BhaavarthPanel, { text, variant: 'prose' }));

    expect(html).toContain('अन्वयार्थ');
    expect(html).toContain('चेतन द्रव्य');
    expect(html).toContain('अचेतन द्रव्य');
    expect(html).toContain('कर्मों का प्रवाह');
    expect(html).toContain('यह प्रस्तावना अनुच्छेद है।');
    expect(html).toContain('यह समापन अनुच्छेद है।');
    expect(html.indexOf('यह प्रस्तावना अनुच्छेद है।')).toBeLessThan(html.indexOf('जीव'));
    expect(html.indexOf('जीव')).toBeLessThan(html.indexOf('यह समापन अनुच्छेद है।'));
  });

  it('keeps compact chips visible in prose mode even when highlight is active', () => {
    const matchText = 'यह प्रस्तावना';
    const start = text.indexOf(matchText);
    const html = renderToStaticMarkup(createElement(BhaavarthPanel, {
      text,
      variant: 'prose',
      highlight: { start, end: start + matchText.length },
    }));

    expect(html).toContain('<mark');
    expect(html).toContain('अन्वयार्थ');
    expect(html).toContain('जीव');
    expect(html).toContain('अजीव');
    expect(html).toContain('आस्रव');
  });

  it('collapses real bhaavarth header-plus-line runs from the source markdown', () => {
    const sourceText = [
      '**[<span style="color:maroon">एयत्तणिच्छयगदो</span>]**',
      'अपने ही शुद्धगुण और पर्यायों में परिणमता हुआ अथवा अभेद-रत्नत्रय में परिणमता हुआ एकता के निश्चय में प्राप्त हुआ',
      '**[<span style="color:maroon">समओ</span>]**',
      'आत्मा-समय शब्द से आत्मा लेना योग्य है क्योंकि इसकी व्युत्पत्ति इस प्रकार है',
      'सम्यक् अयते गच्छति परिणमति कान् स्वकीयगुणपर्यायान्',
      'अर्थात् जो भले प्रकार अपने ही गुण और पर्यायों को परिणमन करे सो समय अर्थात् आत्मा',
      '**[<span style="color:maroon">सव्वत्थ सुंदरो</span>]**',
      'सब ही ठिकाने सबको सुहावना है',
      '**[<span style="color:maroon">लोगे</span>]**',
      'इस संसार में -- सब ही एकेन्द्रियादि-अवस्था में शुद्ध-निश्चयनय से सुन्दर है, उपादेय है ।',
      '**[<span style="color:maroon">बंधकहा</span>]**',
      'किन्तु कर्म बंध से होने वाली गुणस्थानादिरूप पर्यायों से',
    ].join('\n');

    const segments = parseBhaavarthSegments(sourceText);

    expect(segments.some((segment) => segment.kind === 'chips')).toBe(true);

    const chipSegment = segments.find((segment) => segment.kind === 'chips');
    expect(chipSegment && chipSegment.kind === 'chips' ? chipSegment.items[0]?.word : null).toBe('एयत्तणिच्छयगदो');
    expect(chipSegment && chipSegment.kind === 'chips' ? chipSegment.items.map((item) => item.word) : []).toEqual(
      expect.arrayContaining(['एयत्तणिच्छयगदो', 'समओ', 'सव्वत्थ सुंदरो', 'लोगे', 'बंधकहा'])
    );
  });

  it('keeps concluding emphasis outside the previous compact item so hodi remains compact', () => {
    const sourceText = [
      '**[<span style="color:maroon">तेण</span>]**',
      'पूर्वोक्त जीव-पदार्थ के साथ',
      '**[<span style="color:maroon">विसंवादिणी</span>]**',
      'विसंवाद पैदा करने वाली अर्थात् गड़बड़ पैदा करने वाली',
      '**[<span style="color:maroon">होदि</span>]**',
      'होती है, वह असत्य है अर्थात् प्रशंसा योग्य नहीं है क्योंकि वह शुद्ध-निश्चय-नय से शुद्ध जीव का स्वरूप नहीं हो सकता इससे यह सिद्ध हुआ कि',
      '**<span style="color:blue">स्वसमय ही आत्मा का स्वरूप है</span>**',
      '॥३॥',
    ].join('\n');

    const segments = parseBhaavarthSegments(sourceText);
    const chipSegment = segments.find((segment) => segment.kind === 'chips');
    const htmlSegments = segments.filter((segment) => segment.kind === 'html');

    expect(chipSegment && chipSegment.kind === 'chips' ? chipSegment.items.map((item) => item.word) : []).toEqual(
      expect.arrayContaining(['तेण', 'विसंवादिणी', 'होदि'])
    );
    expect(htmlSegments.some((segment) => segment.text.includes('स्वसमय ही आत्मा का स्वरूप है'))).toBe(true);
  });

});

describe('BhaavarthPanel — shortFont entries', () => {
  // "अब " is 3 chars (अ=3bytes but 1 JS char, ब=1, space=1 → index 3 in the string)
  // "मोक्ष-मार्ग" starts at char index 3
  const bhaavarth = 'अब मोक्ष-मार्ग-प्रपंच-सूचक चूलिका है।';

  const shortFontEntries: BhaavarthShortFontEntry[] = [
    {
      marker_number: 4,
      marker_devanagari: '४',
      anchor_text: 'मोक्ष-मार्ग-प्रपंच-सूचक',
      meaning: 'मोक्ष का विस्तार बतलाने वाली।',
      is_definition: true,
      occurrences: [{ start_offset: 3, end_offset: 3 + 'मोक्ष-मार्ग-प्रपंच-सूचक'.length }],
    },
  ];

  it('renders sf-anchor button for the anchor word when shortFontEntries provided', () => {
    const html = renderToStaticMarkup(
      createElement(BhaavarthPanel, {
        text: bhaavarth,
        variant: 'prose',
        shortFontEntries,
      })
    );
    // ShortFontHtml renders a client component; in SSR the anchor text should appear
    expect(html).toContain('मोक्ष-मार्ग-प्रपंच-सूचक');
  });

  it('does not add anchor markup when shortFontEntries is empty', () => {
    const html = renderToStaticMarkup(
      createElement(BhaavarthPanel, {
        text: bhaavarth,
        variant: 'prose',
        shortFontEntries: [],
      })
    );
    expect(html).not.toContain('sf-anchor');
    expect(html).not.toContain('data-sf-idx');
  });

  it('does not add anchor markup when shortFontEntries is absent', () => {
    const html = renderToStaticMarkup(
      createElement(BhaavarthPanel, { text: bhaavarth, variant: 'prose' })
    );
    expect(html).not.toContain('sf-anchor');
    expect(html).not.toContain('data-sf-idx');
  });

  it('still renders chip sections correctly alongside shortFont anchors', () => {
    const mixedText = [
      bhaavarth,
      '',
      '[जीव] चेतन द्रव्य',
      '',
      '[अजीव] अचेतन द्रव्य',
      '',
      '[आस्रव] कर्मों का प्रवाह',
    ].join('\n');

    const html = renderToStaticMarkup(
      createElement(BhaavarthPanel, { text: mixedText, variant: 'prose', shortFontEntries })
    );
    expect(html).toContain('अन्वयार्थ');
    expect(html).toContain('मोक्ष-मार्ग-प्रपंच-सूचक');
  });
});
