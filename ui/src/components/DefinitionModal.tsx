'use client';

import { Fragment } from 'react';
import { Dialog } from '@base-ui/react/dialog';
import { X } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import type { DefinitionBlock, DefinitionReference, KeywordPageSection } from '@/lib/types';

export type MarkdownSegment = { kind: 'text'; text: string } | { kind: 'bold'; text: string } | { kind: 'italic'; text: string };

// Parses **bold**, *italic*, _italic_ markdown tokens into typed segments.
export function parseMarkdownSegments(text: string | null): MarkdownSegment[] {
  if (!text) return [];
  const segments: MarkdownSegment[] = [];
  const regex = /\*\*(.+?)\*\*|\*(.+?)\*|_(.+?)_/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;
  while ((match = regex.exec(text)) !== null) {
    if (match.index > lastIndex) segments.push({ kind: 'text', text: text.slice(lastIndex, match.index) });
    if (match[1] !== undefined) {
      segments.push({ kind: 'bold', text: match[1] });
    } else {
      segments.push({ kind: 'italic', text: match[2] ?? match[3] });
    }
    lastIndex = regex.lastIndex;
  }
  if (lastIndex < text.length) segments.push({ kind: 'text', text: text.slice(lastIndex) });
  return segments;
}

// Renders parsed markdown segments as React nodes.
export function renderInlineMarkdown(text: string | null): React.ReactNode {
  const segments = parseMarkdownSegments(text);
  if (segments.length === 1 && segments[0].kind === 'text') return segments[0].text;
  return (
    <Fragment>
      {segments.map((seg, i) =>
        seg.kind === 'bold' ? <strong key={i}>{seg.text}</strong>
        : seg.kind === 'italic' ? <em key={i}>{seg.text}</em>
        : seg.text
      )}
    </Fragment>
  );
}

interface DefinitionModalProps {
  open: boolean;
  onClose: () => void;
  title: string;
  definitionSections?: KeywordPageSection[];
  topicExtracts?: DefinitionBlock[];
}

// Returns the left-border colour class for a block.
// All blocks get a coloured left accent — grey when unreferenced, colour-coded when referenced.
// Teeka refs → amber; shastra refs on Sanskrit/Prakrit → teal; shastra refs on others → sky-blue.
export function getBlockBorderClass(block: DefinitionBlock, refsToShow: DefinitionReference[]): string {
  if (refsToShow.length === 0) return 'border-border-strong';
  if (refsToShow.some((r) => r.is_teeka)) return 'border-amber-400';
  if (block.kind === 'prakrit_text' || block.kind === 'prakrit_gatha') return 'border-emerald-500';
  if (block.kind === 'sanskrit_text') return 'border-cat-keyword';
  return 'border-sky-500';
}

// Returns the display label for a reference badge.
// Teeka refs show "shastra_name, teeka_name"; shastra refs show shastra_name.
export function formatRefSourceLabel(ref: DefinitionReference): string {
  if (ref.is_teeka) {
    const parts = [ref.shastra_name, ref.teeka_name].filter(Boolean);
    return parts.join(', ');
  }
  return ref.shastra_name ?? '';
}

export function pickRefsToShow(block: DefinitionBlock): DefinitionReference[] {
  const nonInline = block.references.filter((r) => !r.inline_reference);
  if (nonInline.length > 0) {
    // Show all non-inline references that have resolved fields.
    return nonInline.filter((r) => r.resolved_fields.length > 0);
  }
  // Fallback: show only the first qualifying inline reference.
  return block.references.filter((r) => r.inline_reference && r.resolved_fields.length > 0).slice(0, 1);
}

// Returns references with resolved fields that are NOT already shown by pickRefsToShow.
export function pickHiddenRefs(block: DefinitionBlock): DefinitionReference[] {
  const shownSet = new Set(pickRefsToShow(block));
  return block.references.filter((r) => r.resolved_fields.length > 0 && !shownSet.has(r));
}

function RefBadge({ ref, isPrakrit }: { ref: DefinitionReference; isPrakrit: boolean }) {
  const sourceLabel = formatRefSourceLabel(ref);
  return (
    <span
      className={cn(
        'inline-flex items-center gap-0 rounded-full px-2.5 py-0.5 text-xs ring-1',
        ref.is_teeka
          ? 'bg-amber-50 text-amber-800 ring-amber-200'
          : 'bg-surface-muted text-foreground-muted ring-border',
      )}
    >
      {sourceLabel && (
        <>
          <span className={cn(
            'font-semibold',
            ref.is_teeka ? 'text-amber-700' : isPrakrit ? 'text-emerald-700' : 'text-sky-700',
          )}>
            {sourceLabel}
          </span>
          {ref.resolved_fields.length > 0 && (
            <span className="mx-1.5 opacity-30">|</span>
          )}
        </>
      )}
      {ref.resolved_fields.map((f, fi) => (
        <span key={fi} className="flex items-center">
          {fi > 0 && <span className="mx-1 opacity-30">·</span>}
          <span className="opacity-60">{f.field}:</span>
          <span className="ml-0.5 font-medium">{f.value}</span>
        </span>
      ))}
    </span>
  );
}

function ModalBlock({ block }: { block: DefinitionBlock }) {
  const isPrakrit = block.kind === 'prakrit_text' || block.kind === 'prakrit_gatha';
  const isSanskrit = block.kind === 'sanskrit_text' || isPrakrit;
  const refsToShow = pickRefsToShow(block);
  const hiddenRefs = pickHiddenRefs(block);
  const borderClass = getBlockBorderClass(block, refsToShow);

  const hasAnyRef = refsToShow.length > 0 || hiddenRefs.length > 0;

  return (
    <div>
      <div className={`rounded border-l-4 ${borderClass} bg-surface-muted p-3`}>
        <p className={cn(
          'font-serif-hindi text-foreground',
          isSanskrit ? 'text-sm' : 'text-[length:var(--font-size-body)]',
        )}>
          {renderInlineMarkdown(block.text_devanagari)}
        </p>
        {block.hindi_translation && (
          <p className="mt-1.5 font-serif-hindi text-sm text-foreground-muted">
            {renderInlineMarkdown(block.hindi_translation)}
          </p>
        )}
      </div>
      {hasAnyRef && (
        <div className="mt-2 flex items-start gap-2">
          <div className="flex flex-1 flex-wrap gap-1.5">
            {refsToShow.map((ref, ri) => (
              <RefBadge key={ri} ref={ref} isPrakrit={isPrakrit} />
            ))}
          </div>
          {hiddenRefs.length > 0 && (
            <Popover>
              <PopoverTrigger
                aria-haspopup="dialog"
                className="ml-auto shrink-0 rounded-[var(--radius-sm)] bg-accent px-2.5 py-0.5 font-serif-hindi text-xs font-bold text-white transition-colors hover:bg-accent-hover"
              >
                समान संदर्भ
              </PopoverTrigger>
              <PopoverContent
                align="end"
                sideOffset={6}
                className="w-[480px] max-w-[min(480px,calc(100vw-2rem))] rounded-[var(--radius-md)] border border-border bg-surface p-4 text-foreground"
              >
                <p className="mb-2.5 font-sans text-xs font-semibold uppercase tracking-widest text-foreground-muted">
                  समान संदर्भ ({hiddenRefs.length})
                </p>
                <div className="flex flex-col gap-1.5 overflow-x-auto">
                  {hiddenRefs.map((ref, ri) => (
                    <RefBadge key={ri} ref={ref} isPrakrit={isPrakrit} />
                  ))}
                </div>
              </PopoverContent>
            </Popover>
          )}
        </div>
      )}
    </div>
  );
}

export function DefinitionModal({ open, onClose, title, definitionSections, topicExtracts }: DefinitionModalProps) {
  return (
    <Dialog.Root open={open} onOpenChange={(v) => { if (!v) onClose(); }}>
      <Dialog.Portal>
        <Dialog.Backdrop className="fixed inset-0 z-50 bg-black/40 transition-opacity duration-150 data-ending-style:opacity-0 data-starting-style:opacity-0 supports-backdrop-filter:backdrop-blur-sm" />
        <Dialog.Popup className="fixed left-1/2 top-1/2 z-50 flex max-h-[85vh] w-full max-w-2xl -translate-x-1/2 -translate-y-1/2 flex-col rounded-[var(--radius-lg)] bg-surface shadow-xl transition duration-150 data-ending-style:opacity-0 data-ending-style:scale-95 data-starting-style:opacity-0 data-starting-style:scale-95">
          <div className="flex shrink-0 items-start justify-between border-b border-border px-5 py-4">
            <Dialog.Title className="font-serif-hindi text-[length:var(--font-size-h1)] font-semibold text-foreground">
              {title}
            </Dialog.Title>
            <Dialog.Close
              className="ml-4 mt-0.5 shrink-0 rounded-[var(--radius-sm)] p-1 text-foreground-muted transition-colors hover:bg-surface-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/30"
              aria-label="बंद करें"
            >
              <X className="size-4" />
            </Dialog.Close>
          </div>

          <div className="flex-1 overflow-y-auto px-5 py-4">
            {definitionSections && (
              <div>
                {definitionSections.map((section, si) => (
                  <div key={section.section_index} className={si > 0 ? 'mt-8' : ''}>
                    {si > 0 && (
                      <div className="mb-4 space-y-1">
                        <div className="h-px bg-border-strong" />
                        <div className="h-px bg-border" />
                      </div>
                    )}
                    <div className="mb-4">
                      <span className="text-xs font-semibold uppercase tracking-widest text-foreground-muted">
                        {section.h2_text}
                      </span>
                    </div>
                    <div className="space-y-1">
                      {section.definitions.map((def, di) => {
                        const visibleBlocks = def.blocks.filter((b) => b.kind !== 'see_also');
                        return (
                          <div key={def.definition_index}>
                            {di > 0 && <hr className="my-3 border-border" />}
                            <div className="space-y-3">
                              {visibleBlocks.map((block, bi) => (
                                <div key={bi}>
                                  {bi > 0 && <hr className="mb-3 border-border" />}
                                  <ModalBlock block={block} />
                                </div>
                              ))}
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                ))}
              </div>
            )}

            {topicExtracts && (
              <div className="space-y-3">
                <p className="text-xs font-medium uppercase tracking-wide text-foreground-muted">
                  विषय अंश ({topicExtracts.filter((b) => b.kind !== 'see_also').length})
                </p>
                {topicExtracts.filter((b) => b.kind !== 'see_also').map((block, i) => (
                  <div key={i}>
                    {i > 0 && <hr className="mb-3 border-border" />}
                    <ModalBlock block={block} />
                  </div>
                ))}
              </div>
            )}
          </div>
        </Dialog.Popup>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
