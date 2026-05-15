'use client';

import { useEffect, useMemo, useState } from 'react';
import { X, ArrowRight } from 'lucide-react';
import { cn } from '@/lib/utils';
import { BadgeChip } from '@/components/BadgeChip';
import { StatTileRow } from '@/components/StatTileRow';
import { ConnectedItemRow } from '@/components/ConnectedItemRow';
import { PrimaryCTA } from '@/components/PrimaryCTA';
import { DefinitionModal } from '@/components/DefinitionModal';
import { EDGE_LABELS } from '@/components/RelationConnector';
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet';
import * as dataApi from '@/lib/api/data';
import { ApiError } from '@/lib/api/_fetch';
import type { DefinitionBlock, EdgeKind, EntityDetail, GraphEdge, GraphNode, KeywordPageSection } from '@/lib/types';

const EDGE_DESCRIPTIONS: Partial<Record<EdgeKind, string>> = {
  RELATED_TO: 'These two entities are contextually related.',
  HAS_TOPIC: 'Source contains the target topic.',
  MENTIONS_KEYWORD: 'Source mentions this keyword explicitly.',
};

function buildTiles(detail: EntityDetail): [{ count: number; label: string }, { count: number; label: string }, { count: number; label: string }] {
  const entries = Object.entries(detail.stats ?? {}).slice(0, 3);
  while (entries.length < 3) entries.push(['-', 0]);
  return [
    { label: entries[0][0], count: Number(entries[0][1]) || 0 },
    { label: entries[1][0], count: Number(entries[1][1]) || 0 },
    { label: entries[2][0], count: Number(entries[2][1]) || 0 },
  ];
}

function BlockPreview({ block }: { block: DefinitionBlock }) {
  const isSanskrit = block.kind === 'sanskrit_text' || block.kind === 'prakrit_text';
  const devanagari = block.text_devanagari.length > 180
    ? block.text_devanagari.slice(0, 180) + '…'
    : block.text_devanagari;
  return (
    <div className={cn(isSanskrit && 'rounded border-l-4 border-cat-keyword bg-surface-muted p-3')}>
      <p className={cn(
        'font-serif-hindi text-foreground',
        isSanskrit ? 'text-sm' : 'text-[length:var(--font-size-body)]',
      )}>
        {devanagari}
      </p>
      {block.hindi_translation && (
        <p className="mt-1 font-serif-hindi text-sm text-foreground-muted">
          {block.hindi_translation}
        </p>
      )}
    </div>
  );
}

function KeywordDefinitionPreview({ sections }: { sections: KeywordPageSection[] }) {
  const section = sections[0];
  if (!section) return null;
  const blocks = section.definitions[0]?.blocks.slice(0, 2) ?? [];
  return (
    <div className="space-y-2">
      <p className="text-xs font-medium uppercase tracking-wide text-foreground-muted">{section.h2_text}</p>
      {blocks.map((block, i) => <BlockPreview key={i} block={block} />)}
    </div>
  );
}

export interface DetailsPanelProps {
  open: boolean;
  selected: { kind: 'node'; id: string } | { kind: 'edge'; id: string } | null;
  nodes: Record<string, GraphNode>;
  edges: Record<string, GraphEdge>;
  depth: 1 | 2 | 3 | 4;
  onClose: () => void;
  onSelectNode: (nk: string) => void;
  onExpand: (nk: string, depth: 1 | 2 | 3 | 4) => void;
}

export function DetailsPanel({ open, selected, nodes, edges, depth, onClose, onSelectNode, onExpand }: DetailsPanelProps) {
  const [detail, setDetail] = useState<EntityDetail | null>(null);
  const [isDesktop, setIsDesktop] = useState(false);
  const [definitionModalOpen, setDefinitionModalOpen] = useState(false);

  const selectedNode = selected?.kind === 'node' ? nodes[selected.id] : null;
  const selectedEdge = selected?.kind === 'edge' ? edges[selected.id] : null;

  useEffect(() => {
    let cancelled = false;
    async function run() {
      if (!selectedNode) {
        setDetail(null);
        return;
      }
      try {
        const response = await dataApi.getEntityDetail(selectedNode.kind, selectedNode.nk);
        if (!cancelled) setDetail(response);
      } catch (err) {
        if (!(err instanceof ApiError && err.status === 404)) {
          console.error('details fetch failed', err);
        }
        if (!cancelled) setDetail(null);
      }
    }
    void run();
    return () => {
      cancelled = true;
    };
  }, [selectedNode?.nk, selectedNode?.kind]);

  useEffect(() => {
    setDefinitionModalOpen(false);
  }, [selectedNode?.nk]);

  const edgeNodes = useMemo(() => {
    if (!selectedEdge) return { src: null, dst: null };
    return { src: nodes[selectedEdge.src] ?? null, dst: nodes[selectedEdge.dst] ?? null };
  }, [selectedEdge, nodes]);

  useEffect(() => {
    const media = window.matchMedia('(min-width: 1280px)');
    const sync = () => setIsDesktop(media.matches);
    sync();
    media.addEventListener('change', sync);
    return () => media.removeEventListener('change', sync);
  }, []);

  const hasDefinitionContent = !!(detail?.definitionSections || detail?.topicExtracts);

  const vivaranSection = detail?.definitionSections ? (
    <KeywordDefinitionPreview sections={detail.definitionSections} />
  ) : detail?.topicExtracts?.length ? (
    <div className="space-y-2">
      {detail.topicExtracts.slice(0, 2).map((block, i) => (
        <BlockPreview key={i} block={block} />
      ))}
      {detail.topicExtracts.length > 2 && (
        <p className="text-xs text-foreground-muted">+{detail.topicExtracts.length - 2} और…</p>
      )}
    </div>
  ) : (
    <p className="font-serif-hindi text-[length:var(--font-size-body)] text-foreground">
      {detail?.description ?? 'विवरण उपलब्ध नहीं है।'}
    </p>
  );

  const body = selectedNode ? (
    <div className="flex flex-col">
      <div className="border-b border-border p-4">
        <BadgeChip kind={selectedNode.kind} />
        <h2 className="mt-2 font-serif-hindi text-[length:var(--font-size-h1)] font-semibold text-foreground">{selectedNode.title_hi}</h2>
        {selectedNode.title_en && <p className="text-[length:var(--font-size-sm)] text-foreground-muted">{selectedNode.title_en}</p>}
      </div>
      <div className="flex-1 space-y-4 overflow-y-auto p-4">
        {detail && <StatTileRow tiles={buildTiles(detail)} />}
        <section>
          <h3 className="mb-2 text-[length:var(--font-size-h3)] font-semibold">विवरण</h3>
          {vivaranSection}
        </section>
        <section>
          <h3 className="mb-2 text-[length:var(--font-size-h3)] font-semibold">संबंधित</h3>
          <div className="space-y-2">
            {(detail?.connected ?? []).slice(0, 5).map((row) => (
              <ConnectedItemRow key={row.nk} kind={row.kind} titleHi={row.title_hi} titleEn={row.title_en} onClick={() => onSelectNode(row.nk)} />
            ))}
          </div>
          <button
            type="button"
            className="mt-3 text-sm font-medium text-accent hover:underline"
            onClick={() => onExpand(selectedNode.nk, Math.min(4, depth + 1) as 1 | 2 | 3 | 4)}
          >
            View All Connections →
          </button>
        </section>
      </div>
      {hasDefinitionContent && (
        <div className="border-t border-border py-4">
          <PrimaryCTA
            variant="soft"
            labelHi="पूरा वर्णन पढ़ें"
            onClick={() => setDefinitionModalOpen(true)}
          />
        </div>
      )}
    </div>
  ) : selectedEdge ? (
    <div className="h-full overflow-y-auto p-4">
      <div className="mb-3 inline-flex rounded-[var(--radius-pill)] bg-accent-soft px-3 py-1 text-xs font-medium text-accent">{EDGE_LABELS[selectedEdge.kind]}</div>
      <h2 className="mb-1 flex items-center gap-2 text-lg font-semibold">
        <span>{edgeNodes.src?.title_hi ?? selectedEdge.src}</span>
        <ArrowRight className="size-4" />
        <span>{edgeNodes.dst?.title_hi ?? selectedEdge.dst}</span>
      </h2>
      <p className="mb-3 text-sm text-foreground-muted">{selectedEdge.kind}</p>
      <p className="mb-4 text-sm text-foreground">{EDGE_DESCRIPTIONS[selectedEdge.kind] ?? 'Relation between connected entities.'}</p>
      <div className="space-y-2">
        {edgeNodes.src && <ConnectedItemRow kind={edgeNodes.src.kind} titleHi={edgeNodes.src.title_hi} titleEn={edgeNodes.src.title_en} onClick={() => onSelectNode(edgeNodes.src!.nk)} />}
        {edgeNodes.dst && <ConnectedItemRow kind={edgeNodes.dst.kind} titleHi={edgeNodes.dst.title_hi} titleEn={edgeNodes.dst.title_en} onClick={() => onSelectNode(edgeNodes.dst!.nk)} />}
      </div>
    </div>
  ) : null;

  if (!open || !body) return null;

  const modal = selectedNode && hasDefinitionContent ? (
    <DefinitionModal
      open={definitionModalOpen}
      onClose={() => setDefinitionModalOpen(false)}
      title={selectedNode.title_hi}
      definitionSections={detail?.definitionSections}
      topicExtracts={detail?.topicExtracts}
    />
  ) : null;

  if (isDesktop) {
    return (
      <>
        <aside className="flex h-screen w-[380px] shrink-0 flex-col overflow-hidden border-l border-border bg-surface">
          <div className="sticky top-0 z-10 flex items-center justify-between border-b border-border bg-surface px-4 py-3">
            <p className="text-sm font-medium">विवरण</p>
            <button type="button" aria-label="Close details" onClick={onClose}><X className="size-4" /></button>
          </div>
          <div className="flex flex-1 flex-col overflow-hidden">
            {body}
          </div>
        </aside>
        {modal}
      </>
    );
  }

  return (
    <>
      <Sheet open={open} onOpenChange={(v) => { if (!v) onClose(); }}>
        <SheetContent side="bottom" className="h-[75vh] p-0">
          <SheetHeader className="border-b border-border px-4 py-3">
            <SheetTitle>विवरण</SheetTitle>
          </SheetHeader>
          {body}
        </SheetContent>
      </Sheet>
      {modal}
    </>
  );
}
