'use client';

import { useEffect, useMemo, useRef } from 'react';
import { GraphCanvas, type CanvasEdge, type CanvasNode } from './GraphCanvas';
import * as navigationApi from '@/lib/api/navigation';
import { useGraphStore } from '@/lib/store/graphStore';
import { buildGraphQuery, parseGraphQuery } from '@/lib/store/graphUrlState';
import { buildCanvasNodes, buildCanvasEdges } from './graphViewHelpers';

export default function GraphPage() {
  const nodes = useGraphStore((s) => s.nodes);
  const edges = useGraphStore((s) => s.edges);
  const selected = useGraphStore((s) => s.selected);
  const pinned = useGraphStore((s) => s.pinned);
  const expanded = useGraphStore((s) => s.expanded);
  const depth = useGraphStore((s) => s.depth);
  const layout = useGraphStore((s) => s.layout);
  const categoryVisibility = useGraphStore((s) => s.categoryVisibility);

  const selectNode = useGraphStore((s) => s.selectNode);
  const selectEdge = useGraphStore((s) => s.selectEdge);
  const clearSelection = useGraphStore((s) => s.clearSelection);
  const togglePin = useGraphStore((s) => s.togglePin);
  const expandFromNode = useGraphStore((s) => s.expandFromNode);
  const seedFromPayload = useGraphStore((s) => s.seedFromPayload);
  const setDepth = useGraphStore((s) => s.setDepth);

  const hydratedRef = useRef(false);

  useEffect(() => {
    if (hydratedRef.current) return;
    hydratedRef.current = true;

    const parsed = parseGraphQuery(new URLSearchParams(window.location.search));
    setDepth(parsed.depth);

    for (const kind of ['shastra', 'gatha', 'topic', 'keyword'] as const) {
      useGraphStore.getState().setCategoryVisibility(kind, !parsed.hiddenCats.includes(kind));
    }

    async function boot() {
      try {
        if (parsed.node) {
          selectNode(parsed.node);
          await expandFromNode(parsed.node, parsed.depth);
        } else {
          const landing = await navigationApi.getNavLanding();
          seedFromPayload(landing, null);
        }
        if (parsed.edge) selectEdge(parsed.edge);
      } catch {
        // Keep canvas interactive and let empty-state render when services are down.
        useGraphStore.setState({ lastError: 'graph boot failed' });
      }
    }

    void boot();
  }, [expandFromNode, seedFromPayload, selectEdge, selectNode, setDepth]);

  useEffect(() => {
    const handle = window.setTimeout(() => {
      const hiddenCats = (Object.entries(categoryVisibility).filter(([, v]) => !v).map(([k]) => k)) as Array<'shastra' | 'gatha' | 'topic' | 'keyword'>;
      const query = buildGraphQuery({
        selectedNode: selected?.kind === 'node' ? selected.id : null,
        selectedEdge: selected?.kind === 'edge' ? selected.id : null,
        depth,
        hiddenCats,
      });
      const url = `${window.location.pathname}${query.toString() ? `?${query.toString()}` : ''}`;
      window.history.replaceState(null, '', url);
    }, 500);
    return () => window.clearTimeout(handle);
  }, [selected, depth, categoryVisibility]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      if (target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable)) return;
      if (e.key === 'Escape') clearSelection();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [clearSelection]);

  // BFS root for hierarchical layout: prefer the selected node, then the
  // first expanded node, then let GraphCanvas fall back to the first node.
  const focusNk = useMemo(() => {
    if (selected?.kind === 'node') return selected.id;
    const [first] = expanded;
    return first ?? null;
  }, [selected, expanded]);

  const canvasNodes = useMemo<CanvasNode[]>(() => {
    const selectedNodeId = selected?.kind === 'node' ? selected.id : null;
    return buildCanvasNodes(nodes, categoryVisibility, selectedNodeId, pinned) as CanvasNode[];
  }, [nodes, selected, pinned, categoryVisibility]);

  const canvasEdges = useMemo<CanvasEdge[]>(() => {
    const renderedNks = new Set(canvasNodes.map((n) => n.nk));
    const selectedEdgeId = selected?.kind === 'edge' ? selected.id : null;
    return buildCanvasEdges(edges, nodes, renderedNks, categoryVisibility, selectedEdgeId) as CanvasEdge[];
  }, [edges, nodes, selected, categoryVisibility, canvasNodes]);

  return (
    <>
      <GraphCanvas
        nodes={canvasNodes}
        edges={canvasEdges}
        layout={layout}
        focusNk={focusNk}
        onNodeClick={(nk) => {
          selectNode(nk);
          if (!expanded.has(nk)) void expandFromNode(nk, depth);
        }}
        onNodeDoubleClick={(nk) => {
          selectNode(nk);
          void expandFromNode(nk, 1);
        }}
        onNodePinToggle={togglePin}
        onEdgeClick={selectEdge}
        onCanvasClick={clearSelection}
      />

      <nav className="sr-only" aria-label="ग्राफ लीनियर दृश्य">
        <ul>
          {canvasNodes.map((node) => (
            <li key={node.nk}>
              <a href={`/${node.kind}s/${node.nk}`}>{node.titleHi}</a>
            </li>
          ))}
        </ul>
      </nav>
    </>
  );
}
