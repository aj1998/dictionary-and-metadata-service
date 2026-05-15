'use client';

import { useEffect, useRef } from 'react';
import {
  forceSimulation,
  forceLink,
  forceManyBody,
  forceCenter,
  forceCollide,
  forceX,
  forceY,
  type SimulationNodeDatum,
  type SimulationLinkDatum,
} from 'd3-force';

// ─── Card geometry constants ───────────────────────────────────────────────────

const CARD_W = 220;
const CARD_H = 88; // approximate rendered height used for anchor / collide calc
const CARD_HALF_W = CARD_W / 2;
const CARD_HALF_H = CARD_H / 2;
const CONTROL_OFFSET = 80;

// ─── Force tuning constants (exported for tests) ──────────────────────────────

export const LINK_DISTANCE   = 140;
export const CHARGE_STRENGTH = -500;
/** Per-node gravity toward canvas centre — keeps disconnected nodes visible. */
export const GRAVITY_STRENGTH = 0.07;

// ─── Bézier helpers (exported for testing) ────────────────────────────────────

type Side = 'top' | 'right' | 'bottom' | 'left';

function anchorSide(x1: number, y1: number, x2: number, y2: number): Side {
  const dx = x2 - x1;
  const dy = y2 - y1;
  if (Math.abs(dx) >= Math.abs(dy)) return dx >= 0 ? 'right' : 'left';
  return dy >= 0 ? 'bottom' : 'top';
}

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

export interface BezierResult {
  d: string;
  a1: { x: number; y: number };
  a2: { x: number; y: number };
  mid: { x: number; y: number };
  /** Tangent angle (degrees), clamped to [−20, +20]. */
  angle: number;
}

/**
 * Compute a cubic Bézier path between two node centres.
 * Anchor points are on the nearest card side; control points are
 * 80 px outward along each side's normal (per §4.4 of the spec).
 * Exported for unit tests.
 */
export function buildBezierPath(
  sx: number, sy: number,
  dx: number, dy: number,
): BezierResult {
  const ss = anchorSide(sx, sy, dx, dy);
  const ds = anchorSide(dx, dy, sx, sy);
  const a1 = anchorPt(sx, sy, ss);
  const a2 = anchorPt(dx, dy, ds);
  const c1 = controlPt(a1.x, a1.y, ss);
  const c2 = controlPt(a2.x, a2.y, ds);

  // Mid-point at t = 0.5
  const mid = {
    x: 0.125 * a1.x + 0.375 * c1.x + 0.375 * c2.x + 0.125 * a2.x,
    y: 0.125 * a1.y + 0.375 * c1.y + 0.375 * c2.y + 0.125 * a2.y,
  };

  // Tangent at t = 0.5
  const tx = 0.75 * (c1.x - a1.x) + 1.5 * (c2.x - c1.x) + 0.75 * (a2.x - c2.x);
  const ty = 0.75 * (c1.y - a1.y) + 1.5 * (c2.y - c1.y) + 0.75 * (a2.y - c2.y);
  const rawAngle = Math.atan2(ty, tx) * 180 / Math.PI;
  const angle = Math.max(-20, Math.min(20, rawAngle));

  return {
    d: `M ${a1.x} ${a1.y} C ${c1.x} ${c1.y} ${c2.x} ${c2.y} ${a2.x} ${a2.y}`,
    a1,
    a2,
    mid,
    angle,
  };
}

// ─── D3 internal types ────────────────────────────────────────────────────────

interface D3Node extends SimulationNodeDatum {
  nk: string;
}

interface D3Link extends SimulationLinkDatum<D3Node> {
  edgeId: string;
  srcNk: string;
  dstNk: string;
}

// ─── Public API ───────────────────────────────────────────────────────────────

export interface SimNodeInput {
  nk: string;
  x?: number;
  y?: number;
  fx?: number | null;
  fy?: number | null;
}

export interface SimEdgeInput {
  id: string;
  src: string;
  dst: string;
}

/** DOM element handles for a single edge group. */
export interface EdgeEl {
  path: SVGPathElement;
  c1: SVGCircleElement;
  c2: SVGCircleElement;
  labelFo: SVGForeignObjectElement;
}

/**
 * D3 force-simulation hook.
 *
 * Updates node `<foreignObject>` positions and edge `<path>` / circle / label
 * attributes **directly via DOM refs** on every simulation tick — no React
 * state updates during the animation loop.
 *
 * Consumers must call `registerNode` / `registerEdge` from ref callbacks on
 * the matching SVG elements, then call `restart` with the initial node/edge
 * arrays to seed the simulation.
 */
export function useForceSimulation(canvasW: number, canvasH: number) {
  const nodeElsRef = useRef(new Map<string, SVGForeignObjectElement>());
  const edgeElsRef = useRef(new Map<string, EdgeEl>());
  const linksRef   = useRef<D3Link[]>([]);

  // Stable function refs so callers never break memo boundaries
  const registerNode = useRef((nk: string, fo: SVGForeignObjectElement | null) => {
    if (fo) nodeElsRef.current.set(nk, fo);
    else nodeElsRef.current.delete(nk);
  }).current;

  const registerEdge = useRef((id: string, els: EdgeEl | null) => {
    if (els) edgeElsRef.current.set(id, els);
    else edgeElsRef.current.delete(id);
  }).current;

  const simRef = useRef<ReturnType<typeof forceSimulation<D3Node, D3Link>> | null>(null);

  // Create simulation once — canvas size handled by the effect below.
  useEffect(() => {
    const halfDiag = Math.sqrt(CARD_W ** 2 + CARD_H ** 2) / 2;

    const sim = forceSimulation<D3Node, D3Link>()
      .force('link',    forceLink<D3Node, D3Link>().distance(LINK_DISTANCE).strength(0.7))
      .force('charge',  forceManyBody<D3Node>().strength(CHARGE_STRENGTH))
      .force('center',  forceCenter(canvasW / 2, canvasH / 2))
      .force('x',       forceX<D3Node>(canvasW / 2).strength(GRAVITY_STRENGTH))
      .force('y',       forceY<D3Node>(canvasH / 2).strength(GRAVITY_STRENGTH))
      .force('collide', forceCollide<D3Node>(halfDiag + 8))
      .stop()
      .on('tick', () => {
        const nodes = sim.nodes();
        const nodeMap = new Map(nodes.map(n => [n.nk, n]));

        // Update node foreignObject positions
        for (const n of nodes) {
          const fo = nodeElsRef.current.get(n.nk);
          if (fo && n.x != null && n.y != null) {
            fo.setAttribute('x', String(Math.round(n.x - CARD_HALF_W)));
            fo.setAttribute('y', String(Math.round(n.y - CARD_HALF_H)));
          }
        }

        // Update edge paths, circles, and label foreignObjects
        for (const link of linksRef.current) {
          const el = edgeElsRef.current.get(link.edgeId);
          if (!el) continue;
          const src = nodeMap.get(link.srcNk);
          const dst = nodeMap.get(link.dstNk);
          if (
            !src || !dst ||
            src.x == null || src.y == null ||
            dst.x == null || dst.y == null
          ) continue;

          const bp = buildBezierPath(src.x, src.y, dst.x, dst.y);
          el.path.setAttribute('d', bp.d);
          el.c1.setAttribute('cx', String(Math.round(bp.a1.x)));
          el.c1.setAttribute('cy', String(Math.round(bp.a1.y)));
          el.c2.setAttribute('cx', String(Math.round(bp.a2.x)));
          el.c2.setAttribute('cy', String(Math.round(bp.a2.y)));
          el.labelFo.setAttribute('x', String(Math.round(bp.mid.x - 40)));
          el.labelFo.setAttribute('y', String(Math.round(bp.mid.y - 12)));
          if (Math.abs(bp.angle) > 0.5) {
            el.labelFo.setAttribute(
              'transform',
              `rotate(${bp.angle.toFixed(1)},${Math.round(bp.mid.x)},${Math.round(bp.mid.y)})`,
            );
          } else {
            el.labelFo.removeAttribute('transform');
          }
        }
      });

    simRef.current = sim;
    return () => {
      sim.stop();
      simRef.current = null;
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); // intentionally run once; canvas size is handled by the effect below

  // When the canvas is resized (e.g. DetailsPanel opens), nudge all positioning
  // forces without tearing down or restarting the simulation.
  useEffect(() => {
    const sim = simRef.current;
    if (!sim) return;
    const cx = canvasW / 2;
    const cy = canvasH / 2;
    (sim.force('center') as ReturnType<typeof forceCenter> | null)?.x(cx).y(cy);
    (sim.force('x') as ReturnType<typeof forceX> | null)?.x(cx);
    (sim.force('y') as ReturnType<typeof forceY> | null)?.y(cy);
  }, [canvasW, canvasH]);

  const restart = useRef((nodes: SimNodeInput[], edges: SimEdgeInput[]) => {
    const sim = simRef.current;
    if (!sim) return;

    const d3Nodes: D3Node[] = nodes.map(n => ({
      nk: n.nk,
      x:  n.x,
      y:  n.y,
      fx: n.fx ?? null,
      fy: n.fy ?? null,
    }));

    const nkToNode = new Map(d3Nodes.map(n => [n.nk, n]));
    const links: D3Link[] = edges.flatMap(e => {
      const src = nkToNode.get(e.src);
      const dst = nkToNode.get(e.dst);
      if (!src || !dst) return [];
      return [{
        source: src as D3Node,
        target: dst as D3Node,
        edgeId: e.id,
        srcNk:  e.src,
        dstNk:  e.dst,
      }];
    });

    linksRef.current = links;
    sim.nodes(d3Nodes);
    (sim.force('link') as ReturnType<typeof forceLink<D3Node, D3Link>>).links(links);
    sim.alpha(0.3).restart();
  }).current;

  return { registerNode, registerEdge, restart };
}
