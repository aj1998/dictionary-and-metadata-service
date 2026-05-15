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
      {block.references.length > 0 && (
        <div className="mt-1 space-y-0.5 border-t border-border pt-1">
          {block.references.map((ref, ri) => (
            <p key={ri} className="text-xs italic text-foreground-muted">{ref.text}</p>
          ))}
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
