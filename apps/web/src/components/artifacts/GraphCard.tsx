/**
 * GraphCard — light-weight directed graph viewer. No physics library: we
 * lay nodes out on a circle (or a single line for ≤3) and draw edges as
 * arrows between them. Good for showing flows, dependency chains, or
 * "this leads to that" maps.
 *
 * For dense graphs (>~12 nodes) the layout becomes a hairball — Maya
 * should usually prefer a table or stack diagram for those. We render
 * gracefully anyway.
 */
import { useMemo } from "react";
import type { GraphPayload } from "./types";

const NODE_RADIUS = 32;
const PADDING = 24;
const COLORS_BY_GROUP: Record<string, string> = {};
const PALETTE = [
  "#0f766e",
  "#9d2545",
  "#7c3aed",
  "#b45309",
  "#1d4ed8",
  "#15803d",
];

function colorForGroup(group: string | undefined): string {
  if (!group) return "hsl(var(--muted-foreground))";
  if (!(group in COLORS_BY_GROUP)) {
    COLORS_BY_GROUP[group] = PALETTE[Object.keys(COLORS_BY_GROUP).length % PALETTE.length];
  }
  return COLORS_BY_GROUP[group];
}

export function GraphCard({ payload }: { payload: GraphPayload }) {
  const { nodes, edges } = payload;

  const layout = useMemo(() => {
    if (nodes.length === 0) return { positions: new Map<string, { x: number; y: number }>(), width: 0, height: 0 };
    const w = 480;
    const h = 280;
    const cx = w / 2;
    const cy = h / 2;
    const r = Math.min(cx, cy) - NODE_RADIUS - PADDING;
    const positions = new Map<string, { x: number; y: number }>();
    if (nodes.length === 1) {
      positions.set(nodes[0].id, { x: cx, y: cy });
    } else {
      nodes.forEach((n, i) => {
        const theta = (2 * Math.PI * i) / nodes.length - Math.PI / 2;
        positions.set(n.id, {
          x: cx + r * Math.cos(theta),
          y: cy + r * Math.sin(theta),
        });
      });
    }
    return { positions, width: w, height: h };
  }, [nodes]);

  if (nodes.length === 0) {
    return (
      <p className="text-[12px] text-muted-foreground italic">
        Empty graph — Maya passed no nodes.
      </p>
    );
  }

  const { positions, width, height } = layout;

  return (
    <div className="w-full overflow-x-auto rounded-lg border border-border bg-card">
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="w-full h-auto"
        style={{ minWidth: 360 }}
      >
        <defs>
          <marker
            id="arrow"
            viewBox="0 0 10 10"
            refX="10"
            refY="5"
            markerWidth="6"
            markerHeight="6"
            orient="auto-start-reverse"
          >
            <path d="M 0 0 L 10 5 L 0 10 z" fill="hsl(var(--muted-foreground))" />
          </marker>
        </defs>

        {/* Edges first so nodes paint over them */}
        {edges.map((e, i) => {
          const a = positions.get(e.from);
          const b = positions.get(e.to);
          if (!a || !b) return null;
          // Pull endpoints back from the node centre by NODE_RADIUS
          const dx = b.x - a.x;
          const dy = b.y - a.y;
          const len = Math.hypot(dx, dy) || 1;
          const ux = dx / len;
          const uy = dy / len;
          const x1 = a.x + ux * NODE_RADIUS;
          const y1 = a.y + uy * NODE_RADIUS;
          const x2 = b.x - ux * NODE_RADIUS;
          const y2 = b.y - uy * NODE_RADIUS;
          const mx = (x1 + x2) / 2;
          const my = (y1 + y2) / 2;
          return (
            <g key={i}>
              <line
                x1={x1}
                y1={y1}
                x2={x2}
                y2={y2}
                stroke="hsl(var(--muted-foreground))"
                strokeWidth="1.5"
                markerEnd="url(#arrow)"
              />
              {e.label && (
                <text
                  x={mx}
                  y={my - 4}
                  textAnchor="middle"
                  fontSize="10"
                  fill="hsl(var(--muted-foreground))"
                  className="pointer-events-none"
                >
                  {e.label}
                </text>
              )}
            </g>
          );
        })}

        {/* Nodes */}
        {nodes.map((n) => {
          const p = positions.get(n.id);
          if (!p) return null;
          const colour = colorForGroup(n.group);
          return (
            <g key={n.id}>
              <circle cx={p.x} cy={p.y} r={NODE_RADIUS} fill={`${colour}22`} stroke={colour} strokeWidth="1.5" />
              <text
                x={p.x}
                y={p.y}
                textAnchor="middle"
                dominantBaseline="middle"
                fontSize="11"
                fontWeight="500"
                fill="hsl(var(--foreground))"
              >
                {n.label.length > 12 ? n.label.slice(0, 11) + "…" : n.label}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}
