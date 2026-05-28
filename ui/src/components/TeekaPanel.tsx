'use client';

import { useState } from 'react';
import { cn } from '@/lib/utils';

export interface TeekaPanelItem {
  key: string;
  label: string;
  content: string;
}

interface TeekaPanelProps {
  items: TeekaPanelItem[];
}

function markdownToHtml(text: string): string {
  // Collapse newlines before lines that open with a parenthetical annotation so they
  // render inline regardless of whether the paren is later wrapped in *em* or **strong**.
  const parenLike = String.raw`\*{0,2}\(+[^()\n]+\)+\*{0,2}`;
  const inlined = text
    .replace(new RegExp(`\\n+(${parenLike})`, 'g'), ' $1')
    .replace(new RegExp(`(${parenLike})\\n(?![\\n*\\-\\[])`, 'g'), '$1 ');

  const formatInline = (s: string) =>
    s
      .replace(/\*\*([^*\n]+)\*\*/g, '<strong>$1</strong>')
      .replace(/\*\(\(([^)]+)\)\)\*/g, '<em class="teeka-paren">($1)</em>')
      .replace(/(?<!\*)\*\(([^)\n]+)\)\*(?!\*)/g, '<em class="teeka-paren">($1)</em>')
      .replace(/(?<!\*)\*([^*\n]+)\*(?!\*)/g, '<em>$1</em>')
      .replace(/\(\(([^)]+)\)\)/g, '<span class="teeka-paren">($1)</span>');

  // Split on paragraph breaks; within each paragraph, group hyphen-prefixed lines into <ul>.
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

export function TeekaPanel({ items }: TeekaPanelProps) {
  const [active, setActive] = useState(0);

  if (items.length === 0) {
    return (
      <section className="rounded-[var(--radius-md)] border border-border bg-surface p-5 shadow-node">
        <h3 className="mb-3 font-serif-hindi text-base font-semibold">टीका</h3>
        <p className="text-sm text-foreground-muted">टीका उपलब्ध नहीं है।</p>
      </section>
    );
  }

  const current = items[active];

  return (
    <section className="rounded-[var(--radius-md)] border border-border bg-surface shadow-node overflow-hidden">
      <div className="px-5 pt-5 pb-3">
        <h3 className="font-serif-hindi text-base font-semibold text-foreground">टीका</h3>
      </div>

      {items.length > 1 && (
        <div className="flex overflow-x-auto border-b border-border px-5 gap-1">
          {items.map((item, i) => (
            <button
              key={item.key}
              onClick={() => setActive(i)}
              className={cn(
                'shrink-0 pb-2 pt-1 px-3 text-xs font-medium border-b-2 transition-colors whitespace-nowrap',
                i === active
                  ? 'border-accent text-accent'
                  : 'border-transparent text-foreground-muted hover:text-foreground'
              )}
            >
              {item.label}
            </button>
          ))}
        </div>
      )}

      {items.length === 1 && (
        <p className="px-5 pb-1 text-xs text-foreground-muted">{current.label}</p>
      )}

      <div
        className="px-5 py-4 overflow-y-auto max-h-[55vh] font-serif-hindi text-sm leading-8 text-foreground teeka-content"
        /* content is from internal DB, not user input */
        dangerouslySetInnerHTML={{ __html: markdownToHtml(current.content) }}
      />
    </section>
  );
}
