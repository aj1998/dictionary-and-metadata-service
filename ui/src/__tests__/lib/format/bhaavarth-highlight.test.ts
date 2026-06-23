import { describe, it, expect } from 'vitest';
import {
  injectHighlightSentinel,
  injectHighlightAndShortFont,
  postProcessHighlightHtml,
} from '@/lib/format/bhaavarth-highlight';
import { postProcessShortFontHtml } from '@/lib/format/bhaavarth-shortfont';
import { teekaMarkdownToHtml } from '@/lib/format/teeka-markdown';

describe('bhaavarth-highlight', () => {
  it('injects a sentinel pair around the range', () => {
    const out = injectHighlightSentinel('abcdef', 1, 4);
    expect(out).toBe('a\x02hl\x03bcd\x02/hl\x03ef');
  });

  it('returns text unchanged for empty / out-of-bounds ranges', () => {
    expect(injectHighlightSentinel('abc', 2, 2)).toBe('abc');
    expect(injectHighlightSentinel('abc', -1, 2)).toBe('abc');
    expect(injectHighlightSentinel('abc', 0, 99)).toBe('abc');
  });

  it('post-processes sentinels into a <mark> element', () => {
    const html = postProcessHighlightHtml('x\x02hl\x03y\x02/hl\x03z');
    expect(html).toContain('<mark');
    expect(html).toContain('>y</mark>');
    expect(html).not.toContain('\x02');
  });

  it('preserves markdown formatting inside the highlighted span', () => {
    // Markdown gloss marker must render as <em>, not leak raw `*((…))*`.
    const raw = 'अस्तित्व है *((अस्तित्व))* वह';
    const injected = injectHighlightSentinel(raw, 0, raw.length);
    const html = postProcessHighlightHtml(teekaMarkdownToHtml(injected));
    expect(html).toContain('<em class="teeka-paren">(अस्तित्व)</em>');
    expect(html).toContain('<mark');
    expect(html).not.toContain('*((');
    expect(html).not.toContain('\x02');
  });

  describe('injectHighlightAndShortFont', () => {
    it('keeps shortfont anchors clickable inside a highlighted span', () => {
      // "abc DEF ghi" — highlight covers the whole string, shortfont covers "DEF".
      const text = 'abc DEF ghi';
      const injected = injectHighlightAndShortFont(
        text,
        [{ localStart: 4, localEnd: 7, entryIdx: 2 }],
        0,
        text.length,
      );
      const html = postProcessHighlightHtml(postProcessShortFontHtml(teekaMarkdownToHtml(injected)));
      expect(html).toContain('<mark');
      expect(html).toContain('data-sf-idx="2"');
      expect(html).toContain('>DEF</button>');
      expect(html).not.toContain('\x02');
      // The shortfont anchor sits inside the mark (mark opens before the button).
      expect(html.indexOf('<mark')).toBeLessThan(html.indexOf('data-sf-idx'));
    });

    it('falls back to plain text when nothing to inject', () => {
      expect(injectHighlightAndShortFont('abc', [], 2, 2)).toBe('abc');
    });

    it('skips out-of-range shortfont spans', () => {
      const out = injectHighlightAndShortFont('abc', [{ localStart: 1, localEnd: 99, entryIdx: 0 }], 0, 3);
      expect(out).toContain('\x02hl\x03');
      expect(out).not.toContain('sf:0');
    });
  });
});
