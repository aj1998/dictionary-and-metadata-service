import { getPreview } from '@/lib/api/navigation';
import type { GraphPayload } from '@/lib/types';
import Link from 'next/link';

export interface PreviewNode {
  nk: string;
  title: string;
  x: number;
  y: number;
}

export interface PreviewEdge {
  id: string;
  x1: number;
  y1: number;
  x2: number;
  y2: number;
}

export function buildPreviewLayout(payload: GraphPayload): { nodes: PreviewNode[]; edges: PreviewEdge[] } {
  const width = 280;
  const height = 180;
  const cx = width / 2;
  const cy = height / 2;
  const radius = Math.min(width, height) * 0.35;

  const nodes = payload.nodes.map((node, index) => {
    const angle = (index / Math.max(1, payload.nodes.length)) * Math.PI * 2;
    return {
      nk: node.nk,
      title: node.title_hi,
      x: Number((cx + Math.cos(angle) * radius).toFixed(2)),
      y: Number((cy + Math.sin(angle) * radius).toFixed(2)),
    };
  });

  const byNk = new Map(nodes.map((node) => [node.nk, node]));
  const edges = payload.edges
    .map((edge) => {
      const src = byNk.get(edge.src);
      const dst = byNk.get(edge.dst);
      if (!src || !dst) return null;
      return { id: edge.id, x1: src.x, y1: src.y, x2: dst.x, y2: dst.y };
    })
    .filter((edge): edge is PreviewEdge => edge !== null);

  return { nodes, edges };
}

interface MiniGraphPreviewProps {
  nk: string;
}

export async function MiniGraphPreview({ nk }: MiniGraphPreviewProps) {
  let payload: GraphPayload | null = null;
  try {
    payload = await getPreview(nk, 1);
  } catch (error) {
    console.error('MiniGraphPreview fetch failed', { nk, error });
  }

  const layout = payload ? buildPreviewLayout(payload) : { nodes: [], edges: [] };

  return (
    <div className="group relative overflow-hidden rounded-[var(--radius-md)] border border-border bg-surface p-3 shadow-node">
      <svg viewBox="0 0 280 180" className="h-[180px] w-full">
        <rect x="0" y="0" width="280" height="180" fill="var(--background)" />
        {layout.edges.map((edge) => (
          <line
            key={edge.id}
            x1={edge.x1}
            y1={edge.y1}
            x2={edge.x2}
            y2={edge.y2}
            stroke="var(--graph-edge)"
            strokeWidth="1.5"
            strokeLinecap="round"
          />
        ))}
        {layout.nodes.map((node) => (
          <g key={node.nk}>
            <circle cx={node.x} cy={node.y} r="8" fill="var(--surface)" stroke="var(--border-strong)" strokeWidth="1" />
            <text x={node.x} y={node.y + 20} textAnchor="middle" fontSize="10" fill="var(--foreground-muted)">
              {node.title.slice(0, 10)}
            </text>
          </g>
        ))}
      </svg>
      <Link
        href={`/graph?node=${encodeURIComponent(nk)}`}
        className="absolute inset-0 flex items-center justify-center bg-background/70 text-sm font-medium text-accent opacity-0 transition-opacity group-hover:opacity-100"
      >
        ग्राफ में खोलें
      </Link>
    </div>
  );
}
