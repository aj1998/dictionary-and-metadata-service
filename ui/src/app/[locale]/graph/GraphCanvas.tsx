'use client';

import {
  useRef,
  useState,
  useEffect,
  useCallback,
  memo,
  type RefCallback,
} from 'react';
import { NodeCard, resolveNodeTitle } from '@/components/NodeCard';
import { EDGE_LABELS } from '@/components/RelationConnector';
import { ZoomControls } from './ZoomControls';
import {
  useForceSimulation,
  type SimNodeInput,
  type SimEdgeInput,
  type EdgeEl,
} from './useForceSimulation';
import { cn } from '@/lib/utils';
import {
  computeHierarchicalPositions,
  computeRadialPositions,
  resolveHierRowCollisions,
  resolveRadialDiscCollisions,
  RADIAL_MIN_ARC,
  HIER_LEVEL_HEIGHT,
  HIER_NODE_SPACING,
} from './graphViewHelpers';
import type { EntityKind, EdgeKind } from '@/lib/types';
import { useGraphStore } from '@/lib/store/graphStore';

// ─── Constants ────────────────────────────────────────────────────────────────

const CARD_W = 220;
const CARD_H = 88;

// Radial incremental-expansion constant (Neo4j-style)
const RADIAL_FAN_RADIUS = 280;  // base radius for new-child fan around the expander
const MIN_ZOOM = 0.4;
const MAX_ZOOM = 2.5;
const FIT_DURATION_MS = 600;
// Maximum pointer displacement (px) that is treated as a click rather than a drag.
export const CANVAS_CLICK_THRESHOLD_PX = 5;

// ─── Types ────────────────────────────────────────────────────────────────────

export interface CanvasNode extends SimNodeInput {
  kind: EntityKind;
  titleHi: string;
  titleEn?: string;
  selected?: boolean;
  faded?: boolean;
  pinned?: boolean;
  expanded?: boolean;
}

export interface CanvasEdge extends SimEdgeInput {
  kind: EdgeKind;
  active?: boolean;
}

interface Camera { x: number; y: number; k: number }

// ─── Edge pill label (rendered inside foreignObject) ─────────────────────────

function EdgePill({
  kind,
  active,
}: {
  kind: EdgeKind;
  active?: boolean;
}) {
  return (
    <div
      style={{ opacity: active ? 1 : 0.5 }}
      className={cn(
        'inline-flex h-full w-full items-center justify-center',
        'rounded-[var(--radius-pill)] border bg-surface',
        'text-[length:var(--font-size-xs)] font-medium text-foreground-muted',
        active ? 'border-accent' : 'border-border',
      )}
    >
      {EDGE_LABELS[kind] ?? kind}
    </div>
  );
}

// ─── EdgesAndNodes — memoised so camera state changes don't re-render it ──────
//
// The force-simulation hook updates foreignObject / path attributes directly on
// every tick.  If GraphCanvas re-rendered this subtree on every camera change,
// React would write back the initial JSX x/y values and overwrite the sim's
// work.  The memo boundary prevents that: React only reconciles this subtree
// when `nodes` or `edges` identity changes (i.e. a new set arrives).

interface EdgesAndNodesProps {
  nodes: CanvasNode[];
  edges: CanvasEdge[];
  registerNode: (nk: string, fo: SVGForeignObjectElement | null) => void;
  accumulateEdgeRef: (id: string, part: keyof EdgeEl, el: SVGElement | null) => void;
  onNodeClick?: (nk: string) => void;
  onNodeDoubleClick?: (nk: string) => void;
  onNodePinToggle?: (nk: string) => void;
  onNodeExpand?: (nk: string) => void;
  onEdgeClick?: (id: string) => void;
  onNodePointerDown?: (nk: string, e: React.PointerEvent) => void;
}

const EdgesAndNodes = memo(function EdgesAndNodes({
  nodes,
  edges,
  registerNode,
  accumulateEdgeRef,
  onNodeClick,
  onNodeDoubleClick,
  onNodePinToggle,
  onNodeExpand,
  onEdgeClick,
  onNodePointerDown,
}: EdgesAndNodesProps) {
  return (
    <>
      {/* ── Edges layer (rendered below nodes) ── */}
      <g className="edges">
        {edges.map(edge => {
          const stroke = edge.active ? 'var(--accent)' : 'var(--graph-edge)';

          // Typed ref callbacks for each SVG element in the group
          const pathRef: RefCallback<SVGPathElement> = el =>
            accumulateEdgeRef(edge.id, 'path', el);
          const c1Ref: RefCallback<SVGCircleElement> = el =>
            accumulateEdgeRef(edge.id, 'c1', el);
          const c2Ref: RefCallback<SVGCircleElement> = el =>
            accumulateEdgeRef(edge.id, 'c2', el);
          const labelRef: RefCallback<SVGForeignObjectElement> = el =>
            accumulateEdgeRef(edge.id, 'labelFo', el);

          return (
            <g key={edge.id} className="graph-edge cursor-pointer" onClick={() => onEdgeClick?.(edge.id)}>
              <path
                ref={pathRef}
                stroke={stroke}
                strokeWidth={1.5}
                strokeLinecap="round"
                fill="none"
              />
              <circle ref={c1Ref} r={3} fill={stroke} />
              <circle ref={c2Ref} r={3} fill={stroke} />
              <foreignObject ref={labelRef} width={80} height={24}>
                <EdgePill kind={edge.kind} active={edge.active} />
              </foreignObject>
            </g>
          );
        })}
      </g>

      {/* ── Nodes layer (rendered above edges) ── */}
      <g className="nodes">
        {nodes.map(node => (
          <foreignObject
            key={node.nk}
            ref={fo => registerNode(node.nk, fo)}
            x={0}
            y={0}
            width={CARD_W}
            height={CARD_H}
            className="graph-node overflow-visible"
            style={{ cursor: 'grab' }}
            onPointerDown={e => onNodePointerDown?.(node.nk, e)}
          >
            <NodeCard
              id={node.nk}
              kind={node.kind}
              titleHi={resolveNodeTitle(node.nk, node.kind, node.titleHi)}
              titleEn={node.titleEn}
              selected={node.selected}
              faded={node.faded}
              pinned={node.pinned}
              expanded={node.expanded}
              onClick={() => onNodeClick?.(node.nk)}
              onDoubleClick={() => onNodeDoubleClick?.(node.nk)}
              onPinToggle={() => onNodePinToggle?.(node.nk)}
              onExpand={() => onNodeExpand?.(node.nk)}
            />
          </foreignObject>
        ))}
      </g>
    </>
  );
});

// ─── GraphCanvas ──────────────────────────────────────────────────────────────

interface GraphCanvasProps {
  nodes: CanvasNode[];
  edges: CanvasEdge[];
  layout?: 'force' | 'radial' | 'hierarchical';
  /** BFS root for hierarchical mode. Falls back to first node when null. */
  focusNk?: string | null;
  onNodeClick?(nk: string): void;
  onNodeDoubleClick?(nk: string): void;
  onNodePinToggle?(nk: string): void;
  onNodeExpand?(nk: string): void;
  onEdgeClick?(id: string): void;
  onCanvasClick?(): void;
  className?: string;
}

export function GraphCanvas({
  nodes,
  edges,
  layout = 'force',
  focusNk,
  onNodeClick,
  onNodeDoubleClick,
  onNodePinToggle,
  onNodeExpand,
  onEdgeClick,
  onCanvasClick,
  className,
}: GraphCanvasProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const svgRef       = useRef<SVGSVGElement>(null);

  const [camera, setCamera] = useState<Camera>({ x: 0, y: 0, k: 1 });
  const [canvasSize, setCanvasSize] = useState({ w: 800, h: 600 });
  const [isDragging, setIsDragging] = useState(false);

  const lastPosRef      = useRef({ x: 0, y: 0 });
  // Tracks the mousedown position so we can distinguish a click from a drag.
  const mouseDownPosRef = useRef({ x: 0, y: 0 });
  const cameraRef    = useRef(camera);
  cameraRef.current  = camera;
  const canvasSizeRef = useRef(canvasSize);
  canvasSizeRef.current = canvasSize;
  // Keep a stable ref to focusNk so the restart effect doesn't re-fire on
  // every node selection — hierarchical positions are recomputed only when
  // the node set or layout changes.
  const focusNkRef = useRef(focusNk ?? null);
  focusNkRef.current = focusNk ?? null;

  // Tracks which node triggered an expansion so the radial branch can do
  // incremental positioning instead of a full re-layout.
  const expanderNkRef = useRef<string | null>(null);
  // Stores the last committed canvas positions so incremental expansions can
  // pin existing nodes and only place newly added ones. Seeded from the
  // zustand store on mount so positions survive page navigation away/back.
  const storePositions = useGraphStore.getState().positions;
  const setStorePositions = useGraphStore.getState().setPositions;
  const lastPositionsRef = useRef<Map<string, { x: number; y: number }>>(
    new Map(Object.entries(storePositions)),
  );
  // Snapshots of committed positions keyed by the node that triggered the
  // expansion — used to restore the previous radial layout when that node is
  // collapsed again.
  const expandSnapshotsRef = useRef<Map<string, Map<string, { x: number; y: number }>>>(new Map());
  // Stable layout ref so the expand handler doesn't capture a stale closure.
  const layoutRef = useRef(layout);
  layoutRef.current = layout;

  // Measure canvas on mount / resize
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const ro = new ResizeObserver(([entry]) => {
      const { width, height } = entry.contentRect;
      if (width > 0 && height > 0) setCanvasSize({ w: width, h: height });
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // Force simulation (direct DOM updates, no React re-renders per tick)
  const { registerNode, registerEdge, restart, getSimNode, kickSim } = useForceSimulation(
    canvasSize.w,
    canvasSize.h,
  );

  // Accumulate the 4 sub-element refs for each edge then register as a unit
  const edgeElAccumRef = useRef(new Map<string, Partial<EdgeEl>>());

  const accumulateEdgeRef = useCallback(
    (id: string, part: keyof EdgeEl, el: SVGElement | null) => {
      const map = edgeElAccumRef.current;
      if (!el) {
        // One part unmounted → deregister the whole edge
        map.delete(id);
        registerEdge(id, null);
        return;
      }
      if (!map.has(id)) map.set(id, {});
      const parts = map.get(id)!;
      (parts as Record<string, unknown>)[part] = el;
      const { path, c1, c2, labelFo } = parts;
      if (path && c1 && c2 && labelFo) {
        registerEdge(id, { path, c1, c2, labelFo } as EdgeEl);
      }
    },
    // registerEdge is a stable ref — no deps needed
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [],
  );

  // Seed / restart simulation when the node set or layout changes.
  // canvasSizeRef and focusNkRef are read via refs so this effect doesn't
  // re-fire on resize or node selection, which would reset positions.
  useEffect(() => {
    const { w, h } = canvasSizeRef.current;
    if (w === 0 || nodes.length === 0) return;

    const simEdges: SimEdgeInput[] = edges.map(e => ({
      id:  e.id,
      src: e.src,
      dst: e.dst,
    }));

    if (layout === 'hierarchical') {
      const expanderNk = expanderNkRef.current;
      expanderNkRef.current = null;

      const prevPos = lastPositionsRef.current;
      const newNks = nodes.filter(n => !prevPos.has(n.nk));
      const existingCount = nodes.length - newNks.length;
      const expanderPos = expanderNk ? prevPos.get(expanderNk) : undefined;

      // Collapse: same toggle, no new nodes, total count dropped, snapshot exists.
      const isCollapse =
        !!expanderNk &&
        newNks.length === 0 &&
        nodes.length < prevPos.size &&
        expandSnapshotsRef.current.has(expanderNk);

      // Incremental expand: expander has a known position, existing nodes remain,
      // and new children arrived. Keep everything in place; drop children below.
      const canIncremental =
        !!expanderPos &&
        existingCount > 0 &&
        newNks.length > 0;

      let simNodes: SimNodeInput[];

      if (isCollapse) {
        const snapshot = expandSnapshotsRef.current.get(expanderNk!)!;
        expandSnapshotsRef.current.delete(expanderNk!);
        simNodes = nodes.map(node => {
          const pos = snapshot.get(node.nk) ?? prevPos.get(node.nk);
          const x = pos?.x ?? w / 2;
          const y = pos?.y ?? h / 2;
          return { nk: node.nk, x, y, fx: x, fy: y };
        });
      } else if (newNks.length === 0 && nodes.length < prevPos.size) {
        // Pure collapse without a snapshot (e.g. the original expand happened
        // before any incremental layout ran). Just keep the surviving nodes
        // exactly where they are instead of running a full re-layout — that
        // would scatter them into disconnected components.
        simNodes = nodes.map(node => {
          const existing = prevPos.get(node.nk);
          const x = existing?.x ?? w / 2;
          const y = existing?.y ?? h / 2;
          return { nk: node.nk, x, y, fx: x, fy: y };
        });
      } else if (canIncremental && expanderPos) {
        // Snapshot pre-expand layout so a later collapse can restore it.
        expandSnapshotsRef.current.set(expanderNk!, new Map(prevPos));

        const n = newNks.length;
        const childY = expanderPos.y + HIER_LEVEL_HEIGHT;
        // Centre the children row under the expander.
        const rowWidth = (n - 1) * HIER_NODE_SPACING;
        const startX = expanderPos.x - rowWidth / 2;

        // Detect existing nodes on the same row as the new children's band
        // and shift them outward so the new children don't overlap them.
        const yTolerance = HIER_LEVEL_HEIGHT / 2;
        const sameRowExisting: Array<{ nk: string; x: number }> = [];
        for (const [nk, pos] of prevPos.entries()) {
          if (nk === expanderNk) continue;
          if (Math.abs(pos.y - childY) < yTolerance) {
            sameRowExisting.push({ nk, x: pos.x });
          }
        }
        const shifts = resolveHierRowCollisions(
          sameRowExisting,
          startX,
          startX + rowWidth,
          expanderPos.x,
        );

        simNodes = nodes.map(node => {
          if (node.nk === expanderNk) {
            return { nk: node.nk, x: expanderPos.x, y: expanderPos.y, fx: expanderPos.x, fy: expanderPos.y };
          }
          const existing = prevPos.get(node.nk);
          if (existing) {
            const shiftedX = shifts.get(node.nk);
            const x = shiftedX ?? existing.x;
            return { nk: node.nk, x, y: existing.y, fx: x, fy: existing.y };
          }
          const idx = newNks.findIndex(nn => nn.nk === node.nk);
          const x = startX + idx * HIER_NODE_SPACING;
          const y = childY;
          return { nk: node.nk, x, y, fx: x, fy: y };
        });
      } else if (existingCount > 0 && newNks.length > 0) {
        // External addition (e.g. user navigated to a different node via the
        // dictionary). No expander to anchor against, so freeze existing nodes
        // and lay out the new subtree as its own BFS tree beside them.
        const newNkSet = new Set(newNks.map(n => n.nk));
        const subEdges = simEdges.filter(e => newNkSet.has(e.src) && newNkSet.has(e.dst));
        const subFocus = focusNkRef.current && newNkSet.has(focusNkRef.current) ? focusNkRef.current : newNks[0].nk;
        const subPositions = computeHierarchicalPositions(
          newNks.map(n => n.nk), subEdges, subFocus, w, h,
        );
        // Compute the existing tree's bounding box so we can drop the new
        // subtree just to the right of it (and aligned at the same top row).
        let exMinX = Infinity, exMaxX = -Infinity, exMinY = Infinity;
        for (const p of prevPos.values()) {
          if (p.x < exMinX) exMinX = p.x;
          if (p.x > exMaxX) exMaxX = p.x;
          if (p.y < exMinY) exMinY = p.y;
        }
        // Sub-layout's own bbox (computed positions are centred on w/2).
        let subMinX = Infinity, subMaxX = -Infinity, subMinY = Infinity;
        for (const p of subPositions.values()) {
          if (p.x < subMinX) subMinX = p.x;
          if (p.x > subMaxX) subMaxX = p.x;
          if (p.y < subMinY) subMinY = p.y;
        }
        const xOffset = (exMaxX + HIER_NODE_SPACING) - subMinX;
        const yOffset = exMinY - subMinY;
        simNodes = nodes.map(node => {
          const existing = prevPos.get(node.nk);
          if (existing) {
            return { nk: node.nk, x: existing.x, y: existing.y, fx: existing.x, fy: existing.y };
          }
          const pos = subPositions.get(node.nk);
          const x = (pos?.x ?? w / 2) + xOffset;
          const y = (pos?.y ?? h / 2) + yOffset;
          return { nk: node.nk, x, y, fx: x, fy: y };
        });
      } else {
        // Full BFS layout: first load, reset, layout switch.
        lastPositionsRef.current = new Map();
        const positions = computeHierarchicalPositions(nodes.map(n => n.nk), simEdges, focusNkRef.current, w, h);
        simNodes = nodes.map(n => {
          const pos = positions.get(n.nk);
          const x = pos?.x ?? w / 2;
          const y = pos?.y ?? h / 2;
          return { nk: n.nk, x, y, fx: x, fy: y };
        });
      }

      // Commit positions for the next incremental step.
      const committed = new Map<string, { x: number; y: number }>();
      for (const sn of simNodes) committed.set(sn.nk, { x: sn.x ?? w / 2, y: sn.y ?? h / 2 });
      lastPositionsRef.current = committed;
      // Mirror into the store so positions survive GraphCanvas remounts
      // (e.g. after the user navigates to /dictionary and back).
      setStorePositions(Object.fromEntries(committed));

      restart(simNodes, simEdges, 'static');

    } else if (layout === 'radial') {
      const expanderNk = expanderNkRef.current;
      expanderNkRef.current = null;

      const prevPos = lastPositionsRef.current;
      const newNks = nodes.filter(n => !prevPos.has(n.nk));
      const existingCount = nodes.length - newNks.length;

      let simNodes: SimNodeInput[];

      // Incremental path: expander was clicked, it has a prior position, and
      // it is NOT at the canvas centre (expanding the focus node falls through
      // to BFS which correctly places new ring-1 siblings without overlap).
      const expanderPos = expanderNk ? prevPos.get(expanderNk) : undefined;
      const focusPos = focusNkRef.current
        ? (prevPos.get(focusNkRef.current) ?? { x: w / 2, y: h / 2 })
        : { x: w / 2, y: h / 2 };
      const edx = expanderPos ? expanderPos.x - focusPos.x : 0;
      const edy = expanderPos ? expanderPos.y - focusPos.y : 0;
      const expanderDist = Math.sqrt(edx * edx + edy * edy);

      const canIncremental =
        !!expanderPos &&
        existingCount > 0 &&
        newNks.length > 0 &&
        expanderDist >= 1; // centre-node expansion → BFS handles it cleanly

      // Detect a collapse: same expander toggle was pressed but no new nodes
      // arrived and at least one previously committed node is now gone. In
      // that case, restore the snapshot we took right before this node was
      // expanded so the user gets their original radial view back.
      const isCollapse =
        !!expanderNk &&
        newNks.length === 0 &&
        nodes.length < prevPos.size &&
        expandSnapshotsRef.current.has(expanderNk);

      if (isCollapse) {
        const snapshot = expandSnapshotsRef.current.get(expanderNk)!;
        expandSnapshotsRef.current.delete(expanderNk);
        simNodes = nodes.map(node => {
          const pos = snapshot.get(node.nk) ?? prevPos.get(node.nk);
          const x = pos?.x ?? w / 2;
          const y = pos?.y ?? h / 2;
          return { nk: node.nk, x, y, fx: x, fy: y };
        });
      } else if (newNks.length === 0 && nodes.length < prevPos.size) {
        // Pure collapse without a snapshot — preserve surviving positions
        // rather than running a full re-layout that would scatter them.
        simNodes = nodes.map(node => {
          const existing = prevPos.get(node.nk);
          const x = existing?.x ?? w / 2;
          const y = existing?.y ?? h / 2;
          return { nk: node.nk, x, y, fx: x, fy: y };
        });
      } else if (canIncremental && expanderPos) {
        // Save a snapshot of the current layout BEFORE we mutate it so that a
        // later collapse of this same expander can restore the original view.
        expandSnapshotsRef.current.set(expanderNk!, new Map(prevPos));

        // ── Incremental (Neo4j-style): push the expander outward, then place its
        // children in a full circle around its new position. ─
        const awayAngle = Math.atan2(edy, edx);
        const n = newNks.length;
        // Children ring radius: large enough to keep adjacent cards apart
        // (arc length ≥ RADIAL_MIN_ARC) using the full 360°.
        const fanAngle = 2 * Math.PI;
        const fanR = Math.max(RADIAL_FAN_RADIUS, (n * RADIAL_MIN_ARC) / fanAngle);
        const dTheta = n > 0 ? fanAngle / n : 0;
        // Push the expander outward by the child ring radius + a small gap so
        // the children's circle clears the focus side and doesn't overlap it.
        const pushOut = fanR + RADIAL_FAN_RADIUS * 0.4;
        const newExpanderPos = {
          x: expanderPos.x + Math.cos(awayAngle) * pushOut,
          y: expanderPos.y + Math.sin(awayAngle) * pushOut,
        };

        // Push any existing node sitting inside the new fan disc outward
        // (preserving its angle relative to the new expander position) so the
        // children's circle doesn't collide with previously placed nodes.
        const discR = fanR + CARD_W * 0.5;
        const clearance = CARD_W * 0.3;
        const existingForDisc: Array<{ nk: string; x: number; y: number }> = [];
        for (const [nk, pos] of prevPos.entries()) {
          if (nk === expanderNk) continue;
          existingForDisc.push({ nk, x: pos.x, y: pos.y });
        }
        const radialShifts = resolveRadialDiscCollisions(
          existingForDisc,
          newExpanderPos,
          discR,
          clearance,
        );

        simNodes = nodes.map(node => {
          // Expander: moved outward, pinned at the new position
          if (node.nk === expanderNk) {
            return { nk: node.nk, x: newExpanderPos.x, y: newExpanderPos.y, fx: newExpanderPos.x, fy: newExpanderPos.y };
          }
          // Existing nodes: keep their committed positions (shifted if they
          // collided with the new fan disc).
          const existing = prevPos.get(node.nk);
          if (existing) {
            const shifted = radialShifts.get(node.nk);
            const x = shifted?.x ?? existing.x;
            const y = shifted?.y ?? existing.y;
            return { nk: node.nk, x, y, fx: x, fy: y };
          }
          // New child: place on a full circle around the expander's new position.
          // Start angle = awayAngle (12-o'clock from focus's view) so the ring is
          // centred symmetrically around the outward direction.
          const idx = newNks.findIndex(nn => nn.nk === node.nk);
          const theta = awayAngle + idx * dTheta;
          const x = newExpanderPos.x + fanR * Math.cos(theta);
          const y = newExpanderPos.y + fanR * Math.sin(theta);
          return { nk: node.nk, x, y, fx: x, fy: y };
        });
      } else {
        // ── Full BFS radial layout (first load, reset, layout switch, or centre expansion) ─
        const positions = computeRadialPositions(nodes.map(n => n.nk), simEdges, focusNkRef.current, w, h);
        simNodes = nodes.map(n => {
          const pos = positions.get(n.nk);
          const x = pos?.x ?? w / 2;
          const y = pos?.y ?? h / 2;
          return { nk: n.nk, x, y, fx: x, fy: y };
        });
      }

      // Save positions for the next incremental expansion
      const committed = new Map<string, { x: number; y: number }>();
      for (const sn of simNodes) committed.set(sn.nk, { x: sn.x ?? w / 2, y: sn.y ?? h / 2 });
      lastPositionsRef.current = committed;

      restart(simNodes, simEdges, 'static');

    } else {
      lastPositionsRef.current = new Map();
      const cx = w / 2;
      const cy = h / 2;
      const spread = 80;
      const simNodes: SimNodeInput[] = nodes.map(n => ({
        nk:  n.nk,
        x:   n.x ?? cx + (Math.random() - 0.5) * spread,
        y:   n.y ?? cy + (Math.random() - 0.5) * spread,
      }));
      restart(simNodes, simEdges);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nodes.length, layout]);

  // ── Camera helpers ───────────────────────────────────────────────────────────

  const applyZoom = useCallback(
    (deltaFactor: number, anchorX: number, anchorY: number) => {
      setCamera(prev => {
        const k = Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, prev.k * deltaFactor));
        const ratio = k / prev.k;
        return {
          x: anchorX - ratio * (anchorX - prev.x),
          y: anchorY - ratio * (anchorY - prev.y),
          k,
        };
      });
    },
    [],
  );

  const fitToContent = useCallback(() => {
    if (!svgRef.current) return;
    const rect = svgRef.current.getBoundingClientRect();
    // Animate to identity transform — Phase 5 will do a true bbox fit
    const startCam = { ...cameraRef.current };
    const endCam   = { x: 0, y: 0, k: 1 };
    const start = performance.now();
    const step = (now: number) => {
      const t = Math.min(1, (now - start) / FIT_DURATION_MS);
      const ease = t < 0.5 ? 2 * t * t : -1 + (4 - 2 * t) * t; // ease-in-out
      setCamera({
        x: startCam.x + (endCam.x - startCam.x) * ease,
        y: startCam.y + (endCam.y - startCam.y) * ease,
        k: startCam.k + (endCam.k - startCam.k) * ease,
      });
      if (t < 1) requestAnimationFrame(step);
    };
    void rect; // accessed only for side-effect check
    requestAnimationFrame(step);
  }, []);

  // Capture which node was expanded BEFORE the store mutation fires so the
  // restart effect can read it via expanderNkRef when nodes.length changes.
  const handleNodeExpand = useCallback((nk: string) => {
    if (layoutRef.current === 'radial' || layoutRef.current === 'hierarchical') {
      expanderNkRef.current = nk;
    }
    onNodeExpand?.(nk);
  }, [onNodeExpand]);

  // ── Node drag ────────────────────────────────────────────────────────────────
  //
  // Lets the user reposition any node by pressing and dragging the card.
  // While dragging we mutate the d3 node's fx/fy (pinning it under the cursor)
  // and kick the sim so the existing tick handler updates the DOM. When the
  // drag ends we commit the new position to lastPositionsRef + the zustand
  // store so it survives re-layouts and page navigation.
  const dragRef = useRef<{
    nk: string;
    startClientX: number;
    startClientY: number;
    startNodeX: number;
    startNodeY: number;
    hadFx: boolean;
    hadFy: boolean;
    moved: boolean;
  } | null>(null);
  const suppressNextClickRef = useRef(false);

  const handleNodePointerDown = useCallback((nk: string, e: React.PointerEvent) => {
    if (e.button !== 0) return;
    // Ignore drags initiated on interactive sub-controls of the card
    // (pin / expand / external-link buttons all live inside the node card).
    if ((e.target as Element).closest('button, a')) return;
    const sn = getSimNode(nk);
    if (!sn || sn.x == null || sn.y == null) return;
    dragRef.current = {
      nk,
      startClientX: e.clientX,
      startClientY: e.clientY,
      startNodeX: sn.x,
      startNodeY: sn.y,
      hadFx: sn.fx != null,
      hadFy: sn.fy != null,
      moved: false,
    };
    e.stopPropagation();
  }, [getSimNode]);

  useEffect(() => {
    const onMove = (e: PointerEvent) => {
      const drag = dragRef.current;
      if (!drag) return;
      const dx = (e.clientX - drag.startClientX) / cameraRef.current.k;
      const dy = (e.clientY - drag.startClientY) / cameraRef.current.k;
      if (!drag.moved && Math.hypot(e.clientX - drag.startClientX, e.clientY - drag.startClientY) >= CANVAS_CLICK_THRESHOLD_PX) {
        drag.moved = true;
      }
      const sn = getSimNode(drag.nk);
      if (!sn) return;
      const nx = drag.startNodeX + dx;
      const ny = drag.startNodeY + dy;
      sn.fx = nx;
      sn.fy = ny;
      sn.x = nx;
      sn.y = ny;
      kickSim();
    };
    const onUp = () => {
      const drag = dragRef.current;
      if (!drag) return;
      dragRef.current = null;
      const sn = getSimNode(drag.nk);
      if (sn && drag.moved) {
        // Persist the new position so layout-change effects and remounts
        // honor where the user dropped the card.
        const x = sn.x ?? drag.startNodeX;
        const y = sn.y ?? drag.startNodeY;
        lastPositionsRef.current.set(drag.nk, { x, y });
        setStorePositions(Object.fromEntries(lastPositionsRef.current));
        // Restore freedom if the node wasn't pinned before; otherwise keep it
        // pinned at the new spot (matches d3-drag default behaviour).
        if (!drag.hadFx) sn.fx = null;
        if (!drag.hadFy) sn.fy = null;
        suppressNextClickRef.current = true;
      }
    };
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
    return () => {
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
    };
  }, [getSimNode, kickSim, setStorePositions]);

  const handleNodeClick = useCallback((nk: string) => {
    if (suppressNextClickRef.current) {
      suppressNextClickRef.current = false;
      return;
    }
    onNodeClick?.(nk);
  }, [onNodeClick]);

  // ── Event handlers ───────────────────────────────────────────────────────────

  const handleWheel = useCallback(
    (e: React.WheelEvent) => {
      e.preventDefault();
      const rect = svgRef.current!.getBoundingClientRect();
      const factor = e.deltaY > 0 ? 0.9 : 1 / 0.9;
      applyZoom(factor, e.clientX - rect.left, e.clientY - rect.top);
    },
    [applyZoom],
  );

  const handleMouseDown = useCallback((e: React.MouseEvent<SVGSVGElement>) => {
    if ((e.target as Element).closest('.graph-node, .graph-edge')) return;
    setIsDragging(true);
    lastPosRef.current = { x: e.clientX, y: e.clientY };
    mouseDownPosRef.current = { x: e.clientX, y: e.clientY };
  }, []);

  const handleMouseMove = useCallback((e: React.MouseEvent<SVGSVGElement>) => {
    if (!isDragging) return;
    const dx = e.clientX - lastPosRef.current.x;
    const dy = e.clientY - lastPosRef.current.y;
    lastPosRef.current = { x: e.clientX, y: e.clientY };
    setCamera(prev => ({ ...prev, x: prev.x + dx, y: prev.y + dy }));
  }, [isDragging]);

  // Fire onCanvasClick only when the pointer hasn't moved significantly —
  // prevents panning the graph from closing the side panel.
  const stopDrag = useCallback((e?: React.MouseEvent<SVGSVGElement>) => {
    if (e) {
      const dx = e.clientX - mouseDownPosRef.current.x;
      const dy = e.clientY - mouseDownPosRef.current.y;
      const dist = Math.sqrt(dx * dx + dy * dy);
      if (dist < CANVAS_CLICK_THRESHOLD_PX) onCanvasClick?.();
    }
    setIsDragging(false);
  }, [onCanvasClick]);

  // ── Grid pattern ─────────────────────────────────────────────────────────────

  const tileSize = 24 * camera.k;
  // Positive-modulo offset so the grid appears to pan with the camera
  const gridOffX = ((camera.x % tileSize) + tileSize) % tileSize;
  const gridOffY = ((camera.y % tileSize) + tileSize) % tileSize;
  // Clamp dot screen radius to [0.75, 1.5] px
  const dotR = Math.max(0.75, Math.min(camera.k, 1.5));

  const transform = `translate(${camera.x.toFixed(2)},${camera.y.toFixed(2)}) scale(${camera.k.toFixed(4)})`;

  return (
    <div
      ref={containerRef}
      className={cn('relative h-full w-full overflow-hidden', className)}
    >
      <svg
        ref={svgRef}
        className="h-full w-full select-none"
        style={{ cursor: isDragging ? 'grabbing' : 'grab' }}
        onWheel={handleWheel}
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={(e) => stopDrag(e)}
        onMouseLeave={() => stopDrag()}
        aria-label="ग्राफ कैनवास"
      >
        <defs>
          {/* Dotted grid pattern (screen-space, pans / scales with camera) */}
          <pattern
            id="graph-grid-dots"
            x={0}
            y={0}
            width={tileSize}
            height={tileSize}
            patternUnits="userSpaceOnUse"
            patternTransform={`translate(${gridOffX.toFixed(2)},${gridOffY.toFixed(2)})`}
          >
            <circle cx={0} cy={0} r={dotR} fill="var(--graph-grid-dot)" />
          </pattern>
        </defs>

        {/* Background */}
        <rect width="100%" height="100%" fill="var(--background)" />

        {/* Dot grid */}
        <rect width="100%" height="100%" fill="url(#graph-grid-dots)" />

        {/* Camera group — contains edges + nodes in graph coordinates */}
        <g transform={transform}>
          <EdgesAndNodes
            nodes={nodes}
            edges={edges}
            registerNode={registerNode}
            accumulateEdgeRef={accumulateEdgeRef}
            onNodeClick={handleNodeClick}
            onNodeDoubleClick={onNodeDoubleClick}
            onNodePinToggle={onNodePinToggle}
            onNodeExpand={handleNodeExpand}
            onEdgeClick={onEdgeClick}
            onNodePointerDown={handleNodePointerDown}
          />
        </g>
      </svg>

      {/* Zoom controls — absolute-positioned in screen space */}
      <ZoomControls
        onZoomIn={() => {
          if (!svgRef.current) return;
          const { width, height } = svgRef.current.getBoundingClientRect();
          applyZoom(1 / 0.9, width / 2, height / 2);
        }}
        onZoomOut={() => {
          if (!svgRef.current) return;
          const { width, height } = svgRef.current.getBoundingClientRect();
          applyZoom(0.9, width / 2, height / 2);
        }}
        onFit={fitToContent}
      />

      {/* Empty-canvas message */}
      {nodes.length === 0 && (
        <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
          <div className="rounded-[var(--radius-md)] border border-border bg-surface px-6 py-4 text-center shadow-[var(--node-shadow)]">
            <p className="font-serif-hindi text-[length:var(--font-size-h3)] text-foreground">
              अभी कोई डेटा नहीं है
            </p>
            <p className="mt-1 text-[length:var(--font-size-sm)] text-foreground-muted">
              No graph data yet
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
