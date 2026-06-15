import { describe, it, expect } from 'vitest';
import { teekaMarkdownToHtml } from '@/lib/format/teeka-markdown';

describe('teekaMarkdownToHtml — bold matcher allows inline `*`', () => {
  it('bolds a span that wraps an inline *((…))* italic notes block', () => {
    // Dravyasangrah 57.html शंका pattern: the <b> wraps a red-colored span
    // and an inline *((…))* italic notes-paren. The bold regex must close
    // even with the `*` characters from `*((` and `))*` inside.
    const md = '**<span style="color:red">शंका – ध्यान है *((व्रतों से बन्ध))* किन्तु?</span>**';
    const html = teekaMarkdownToHtml(md);
    expect(html).toContain('<strong>');
    expect(html).toContain('</strong>');
    expect(html).toContain('<em class="teeka-paren">(व्रतों से बन्ध)</em>');
    // No literal `**` should leak through.
    expect(html).not.toContain('**');
  });

  it('still bolds the plain case', () => {
    const md = '**Bold text**';
    const html = teekaMarkdownToHtml(md);
    expect(html).toContain('<strong>Bold text</strong>');
    expect(html).not.toContain('**');
  });

  it('preserves font-color spans inside bold', () => {
    // Regression for the red-font strip removal: <font color=red> must
    // render as <span style="color:red"> rather than being deleted.
    const md = '**<span style="color:red">शंका</span>**';
    const html = teekaMarkdownToHtml(md);
    expect(html).toContain('<strong><span style="color:red">शंका</span></strong>');
  });

  it('does not bold across a paragraph break', () => {
    // Single bold across `\n\n` should not collapse into one <strong>;
    // upstream Python wraps each paragraph in its own `**…**`.
    const md = '**foo**\n\n**bar**';
    const html = teekaMarkdownToHtml(md);
    expect(html).toContain('<strong>foo</strong>');
    expect(html).toContain('<strong>bar</strong>');
  });
});
