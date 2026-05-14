'use client';

import { CategoryFilterList } from '@/components/CategoryFilterList';
import { DetailsPanel } from '@/components/DetailsPanel';
import { useGraphStore } from '@/lib/store/graphStore';
import type { EntityKind } from '@/lib/types';

export default function GraphLayout({ children }: { children: React.ReactNode }) {
  const categoryVisibility = useGraphStore((s) => s.categoryVisibility);
  const depth = useGraphStore((s) => s.depth);
  const layout = useGraphStore((s) => s.layout);
  const nodes = useGraphStore((s) => s.nodes);
  const edges = useGraphStore((s) => s.edges);
  const selected = useGraphStore((s) => s.selected);
  const setCategoryVisibility = useGraphStore((s) => s.setCategoryVisibility);
  const setDepth = useGraphStore((s) => s.setDepth);
  const setLayout = useGraphStore((s) => s.setLayout);
  const reset = useGraphStore((s) => s.reset);
  const clearSelection = useGraphStore((s) => s.clearSelection);
  const selectNode = useGraphStore((s) => s.selectNode);
  const expandFromNode = useGraphStore((s) => s.expandFromNode);

  return (
    <div className="flex flex-1 overflow-hidden">
      <aside className="hidden w-[280px] shrink-0 flex-col overflow-y-auto border-r border-border bg-surface xl:flex" aria-label="ग्राफ फ़िल्टर">
        <CategoryFilterList
          visibility={categoryVisibility}
          onToggle={(kind: EntityKind) => setCategoryVisibility(kind, !categoryVisibility[kind])}
          depth={depth}
          onDepthChange={(next) => setDepth(next as 1 | 2 | 3 | 4)}
          layout={layout}
          onLayoutChange={setLayout}
          onReset={reset}
        />
      </aside>

      <main className="relative flex-1 overflow-hidden">{children}</main>

      <DetailsPanel
        open={Boolean(selected)}
        selected={selected}
        nodes={nodes}
        edges={edges}
        depth={depth}
        onClose={clearSelection}
        onSelectNode={selectNode}
        onExpand={(nk, d) => void expandFromNode(nk, d)}
      />
    </div>
  );
}
