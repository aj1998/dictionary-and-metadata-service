'use client';

import { Fragment, useState } from 'react';
import { Dialog } from '@base-ui/react/dialog';
import { X, ChevronRight } from 'lucide-react';
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

export type ShastraGroup = {
  groupKey: string;   // shastra_name, or '' for blocks with no resolved refs
  label: string;      // display label for the heading
  blocks: DefinitionBlock[];
};

// Groups topic-extract blocks by shastra name (derived from the primary shown ref).
// Blocks with no resolvable ref are grouped under '' / 'अन्य'.
// Preserves the original order of first occurrence of each group.
export function groupTopicExtractsByShastra(blocks: DefinitionBlock[]): ShastraGroup[] {
  const groups = new Map<string, ShastraGroup>();
  const order: string[] = [];

  for (const block of blocks) {
    if (block.kind === 'see_also') continue;
    const refs = pickRefsToShow(block);
    const key = refs.length > 0 ? (refs[0].shastra_name ?? '') : '';
    const label = key !== '' ? key : 'अन्य';

    if (!groups.has(key)) {
      groups.set(key, { groupKey: key, label, blocks: [] });
      order.push(key);
    }
    groups.get(key)!.blocks.push(block);
  }

  // Sort alphabetically by label using Hindi locale; अन्य (empty key) goes last.
  order.sort((a, b) => {
    if (a === '' && b !== '') return 1;
    if (b === '' && a !== '') return -1;
    return (groups.get(a)!.label).localeCompare(groups.get(b)!.label, 'hi');
  });

  return order.map((k) => groups.get(k)!);
}

const REF_BADGE_CLASSES = 'text-foreground-muted';

// Renders a single ref as a bulleted list row used inside the समान संदर्भ popover.
function RefListItem({ ref }: { ref: DefinitionReference }) {
  const sourceLabel = formatRefSourceLabel(ref);
  return (
    <li className="flex items-baseline gap-2 font-serif-hindi text-xs text-foreground">
      <span className="mt-0.5 shrink-0 text-foreground-subtle">•</span>
      <span className="flex flex-wrap items-center gap-x-1.5 gap-y-0.5">
        {sourceLabel && (
          <>
            <span className={cn('font-semibold', ref.is_teeka ? 'text-amber-700' : 'text-foreground-muted')}>
              {sourceLabel}
            </span>
            {ref.resolved_fields.length > 0 && (
              <span className="opacity-30">|</span>
            )}
          </>
        )}
        {ref.resolved_fields.map((f, fi) => (
          <span key={fi} className="flex items-center gap-0.5">
            {fi > 0 && <span className="opacity-30">·</span>}
            <span className="text-foreground-muted">{f.field}:</span>
            <span className="font-medium">{f.value}</span>
          </span>
        ))}
      </span>
    </li>
  );
}

function RefBadge({ ref, showShastra = false }: { ref: DefinitionReference; showShastra?: boolean }) {
  const badgeLabel = showShastra
    ? formatRefSourceLabel(ref) || null
    : ref.is_teeka ? (ref.teeka_name || null) : null;
  return (
    <span className={cn('inline-flex items-center gap-0 font-serif-hindi text-xs italic', REF_BADGE_CLASSES)}>
      {badgeLabel && (
        <>
          <span className="font-semibold">{badgeLabel}</span>
          {ref.resolved_fields.length > 0 && (
            <span className="mx-1.5 opacity-30">|</span>
          )}
        </>
      )}
      {ref.resolved_fields.map((f, fi) => (
        <span key={fi} className="flex items-center">
          {fi > 0 && <span className="mx-1 opacity-50">·</span>}
          <span className="opacity-80">{f.field}:</span>
          <span className="ml-0.5 text-[10px] font-medium not-italic">{f.value}</span>
        </span>
      ))}
    </span>
  );
}

function ShastraAccordion({ group, open, onToggle }: { group: ShastraGroup; open: boolean; onToggle: () => void }) {
  return (
    <div>
      <button
        type="button"
        onClick={onToggle}
        className="flex w-full items-center gap-1.5 py-1.5 text-left transition-colors hover:text-foreground"
        aria-expanded={open}
      >
        <ChevronRight
          strokeWidth={1.5}
          className={cn('size-3.5 shrink-0 text-foreground-muted transition-transform duration-150', open && 'rotate-90')}
        />
        <span className="font-serif-hindi text-sm font-semibold text-foreground">
          {group.label}
        </span>
        <span className="ml-1 font-sans text-xs text-foreground-subtle">
          ({group.blocks.length})
        </span>
      </button>
      {open && (
        <div className={cn('mt-1 space-y-3 pl-4', group.blocks.length > 1 && 'border-l-2 border-border')}>
          {group.blocks.map((block, i) => (
            <div key={i}>
              <ModalBlock block={block} />
            </div>
          ))}
        </div>
      )}
    </div>
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
      <div className={`rounded border-l-[3px] ${borderClass} bg-surface-muted p-3`}>
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
          <div className="flex flex-wrap gap-1.5">
            {refsToShow.map((ref, ri) => (
              <RefBadge key={ri} ref={ref} />
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
                <p className="mb-2.5 font-serif-hindi text-xs font-semibold uppercase tracking-widest text-foreground-muted">
                  समान संदर्भ ({hiddenRefs.length})
                </p>
                <ul className="space-y-1.5">
                  {hiddenRefs.map((ref, ri) => (
                    <RefListItem key={ri} ref={ref} />
                  ))}
                </ul>
              </PopoverContent>
            </Popover>
          )}
        </div>
      )}
    </div>
  );
}

// Top-level collapsible wrapper for a keyword section (e.g. "सिद्धांतकोष से").
// Mirrors the TopicExtractsSection collapse pattern so both paths look consistent.
function KeywordSectionAccordion({ h2Text, blocks }: { h2Text: string; blocks: DefinitionBlock[] }) {
  const [open, setOpen] = useState(true);
  const visibleCount = blocks.filter((b) => b.kind !== 'see_also').length;

  return (
    <div>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-1.5 py-1 text-left transition-colors hover:text-foreground"
        aria-expanded={open}
      >
        <ChevronRight
          strokeWidth={1.5}
          className={cn('size-3.5 shrink-0 text-foreground-muted transition-transform duration-150', open && 'rotate-90')}
        />
        <span className="text-xs font-medium uppercase tracking-wide text-foreground-muted">
          {h2Text}
        </span>
        <span className="ml-1 font-sans text-xs text-foreground-subtle">({visibleCount})</span>
      </button>
      {open && (
        <div className="mt-1 pl-2">
          <KeywordDefinitionBlocks blocks={blocks} />
        </div>
      )}
    </div>
  );
}

// Renders keyword definition blocks grouped by shastra via ShastraAccordion.
// Mirrors the topic-extracts grouping pattern so both paths look consistent.
function KeywordDefinitionBlocks({ blocks }: { blocks: DefinitionBlock[] }) {
  const groups = groupTopicExtractsByShastra(blocks);

  const [openMap, setOpenMap] = useState<Record<number, boolean>>(() =>
    Object.fromEntries(groups.map((_, i) => [i, true]))
  );

  const toggleOne = (i: number) =>
    setOpenMap((prev) => ({ ...prev, [i]: !prev[i] }));

  if (groups.length === 0) return null;

  return (
    <div className="space-y-1">
      {groups.map((group, gi) => (
        <Fragment key={group.groupKey || `__group_${gi}`}>
          {gi > 0 && <hr className="my-2 border-border" />}
          <ShastraAccordion
            group={group}
            open={openMap[gi] ?? true}
            onToggle={() => toggleOne(gi)}
          />
        </Fragment>
      ))}
    </div>
  );
}

function TopicExtractsSection({ blocks }: { blocks: DefinitionBlock[] }) {
  const visibleCount = blocks.filter((b) => b.kind !== 'see_also').length;
  const groups = groupTopicExtractsByShastra(blocks);

  // One open-state entry per group; all start expanded.
  const [openMap, setOpenMap] = useState<Record<number, boolean>>(() =>
    Object.fromEntries(groups.map((_, i) => [i, true]))
  );

  const allOpen = groups.every((_, i) => openMap[i]);

  const toggleAll = () => {
    const next = !allOpen;
    setOpenMap(Object.fromEntries(groups.map((_, i) => [i, next])));
  };

  const toggleOne = (i: number) =>
    setOpenMap((prev) => ({ ...prev, [i]: !prev[i] }));

  return (
    <div>
      <button
        type="button"
        onClick={toggleAll}
        className="flex w-full items-center gap-1.5 py-1 text-left transition-colors hover:text-foreground"
        aria-expanded={allOpen}
      >
        <ChevronRight
          strokeWidth={1.5}
          className={cn('size-3.5 shrink-0 text-foreground-muted transition-transform duration-150', allOpen && 'rotate-90')}
        />
        <span className="text-xs font-medium uppercase tracking-wide text-foreground-muted">
          विषय अंश
        </span>
        <span className="ml-1 font-sans text-xs text-foreground-subtle">({visibleCount})</span>
      </button>
      <div className="mt-1">
        {groups.map((group, gi) => (
          <Fragment key={group.groupKey || `__group_${gi}`}>
            {gi > 0 && <hr className="my-2 border-border" />}
            <ShastraAccordion
              group={group}
              open={openMap[gi] ?? true}
              onToggle={() => toggleOne(gi)}
            />
          </Fragment>
        ))}
      </div>
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
              <div className="space-y-2">
                {definitionSections.map((section, si) => (
                  <Fragment key={section.section_index}>
                    {si > 0 && <hr className="my-2 border-border" />}
                    <KeywordSectionAccordion
                      h2Text={section.h2_text}
                      blocks={section.definitions.flatMap((def) => def.blocks)}
                    />
                  </Fragment>
                ))}
              </div>
            )}

            {topicExtracts && <TopicExtractsSection blocks={topicExtracts} />}
          </div>
        </Dialog.Popup>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
