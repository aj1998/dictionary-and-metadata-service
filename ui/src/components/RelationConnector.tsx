import { cn } from '@/lib/utils';
import type { EdgeKind } from '@/lib/types';

export const EDGE_LABELS: Record<EdgeKind, string> = {
  HAS_TOPIC:           'विषय',
  MENTIONS_KEYWORD:    'कीवर्ड',
  MENTIONS_TOPIC:      'विषय उल्लेख',
  IS_A:                'है का प्रकार',
  PART_OF:             'भाग',
  RELATED_TO:          'संबंधित',
  ALIAS_OF:            'पर्याय',
  IN_SHASTRA:          'शास्त्र में',
  IN_TEEKA:            'टीका में',
  IN_PUBLICATION:      'प्रकाशन',
  CONTAINS_DEFINITION: 'परिभाषा',
};

export const EDGE_TOOLTIPS: Record<EdgeKind, string> = {
  HAS_TOPIC:           'Has topic',
  MENTIONS_KEYWORD:    'Mentions keyword',
  MENTIONS_TOPIC:      'Mentions topic',
  IS_A:                'Is a',
  PART_OF:             'Part of',
  RELATED_TO:          'Related to',
  ALIAS_OF:            'Alias of',
  IN_SHASTRA:          'In shastra',
  IN_TEEKA:            'In teeka',
  IN_PUBLICATION:      'In publication',
  CONTAINS_DEFINITION: 'Contains definition',
};

type Side = 'top' | 'right' | 'bottom' | 'left';

const CARD_HALF_W = 110; // 220 / 2
const CARD_HALF_H = 44;  // approximate half-height
const CONTROL_OFFSET = 80;

function anchorPt(cx: number, cy: number, side: Side) {
  switch (side) {
    case 'top':    return { x: cx,            y: cy - CARD_HALF_H };
    case 'bottom': return { x: cx,            y: cy + CARD_HALF_H };
    case 'left':   return { x: cx - CARD_HALF_W, y: cy            };
    case 'right':  return { x: cx + CARD_HALF_W, y: cy            };
  }
}

function controlPt(ax: number, ay: number, side: Side) {
  switch (side) {
    case 'top':    return { x: ax,                   y: ay - CONTROL_OFFSET };
    case 'bottom': return { x: ax,                   y: ay + CONTROL_OFFSET };
    case 'left':   return { x: ax - CONTROL_OFFSET,  y: ay                  };
    case 'right':  return { x: ax + CONTROL_OFFSET,  y: ay                  };
  }
}

/** Cubic Bézier mid-point at t = 0.5 */
function bezierMid(
  a1: { x: number; y: number },
  c1: { x: number; y: number },
  c2: { x: number; y: number },
  a2: { x: number; y: number },
) {
  return {
    x: 0.125 * a1.x + 0.375 * c1.x + 0.375 * c2.x + 0.125 * a2.x,
    y: 0.125 * a1.y + 0.375 * c1.y + 0.375 * c2.y + 0.125 * a2.y,
  };
}

/** Tangent direction at t = 0.5 (unnormalised) */
function bezierTangent(
  a1: { x: number; y: number },
  c1: { x: number; y: number },
  c2: { x: number; y: number },
  a2: { x: number; y: number },
) {
  return {
    x: 0.75 * (c1.x - a1.x) + 1.5 * (c2.x - c1.x) + 0.75 * (a2.x - c2.x),
    y: 0.75 * (c1.y - a1.y) + 1.5 * (c2.y - c1.y) + 0.75 * (a2.y - c2.y),
  };
}

export interface RelationConnectorProps {
  from: { x: number; y: number; side: Side };
  to:   { x: number; y: number; side: Side };
  kind: EdgeKind;
  active?: boolean;
  onClick?(): void;
  className?: string;
}

/**
 * Static SVG relation connector. Used for previews and the /dev gallery.
 * Inside GraphCanvas the force-simulation hook writes SVG attributes directly
 * to the raw elements, bypassing this component.
 */
export function RelationConnector({
  from,
  to,
  kind,
  active = false,
  onClick,
  className,
}: RelationConnectorProps) {
  const a1 = anchorPt(from.x, from.y, from.side);
  const c1 = controlPt(a1.x, a1.y, from.side);
  const a2 = anchorPt(to.x, to.y, to.side);
  const c2 = controlPt(a2.x, a2.y, to.side);
  const mid = bezierMid(a1, c1, c2, a2);
  const tang = bezierTangent(a1, c1, c2, a2);

  const rawAngle = Math.atan2(tang.y, tang.x) * 180 / Math.PI;
  const angle = Math.max(-20, Math.min(20, rawAngle));

  const stroke = active ? 'var(--accent)' : 'var(--graph-edge-muted)';
  const d = `M ${a1.x} ${a1.y} C ${c1.x} ${c1.y} ${c2.x} ${c2.y} ${a2.x} ${a2.y}`;
  const label = EDGE_LABELS[kind];

  return (
    <g
      className={cn('cursor-pointer', className)}
      onClick={onClick}
      aria-label={`${EDGE_TOOLTIPS[kind]} relation`}
      role="button"
    >
      {/* Bézier path */}
      <path d={d} stroke={stroke} strokeWidth={1.5} strokeLinecap="round" fill="none" />

      {/* Endpoint circles */}
      <circle cx={a1.x} cy={a1.y} r={3} fill={stroke} />
      <circle cx={a2.x} cy={a2.y} r={3} fill={stroke} />

      {/* Midpoint pill label */}
      <foreignObject
        x={mid.x - 40}
        y={mid.y - 12}
        width={80}
        height={24}
        transform={`rotate(${angle.toFixed(1)}, ${mid.x}, ${mid.y})`}
      >
        <div
          className={cn(
            'inline-flex h-full w-full items-center justify-center',
            'rounded-[var(--radius-pill)] border border-border bg-surface',
            'text-[length:var(--font-size-xs)] font-medium text-foreground-muted',
            active && 'border-accent',
          )}
          style={{ opacity: active ? 1 : 0.5 }}
          title={EDGE_TOOLTIPS[kind]}
        >
          {label}
        </div>
      </foreignObject>
    </g>
  );
}
