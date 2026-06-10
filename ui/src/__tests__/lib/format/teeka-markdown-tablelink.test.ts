import { describe, it, expect } from 'vitest';
import { teekaMarkdownToHtml } from '@/lib/format/teeka-markdown';

describe('teekaMarkdownToHtml — inline table links', () => {
  it('converts [text](table://nk) to a button with data-bhaavarth-table-nk', () => {
    const md = 'देखें [तालिका देखें](table://table:jainkosh:foo:01) यहाँ।';
    const html = teekaMarkdownToHtml(md);
    expect(html).toContain('data-bhaavarth-table-nk="table:jainkosh:foo:01"');
    expect(html).toContain('bhaavarth-table-link');
    expect(html).toContain('तालिका देखें');
    expect(html).toContain('<button');
  });

  it('leaves ordinary external [text](https://...) as an anchor', () => {
    const md = 'visit [link](https://example.com/page) now';
    const html = teekaMarkdownToHtml(md);
    expect(html).toContain('<a href="https://example.com/page"');
    expect(html).not.toContain('data-bhaavarth-table-nk');
  });

  it('does not interfere with bracket-header parsing for chip lines', () => {
    const md = '**[शब्द]** अर्थ';
    const html = teekaMarkdownToHtml(md);
    expect(html).not.toContain('data-bhaavarth-table-nk');
  });
});
