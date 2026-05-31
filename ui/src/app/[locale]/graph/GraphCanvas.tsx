'use client';

import {
  useRef,
  useState,
  useEffect,
  useCallback,
  memo,
  type RefCallback,
} from 'react';
import { NodeCard } from '@/components/NodeCard';
import { EDGE_LABELS } from '@/components/RelationConnector';
import { ZoomControls } from './ZoomControls';
import {
  useForceSimulation,
  type SimNodeInput,
  type SimEdgeInput,
  type EdgeEl,
} from './useForceSimulation';
import { cn } from '@/lib/utils';
import { computeHierarchicalPositions, computeRadialPositions, RADIAL_MIN_ARC } from './graphViewHelpers';
import type { EntityKind, EdgeKind } from '@/lib/types';

// ─── Constants ────────────────────────────────────────────────────────────────

const CARD_W = 220;
const CARD_H = 88;

// Radial incremental-expansion constant (Neo4j-style)
const RADIAL_FAN_RADIUS = 280;  // base radius for new-child fan around the expander
const MIN_ZOOM = 0.4;
const MAX_ZOOM = 2.5;
const FIT_DURATION_MS = 600;

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
          >
            <NodeCard
              id={node.nk}
              kind={node.kind}
              titleHi={node.titleHi}
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

  const lastPosRef   = useRef({ x: 0, y: 0 });
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
  // pin existing nodes and only place newly added ones.
  const lastPositionsRef = useRef<Map<string, { x: number; y: number }>>(new Map());
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
  const { registerNode, registerEdge, restart } = useForceSimulation(
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
      lastPositionsRef.current = new Map();
      const positions = computeHierarchicalPositions(nodes.map(n => n.nk), simEdges, focusNkRef.current, w, h);
      const simNodes: SimNodeInput[] = nodes.map(n => {
        const pos = positions.get(n.nk);
        const x = pos?.x ?? w / 2;
        const y = pos?.y ?? h / 2;
        return { nk: n.nk, x, y, fx: x, fy: y };
      });
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

      if (canIncremental && expanderPos) {
        // ── Incremental (Neo4j-style): expander stays put, children fan from it ─
        const awayAngle = Math.atan2(edy, edx);
        const fanAngle = Math.PI; // 180° arc facing away from focus
        const n = newNks.length;
        const fanR = Math.max(RADIAL_FAN_RADIUS, (n * RADIAL_MIN_ARC) / fanAngle);
        const dTheta = n > 1 ? fanAngle / (n - 1) : 0;

        simNodes = nodes.map(node => {
          // Expander: stays exactly where it is (pin in place)
          if (node.nk === expanderNk) {
            return { nk: node.nk, x: expanderPos.x, y: expanderPos.y, fx: expanderPos.x, fy: expanderPos.y };
          }
          // Existing nodes: keep their committed positions
          const existing = prevPos.get(node.nk);
          if (existing) {
            return { nk: node.nk, x: existing.x, y: existing.y, fx: existing.x, fy: existing.y };
          }
          // New child: fan from the expander's position outward
          const idx = newNks.findIndex(nn => nn.nk === node.nk);
          const theta = awayAngle - fanAngle / 2 + idx * dTheta;
          const x = expanderPos.x + fanR * Math.cos(theta);
          const y = expanderPos.y + fanR * Math.sin(theta);
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
    if (layoutRef.current === 'radial') {
      expanderNkRef.current = nk;
    }
    onNodeExpand?.(nk);
  }, [onNodeExpand]);

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
    onCanvasClick?.();
    setIsDragging(true);
    lastPosRef.current = { x: e.clientX, y: e.clientY };
  }, [onCanvasClick]);

  const handleMouseMove = useCallback((e: React.MouseEvent<SVGSVGElement>) => {
    if (!isDragging) return;
    const dx = e.clientX - lastPosRef.current.x;
    const dy = e.clientY - lastPosRef.current.y;
    lastPosRef.current = { x: e.clientX, y: e.clientY };
    setCamera(prev => ({ ...prev, x: prev.x + dx, y: prev.y + dy }));
  }, [isDragging]);

  const stopDrag = useCallback(() => setIsDragging(false), []);

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
        onMouseUp={stopDrag}
        onMouseLeave={stopDrag}
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
            onNodeClick={onNodeClick}
            onNodeDoubleClick={onNodeDoubleClick}
            onNodePinToggle={onNodePinToggle}
            onNodeExpand={handleNodeExpand}
            onEdgeClick={onEdgeClick}
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
