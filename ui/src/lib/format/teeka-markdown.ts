// Shared markdown-ish renderer used by TeekaPanel, BhaavarthPanel, and the
// sanskrit-teeka variant of GathaPanel. Handles inline **bold**, *em*,
// parenthetical annotations like *((...))*, and groups hyphen-prefixed lines
// into <ul>. HTML tags already present in source (e.g. <span style="color:..">)
// are preserved verbatim because the output is rendered via dangerouslySetInnerHTML.
export function teekaMarkdownToHtml(text: string): string {
  // Strip leading BOM (U+FEFF) — present in some NJ-sourced bhaavarth docs.
  text = text.replace(/^﻿/, '');
  // Collapse 3+ consecutive newlines to 2 to remove excessive blank lines in source.
  text = text.replace(/\n{3,}/g, '\n\n');
  const parenLike = String.raw`\*{0,2}\(+[^()\n]+\)+\*{0,2}`;
  const inlined = text
    .replace(new RegExp(`\\n+(${parenLike})`, 'g'), ' $1')
    .replace(new RegExp(`(${parenLike})\\n(?![\\n*\\-\\[])`, 'g'), '$1 ');

  const formatInline = (s: string) =>
    s
      .replace(/\[([^\]]+)\]\(table:\/\/([^)\s]+)\)/g, (_m, label, nk) => {
        const safeNk = String(nk).replace(/"/g, '&quot;');
        return `<button type="button" data-bhaavarth-table-nk="${safeNk}" class="bhaavarth-table-link inline-flex items-center gap-1 px-1.5 py-0.5 mx-0.5 rounded-md border border-[var(--cat-table)] text-[var(--cat-table)] bg-[color:color-mix(in_srgb,var(--cat-table)_12%,transparent)] hover:bg-[color:color-mix(in_srgb,var(--cat-table)_22%,transparent)] transition align-baseline">${label}</button>`;
      })
      .replace(/\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g, (_m, label, href) => {
        const safeHref = String(href).replace(/"/g, '&quot;');
        return `<a href="${safeHref}" target="_blank" rel="noreferrer noopener">${label}</a>`;
      })
      .replace(/\*\*([^\n]+?)\*\*/g, '<strong>$1</strong>')
      .replace(/\*\(\(([^)]+)\)\)\*/g, '<em class="teeka-paren">($1)</em>')
      .replace(/(?<!\*)\*\(([^)\n]+)\)\*(?!\*)/g, '<em class="teeka-paren">($1)</em>')
      .replace(/(?<!\*)\*([^*\n]+)\*(?!\*)/g, '<em>$1</em>')
      .replace(/\(\(([^)]+)\)\)/g, '<span class="teeka-paren">($1)</span>');

  // Numbered section prefix: "1.", "3-4." etc. at the start of a paragraph.
  const SECTION_NUM_RE = /^(\d+(?:-\d+)?)\.\s+/;

  return inlined
    .split(/\n\n+/)
    .map((para) => {
      const lines = para.split('\n');
      const out: string[] = [];
      let listBuf: string[] = [];
      let textBuf: string[] = [];
      const flushList = () => {
        if (listBuf.length) {
          out.push(`<ul>${listBuf.map((l) => `<li>${formatInline(l)}</li>`).join('')}</ul>`);
          listBuf = [];
        }
      };
      const flushText = () => {
        for (const t of textBuf) {
          const trimmed = t.trim();
          if (!trimmed) continue;
          const numMatch = trimmed.match(SECTION_NUM_RE);
          if (numMatch) {
            const numLabel = `${numMatch[1]}.`;
            const rest = trimmed.slice(numMatch[0].length);
            out.push(`<div class="teeka-section-break"><span class="teeka-section-num">${numLabel}</span></div>`);
            if (rest) {
              const isDerivation = /[:्]\s*$/.test(rest);
              const cls = isDerivation ? ' class="teeka-derivation"' : '';
              out.push(`<p${cls}>${formatInline(rest)}</p>`);
            }
            continue;
          }
          const isDerivation = /[:्]\s*$/.test(trimmed);
          const cls = isDerivation ? ' class="teeka-derivation"' : '';
          out.push(`<p${cls}>${formatInline(t)}</p>`);
        }
        textBuf = [];
      };
      const headerRe = /^\s*(?:\*\*)?\[[^\n]*\](?:\*\*)?\s*$/;
      const boldRe = /^\s*\*\*[^\n]+\*\*\s*$/;
      let pendingBracket: string | null = null;
      let glueNext = false;
      for (const line of lines) {
        const hyphen = line.match(/^\s*-\s+(.*)$/);
        if (hyphen) {
          flushText();
          pendingBracket = null;
          glueNext = false;
          listBuf.push(hyphen[1]);
        } else if (headerRe.test(line)) {
          flushList();
          flushText();
          glueNext = false;
          pendingBracket = line.trim();
        } else if (boldRe.test(line)) {
          flushList();
          const piece = line.trim();
          if (pendingBracket) {
            pendingBracket = `${pendingBracket} ${piece}`;
          } else if (textBuf.length) {
            textBuf[textBuf.length - 1] = `${textBuf[textBuf.length - 1]} ${piece}`;
          } else {
            textBuf.push(piece);
          }
          glueNext = true;
        } else {
          flushList();
          if (pendingBracket) {
            textBuf.push(`${pendingBracket} ${line}`);
            pendingBracket = null;
            glueNext = false;
          } else if (glueNext && textBuf.length) {
            textBuf[textBuf.length - 1] = `${textBuf[textBuf.length - 1]} ${line}`;
            glueNext = false;
          } else {
            textBuf.push(line);
          }
        }
      }
      if (pendingBracket) textBuf.push(pendingBracket);
      flushText();
      flushList();
      return out.join('');
    })
    .join('');
}
