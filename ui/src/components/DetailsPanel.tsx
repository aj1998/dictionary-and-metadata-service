'use client';

import { useEffect, useMemo, useState } from 'react';
import { X, ArrowRight } from 'lucide-react';
import { BadgeChip } from '@/components/BadgeChip';
import { StatTileRow } from '@/components/StatTileRow';
import { ConnectedItemRow } from '@/components/ConnectedItemRow';
import { PrimaryCTA } from '@/components/PrimaryCTA';
import { EDGE_LABELS } from '@/components/RelationConnector';
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet';
import * as dataApi from '@/lib/api/data';
import { ApiError } from '@/lib/api/_fetch';
import type { EdgeKind, EntityDetail, GraphEdge, GraphNode } from '@/lib/types';

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

  const body = selectedNode ? (
    <div className="flex h-full flex-col">
      <div className="border-b border-border p-4">
        <BadgeChip kind={selectedNode.kind} />
        <h2 className="mt-2 font-serif-hindi text-[length:var(--font-size-h1)] font-semibold text-foreground">{selectedNode.title_hi}</h2>
        {selectedNode.title_en && <p className="text-[length:var(--font-size-sm)] text-foreground-muted">{selectedNode.title_en}</p>}
      </div>
      <div className="flex-1 space-y-4 overflow-y-auto p-4">
        {detail && <StatTileRow tiles={buildTiles(detail)} />}
        <section>
          <h3 className="mb-2 text-[length:var(--font-size-h3)] font-semibold">विवरण</h3>
          <p className="font-serif-hindi text-[length:var(--font-size-body)] text-foreground">
            {detail?.description ?? 'विवरण उपलब्ध नहीं है।'}
          </p>
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
      <div className="border-t border-border py-4">
        <PrimaryCTA labelHi="पूरा विवरण पढ़ें" labelEn="Read More" href={`/${selectedNode.kind}s/${selectedNode.nk}`} />
      </div>
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

  if (isDesktop) {
    return (
      <aside className="w-[380px] shrink-0 border-l border-border bg-surface">
        <div className="sticky top-0 z-10 flex items-center justify-between border-b border-border bg-surface px-4 py-3">
          <p className="text-sm font-medium">विवरण</p>
          <button type="button" aria-label="Close details" onClick={onClose}><X className="size-4" /></button>
        </div>
        {body}
      </aside>
    );
  }

  return (
    <Sheet open={open} onOpenChange={(v) => { if (!v) onClose(); }}>
      <SheetContent side="bottom" className="h-[75vh] p-0">
        <SheetHeader className="border-b border-border px-4 py-3">
          <SheetTitle>विवरण</SheetTitle>
        </SheetHeader>
        {body}
      </SheetContent>
    </Sheet>
  );
}
