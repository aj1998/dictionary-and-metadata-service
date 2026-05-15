'use client';

import { Dialog } from '@base-ui/react/dialog';
import { X } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { DefinitionBlock, KeywordPageSection } from '@/lib/types';

interface DefinitionModalProps {
  open: boolean;
  onClose: () => void;
  title: string;
  definitionSections?: KeywordPageSection[];
  topicExtracts?: DefinitionBlock[];
}

function ModalBlock({ block }: { block: DefinitionBlock }) {
  const isSanskrit = block.kind === 'sanskrit_text' || block.kind === 'prakrit_text';

  // Prefer non-inline references; fall back to inline ones only if no non-inline exist.
  // Skip any reference that has no resolved_fields.
  const nonInline = block.references.filter(r => !r.inline_reference);
  const candidates = nonInline.length > 0 ? nonInline : block.references.filter(r => r.inline_reference);
  const refsToShow = candidates.filter(r => r.resolved_fields.length > 0);

  return (
    <div>
      <div className={cn(isSanskrit && 'rounded border-l-4 border-cat-keyword bg-surface-muted p-3')}>
        <p className={cn(
          'font-serif-hindi text-foreground',
          isSanskrit ? 'text-sm' : 'text-[length:var(--font-size-body)]',
        )}>
          {block.text_devanagari}
        </p>
        {block.hindi_translation && (
          <p className={cn(
            'font-serif-hindi text-foreground-muted',
            isSanskrit ? 'mt-1.5 text-sm' : 'mt-1 text-sm',
          )}>
            {block.hindi_translation}
          </p>
        )}
      </div>
      {refsToShow.length > 0 && (
        <div className="mt-1.5 flex flex-wrap gap-1.5 border-t border-border pt-1.5">
          {refsToShow.map((ref, ri) => {
            const sourceName = ref.is_teeka ? ref.teeka_name : ref.shastra_name;
            return (
              <span
                key={ri}
                className={cn(
                  'inline-flex items-center gap-0 rounded-full px-2.5 py-0.5 text-xs ring-1',
                  ref.is_teeka
                    ? 'bg-amber-50 text-amber-800 ring-amber-200'
                    : 'bg-surface-muted text-foreground-muted ring-border',
                )}
              >
                {sourceName && (
                  <>
                    <span className={cn(
                      'font-semibold',
                      ref.is_teeka ? 'text-amber-700' : 'text-sky-700',
                    )}>
                      {sourceName}
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
          })}
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
              <div className="space-y-8">
                {definitionSections.map((section) => (
                  <div key={section.section_index}>
                    <p className="mb-3 text-xs font-medium uppercase tracking-wide text-foreground-muted">
                      {section.h2_text}
                    </p>
                    {section.definitions.map((def) => (
                      <div key={def.definition_index} className="space-y-3">
                        {def.blocks.map((block, bi) => (
                          <ModalBlock key={bi} block={block} />
                        ))}
                      </div>
                    ))}
                  </div>
                ))}
              </div>
            )}

            {topicExtracts && (
              <div className="space-y-3">
                <p className="text-xs font-medium uppercase tracking-wide text-foreground-muted">
                  विषय अंश ({topicExtracts.length})
                </p>
                {topicExtracts.map((block, i) => (
                  <ModalBlock key={i} block={block} />
                ))}
              </div>
            )}
          </div>
        </Dialog.Popup>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
