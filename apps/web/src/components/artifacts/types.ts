/**
 * Payload shapes for each render_kind a sub-agent or Maya can produce.
 *
 * Components are defensive: validators below return either a typed view of
 * the payload or null. A null result means the payload is malformed for
 * that kind, and the dispatcher should fall back to a degraded text card.
 *
 * Keep these in sync with:
 *   apps/api/app/deepagent/domain_tools.py::MAYA_RENDER_KINDS
 *   apps/api/app/services/discovery_artifacts.py::VALID_RENDER_KINDS
 *   supabase render_kind_enum
 */

export type RenderKind =
  | "text"
  | "table"
  | "matrix"
  | "bar_chart"
  | "line_chart"
  | "graph"
  | "persona_cards"
  | "stack_diagram"
  /** Mermaid diagram — `mermaid` source text. Good for architecture,
   *  sequence diagrams, ER, state machines. LLMs are strong at writing it. */
  | "mermaid"
  /** A UX flow: N screens wrapped in a device frame, plus arrows describing
   *  the transitions. Greyscale, structural. Maya draws these (after founder
   *  sign-off) as the visual half of the spec; per-screen `derived_from` keeps
   *  every element traceable to the feature + friction it serves. */
  | "wireframe_flow";

// ─── Payload shapes ────────────────────────────────────────────────────────

export interface TextPayload {
  body_md?: string;
}

export interface TablePayload {
  columns: string[];
  rows: (string | number | null)[][];
}

export interface MatrixPayload {
  row_labels: string[];
  col_labels: string[];
  cells: (string | number | null)[][];
}

export interface BarChartPayload {
  x_label?: string;
  y_label?: string;
  categories: string[];
  series: { name: string; values: number[] }[];
}

export interface LineChartPayload {
  x_label?: string;
  y_label?: string;
  series: { name: string; points: { x: number | string; y: number }[] }[];
}

export interface GraphPayload {
  nodes: { id: string; label: string; group?: string }[];
  edges: { from: string; to: string; label?: string }[];
}

export interface PersonaCardsPayload {
  personas: {
    name: string;
    role?: string;
    traits?: string[];
    quote?: string;
    pains?: string[];
  }[];
}

export interface StackDiagramPayload {
  layers: { name: string; items: string[] }[];
}

export interface MermaidPayload {
  /** Raw mermaid source. Validation happens at render time — we don't
   *  pre-parse the DSL ourselves. */
  source: string;
  /** Optional caption shown above the diagram (e.g. "System architecture"). */
  caption?: string;
}

/** Device frame each screen is wrapped in. Drives the chrome the card draws. */
export type WireframeDevice = "phone" | "browser" | "extension" | "desktop";

/** Flow category — drives the accent chip so the founder can spot what KIND
 *  of flow they're looking at. Small, canonical taxonomy. */
export type WireframeFlowType =
  | "onboarding"
  | "core"
  | "settings"
  | "error"
  | "empty"
  | "auth"
  | "other";

/** ── Screen body blocks (the component DSL) ───────────────────────────────
 *  Maya composes a screen from these typed blocks instead of authoring HTML.
 *  The renderer owns ALL layout, spacing, and typography, so every screen is
 *  consistent + mid-fidelity regardless of how the model fills the content.
 *  A curated, deliberately small library — add to it intentionally, not ad hoc. */
export type WireframeBlock =
  | { type: "heading"; text: string; level?: 1 | 2 | 3 }
  | { type: "text"; text: string; tone?: "default" | "muted" }
  | { type: "input"; label?: string; placeholder?: string; kind?: "text" | "password" | "search" | "textarea" }
  | { type: "button"; label: string; variant?: "primary" | "secondary"; fullWidth?: boolean }
  | { type: "buttonGroup"; layout?: "row" | "stack"; buttons: { label: string; variant?: "primary" | "secondary" }[] }
  | { type: "list"; items: { title: string; subtitle?: string; leading?: "avatar" | "icon" | "thumb"; trailing?: string }[] }
  | { type: "card"; title?: string; body?: string; chips?: string[] }
  | { type: "image"; label?: string; ratio?: "square" | "wide" | "tall" }
  | { type: "media"; variant?: "image" | "audio" | "video" | "map"; label?: string }
  | { type: "chips"; items: string[] }
  | { type: "metricRow"; metrics: { value: string; label?: string }[] }
  | { type: "field"; label: string; value?: string }
  | { type: "toggleRow"; label: string; on?: boolean }
  | { type: "segmented"; options: string[]; active?: number }
  | { type: "hero"; kicker?: string; title: string; subtitle?: string; media?: boolean }
  | { type: "divider" }
  | { type: "spacer"; size?: "sm" | "md" | "lg" };

export type WireframeBlockType = WireframeBlock["type"];

/** The top app bar (title + leading/trailing affordances). Rendered by code. */
export interface WireframeAppBar {
  title?: string;
  leading?: "back" | "menu" | "none";
  /** Short labels for trailing affordances (e.g. "Save", "⋯", "Filter"). */
  trailing?: string[];
}

/** The pinned bottom region — either tab navigation or a primary action bar. */
export type WireframeBottomBar =
  | { kind: "nav"; items: { label: string; active?: boolean }[] }
  | { kind: "actions"; buttons: { label: string; variant?: "primary" | "secondary" }[] };

export interface WireframeScreen {
  /** Short name for the screen (e.g. "Welcome", "Today's meals"). Used as the
   *  label above the frame + referenced by transitions. */
  name: string;
  /** The screen body as typed blocks — the preferred path (deterministic render). */
  blocks?: WireframeBlock[];
  /** Optional top app bar. */
  appBar?: WireframeAppBar;
  /** Optional pinned bottom bar (tab nav or action buttons). */
  bottomBar?: WireframeBottomBar;
  /** @deprecated Legacy structural HTML path. Still rendered (in a sandboxed
   *  iframe) when `blocks` is absent, so older artifacts keep working. */
  html?: string;
  /** One-liner on the screen's PURPOSE (not its layout). */
  notes?: string;
  /** Prose pointer to the research that drove this screen — the feature it
   *  serves + the friction/pain it removes. The traceability half. */
  derived_from?: string;
}

export interface WireframeTransition {
  from: string;
  to: string;
  trigger?: string;
}

export interface WireframeFlowPayload {
  flow_name?: string;
  device: WireframeDevice;
  flow_type?: WireframeFlowType;
  screens: WireframeScreen[];
  transitions?: WireframeTransition[];
  /** Research artifact ids whose findings drove the whole flow. */
  informed_by?: string[];
}

// ─── Defensive parsers ─────────────────────────────────────────────────────
// Each returns the typed payload if it looks right, otherwise null. Components
// use these to decide whether to render or hand off to TextCard fallback.

const isStringArr = (v: unknown): v is string[] =>
  Array.isArray(v) && v.every((x) => typeof x === "string");

const isMatrixRow = (v: unknown): v is (string | number | null)[] =>
  Array.isArray(v) &&
  v.every((x) => x === null || typeof x === "string" || typeof x === "number");

export function parseText(p: unknown): TextPayload | null {
  if (!p || typeof p !== "object") return { body_md: "" };
  const obj = p as Record<string, unknown>;
  return { body_md: typeof obj.body_md === "string" ? obj.body_md : "" };
}

export function parseTable(p: unknown): TablePayload | null {
  if (!p || typeof p !== "object") return null;
  const obj = p as Record<string, unknown>;
  if (!isStringArr(obj.columns)) return null;
  if (!Array.isArray(obj.rows) || !obj.rows.every(isMatrixRow)) return null;
  return { columns: obj.columns, rows: obj.rows as (string | number | null)[][] };
}

export function parseMatrix(p: unknown): MatrixPayload | null {
  if (!p || typeof p !== "object") return null;
  const obj = p as Record<string, unknown>;
  if (!isStringArr(obj.row_labels) || !isStringArr(obj.col_labels)) return null;
  if (!Array.isArray(obj.cells) || !obj.cells.every(isMatrixRow)) return null;
  return {
    row_labels: obj.row_labels,
    col_labels: obj.col_labels,
    cells: obj.cells as (string | number | null)[][],
  };
}

export function parseBarChart(p: unknown): BarChartPayload | null {
  if (!p || typeof p !== "object") return null;
  const obj = p as Record<string, unknown>;
  if (!isStringArr(obj.categories)) return null;
  if (
    !Array.isArray(obj.series) ||
    !obj.series.every(
      (s) =>
        s &&
        typeof s === "object" &&
        typeof (s as { name?: unknown }).name === "string" &&
        Array.isArray((s as { values?: unknown }).values) &&
        ((s as { values: unknown[] }).values).every((v) => typeof v === "number"),
    )
  ) {
    return null;
  }
  return {
    x_label: typeof obj.x_label === "string" ? obj.x_label : undefined,
    y_label: typeof obj.y_label === "string" ? obj.y_label : undefined,
    categories: obj.categories,
    series: obj.series as { name: string; values: number[] }[],
  };
}

export function parseLineChart(p: unknown): LineChartPayload | null {
  if (!p || typeof p !== "object") return null;
  const obj = p as Record<string, unknown>;
  if (
    !Array.isArray(obj.series) ||
    !obj.series.every(
      (s) =>
        s &&
        typeof s === "object" &&
        typeof (s as { name?: unknown }).name === "string" &&
        Array.isArray((s as { points?: unknown }).points) &&
        ((s as { points: unknown[] }).points).every(
          (pt) =>
            pt &&
            typeof pt === "object" &&
            ("x" in (pt as object)) &&
            typeof (pt as { y?: unknown }).y === "number",
        ),
    )
  ) {
    return null;
  }
  return {
    x_label: typeof obj.x_label === "string" ? obj.x_label : undefined,
    y_label: typeof obj.y_label === "string" ? obj.y_label : undefined,
    series: obj.series as { name: string; points: { x: number | string; y: number }[] }[],
  };
}

export function parseGraph(p: unknown): GraphPayload | null {
  if (!p || typeof p !== "object") return null;
  const obj = p as Record<string, unknown>;
  if (
    !Array.isArray(obj.nodes) ||
    !obj.nodes.every(
      (n) =>
        n &&
        typeof n === "object" &&
        typeof (n as { id?: unknown }).id === "string" &&
        typeof (n as { label?: unknown }).label === "string",
    )
  ) {
    return null;
  }
  if (
    !Array.isArray(obj.edges) ||
    !obj.edges.every(
      (e) =>
        e &&
        typeof e === "object" &&
        typeof (e as { from?: unknown }).from === "string" &&
        typeof (e as { to?: unknown }).to === "string",
    )
  ) {
    return null;
  }
  return {
    nodes: obj.nodes as GraphPayload["nodes"],
    edges: obj.edges as GraphPayload["edges"],
  };
}

export function parsePersonaCards(p: unknown): PersonaCardsPayload | null {
  if (!p || typeof p !== "object") return null;
  const obj = p as Record<string, unknown>;
  if (
    !Array.isArray(obj.personas) ||
    !obj.personas.every(
      (x) =>
        x &&
        typeof x === "object" &&
        typeof (x as { name?: unknown }).name === "string",
    )
  ) {
    return null;
  }
  return { personas: obj.personas as PersonaCardsPayload["personas"] };
}

export function parseMermaid(p: unknown): MermaidPayload | null {
  if (!p || typeof p !== "object") return null;
  const obj = p as Record<string, unknown>;
  const source = typeof obj.source === "string" ? obj.source.trim() : "";
  if (!source) return null;
  return {
    source,
    caption: typeof obj.caption === "string" ? obj.caption : undefined,
  };
}

const VALID_DEVICES: WireframeDevice[] = ["phone", "browser", "extension", "desktop"];
const VALID_FLOW_TYPES: WireframeFlowType[] = [
  "onboarding", "core", "settings", "error", "empty", "auth", "other",
];

const KNOWN_BLOCK_TYPES = new Set<WireframeBlockType>([
  "heading", "text", "input", "button", "buttonGroup", "list", "card", "image",
  "media", "chips", "metricRow", "field", "toggleRow", "segmented", "hero",
  "divider", "spacer",
]);

/** Keep only well-formed blocks (an object with a known `type`). The renderer is
 *  defensive about the rest, so we pass them through largely as-is. */
function parseBlocks(raw: unknown): WireframeBlock[] {
  if (!Array.isArray(raw)) return [];
  const out: WireframeBlock[] = [];
  for (const b of raw) {
    if (!b || typeof b !== "object") continue;
    const t = (b as { type?: unknown }).type;
    if (typeof t === "string" && KNOWN_BLOCK_TYPES.has(t as WireframeBlockType)) {
      out.push(b as WireframeBlock);
    }
  }
  return out;
}

function parseAppBar(raw: unknown): WireframeAppBar | undefined {
  if (!raw || typeof raw !== "object") return undefined;
  const o = raw as Record<string, unknown>;
  const leading =
    o.leading === "back" || o.leading === "menu" || o.leading === "none"
      ? o.leading
      : undefined;
  const trailing = isStringArr(o.trailing) ? o.trailing : undefined;
  const title = typeof o.title === "string" ? o.title : undefined;
  if (title === undefined && !leading && !trailing) return undefined;
  return { title, leading, trailing };
}

function parseBottomBar(raw: unknown): WireframeBottomBar | undefined {
  if (!raw || typeof raw !== "object") return undefined;
  const o = raw as Record<string, unknown>;
  if (o.kind === "nav" && Array.isArray(o.items)) {
    const items = o.items
      .filter((i): i is Record<string, unknown> => !!i && typeof i === "object")
      .map((i) => ({ label: String(i.label ?? ""), active: i.active === true }))
      .filter((i) => i.label);
    return items.length > 0 ? { kind: "nav", items } : undefined;
  }
  if (o.kind === "actions" && Array.isArray(o.buttons)) {
    const buttons = o.buttons
      .filter((b): b is Record<string, unknown> => !!b && typeof b === "object")
      .map((b) => ({
        label: String(b.label ?? ""),
        variant: b.variant === "secondary" ? ("secondary" as const) : ("primary" as const),
      }))
      .filter((b) => b.label);
    return buttons.length > 0 ? { kind: "actions", buttons } : undefined;
  }
  return undefined;
}

export function parseWireframeFlow(p: unknown): WireframeFlowPayload | null {
  if (!p || typeof p !== "object") return null;
  const obj = p as Record<string, unknown>;
  const rawDevice = obj.device;
  const device: WireframeDevice =
    typeof rawDevice === "string" && (VALID_DEVICES as string[]).includes(rawDevice)
      ? (rawDevice as WireframeDevice)
      : "browser";
  const rawScreens = obj.screens;
  if (!Array.isArray(rawScreens) || rawScreens.length === 0) return null;
  const screens: WireframeScreen[] = [];
  for (const s of rawScreens) {
    if (!s || typeof s !== "object") continue;
    const sObj = s as Record<string, unknown>;
    const name = typeof sObj.name === "string" ? sObj.name.trim() : "";
    if (!name) continue;
    const blocks = parseBlocks(sObj.blocks);
    const html = typeof sObj.html === "string" ? sObj.html : "";
    // A screen needs either typed blocks (preferred) or legacy html.
    if (blocks.length === 0 && !html) continue;
    screens.push({
      name,
      blocks: blocks.length > 0 ? blocks : undefined,
      appBar: parseAppBar(sObj.appBar),
      bottomBar: parseBottomBar(sObj.bottomBar),
      html: html || undefined,
      notes: typeof sObj.notes === "string" ? sObj.notes : undefined,
      derived_from: typeof sObj.derived_from === "string" ? sObj.derived_from : undefined,
    });
  }
  if (screens.length === 0) return null;

  const transitions: WireframeTransition[] = [];
  if (Array.isArray(obj.transitions)) {
    for (const t of obj.transitions) {
      if (!t || typeof t !== "object") continue;
      const tObj = t as Record<string, unknown>;
      const from = typeof tObj.from === "string" ? tObj.from : "";
      const to = typeof tObj.to === "string" ? tObj.to : "";
      if (!from || !to) continue;
      transitions.push({
        from,
        to,
        trigger: typeof tObj.trigger === "string" ? tObj.trigger : undefined,
      });
    }
  }

  const rawFlowType = obj.flow_type;
  const flow_type: WireframeFlowType =
    typeof rawFlowType === "string" && (VALID_FLOW_TYPES as string[]).includes(rawFlowType)
      ? (rawFlowType as WireframeFlowType)
      : "other";

  const informed_by: string[] = Array.isArray(obj.informed_by)
    ? obj.informed_by.filter((x): x is string => typeof x === "string" && x.length > 0)
    : [];

  return {
    flow_name: typeof obj.flow_name === "string" ? obj.flow_name : undefined,
    device,
    flow_type,
    screens,
    transitions: transitions.length > 0 ? transitions : undefined,
    informed_by: informed_by.length > 0 ? informed_by : undefined,
  };
}

export function parseStackDiagram(p: unknown): StackDiagramPayload | null {
  if (!p || typeof p !== "object") return null;
  const obj = p as Record<string, unknown>;
  if (
    !Array.isArray(obj.layers) ||
    !obj.layers.every(
      (l) =>
        l &&
        typeof l === "object" &&
        typeof (l as { name?: unknown }).name === "string" &&
        isStringArr((l as { items?: unknown }).items),
    )
  ) {
    return null;
  }
  return { layers: obj.layers as StackDiagramPayload["layers"] };
}
