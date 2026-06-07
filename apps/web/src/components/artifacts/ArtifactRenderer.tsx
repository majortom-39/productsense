/**
 * ArtifactRenderer — single dispatcher used by:
 *   1. DiscoveryTab (renders Maya-pinned dashboard cards)
 *   2. ChatPanel  (renders a sub-agent's reply inline inside the
 *                  AgentCallCard so the founder sees the rich output
 *                  in flow, not just JSON)
 *
 * Pass render_kind + payload. The dispatcher delegates to the matching
 * card component. Any payload that doesn't parse for its declared
 * render_kind falls back to TextCard with a "degraded" flag — so a
 * malformed sub-agent never breaks the UI, it just looks less rich.
 *
 * For render_kind='text', the body can come from either:
 *   - payload.body_md (Maya's create_artifact synthesis), or
 *   - the externally-passed `textBody` prop (sub-agent's `finding` +
 *     bullets, or a Maya pin where the body lives in `summary`).
 */
import type { RenderKind } from "./types";
import {
  parseText,
  parseTable,
  parseMatrix,
  parseBarChart,
  parseLineChart,
  parseGraph,
  parsePersonaCards,
  parseStackDiagram,
  parseMermaid,
  parseWireframeFlow,
} from "./types";
import { TextCard } from "./TextCard";
import { TableCard } from "./TableCard";
import { MatrixCard } from "./MatrixCard";
import { BarChartCard } from "./BarChartCard";
import { LineChartCard } from "./LineChartCard";
import { GraphCard } from "./GraphCard";
import { PersonaCardsCard } from "./PersonaCardsCard";
import { StackDiagramCard } from "./StackDiagramCard";
import { MermaidCard } from "./MermaidCard";
import { WireframeFlowCard } from "./WireframeFlowCard";

interface Props {
  render_kind: RenderKind | string;     // string for forward-compat
  payload: unknown;
  /** Optional fallback markdown body used when render_kind='text' and
   *  payload doesn't carry a `body_md`. Typical use: pass the sub-agent's
   *  `finding` joined with `bullets`, or an artifact's `summary`. */
  textBody?: string | null;
}

export function ArtifactRenderer({ render_kind, payload, textBody }: Props) {
  switch (render_kind) {
    case "text": {
      const parsed = parseText(payload);
      const body = parsed?.body_md && parsed.body_md.trim()
        ? parsed.body_md
        : (textBody ?? "");
      return <TextCard body={body} />;
    }
    case "table": {
      const p = parseTable(payload);
      return p ? <TableCard payload={p} /> : <TextCard body={textBody} degraded />;
    }
    case "matrix": {
      const p = parseMatrix(payload);
      return p ? <MatrixCard payload={p} /> : <TextCard body={textBody} degraded />;
    }
    case "bar_chart": {
      const p = parseBarChart(payload);
      return p ? <BarChartCard payload={p} /> : <TextCard body={textBody} degraded />;
    }
    case "line_chart": {
      const p = parseLineChart(payload);
      return p ? <LineChartCard payload={p} /> : <TextCard body={textBody} degraded />;
    }
    case "graph": {
      const p = parseGraph(payload);
      return p ? <GraphCard payload={p} /> : <TextCard body={textBody} degraded />;
    }
    case "persona_cards": {
      const p = parsePersonaCards(payload);
      return p ? <PersonaCardsCard payload={p} /> : <TextCard body={textBody} degraded />;
    }
    case "stack_diagram": {
      const p = parseStackDiagram(payload);
      return p ? <StackDiagramCard payload={p} /> : <TextCard body={textBody} degraded />;
    }
    case "mermaid": {
      const p = parseMermaid(payload);
      return p ? <MermaidCard payload={p} /> : <TextCard body={textBody} degraded />;
    }
    case "wireframe_flow": {
      const p = parseWireframeFlow(payload);
      return p ? <WireframeFlowCard payload={p} /> : <TextCard body={textBody} degraded />;
    }
    default:
      // Unknown render_kind — be permissive, render whatever text we have.
      return <TextCard body={textBody} degraded />;
  }
}
