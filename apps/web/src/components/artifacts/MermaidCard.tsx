/**
 * MermaidCard — renders a Mermaid diagram inside the artifact surface.
 *
 * Why Mermaid: LLMs are very strong at writing mermaid; one library renders
 * flowcharts, sequence diagrams, ER, state machines, and class diagrams.
 * Lets Maya draw real architecture / data-flow / sequence diagrams instead
 * of trying to describe them in prose.
 *
 * Implementation notes:
 *   - Lazy-loads the mermaid module so the ~600KB dep isn't in the initial
 *     bundle. DiscoveryTab + chat are the only surfaces that import this.
 *   - Each render gets a unique id — mermaid needs that to namespace its
 *     generated SVG ids and avoid cross-card collisions.
 *   - Defensive: parse errors render an inline note instead of crashing the
 *     parent. Maya may produce slightly malformed mermaid; that's not fatal.
 *   - useEffect re-renders when source changes (e.g. Maya updates a card).
 */
import { useEffect, useRef, useState } from "react";
import { AlertTriangle } from "lucide-react";
import type { MermaidPayload } from "./types";

let mermaidPromise: Promise<typeof import("mermaid")> | null = null;
let mermaidInitialised = false;

async function loadMermaid() {
  if (!mermaidPromise) {
    mermaidPromise = import("mermaid").then((mod) => {
      if (!mermaidInitialised) {
        mod.default.initialize({
          startOnLoad: false,
          theme: "neutral",
          securityLevel: "strict",
          fontFamily: '"Geist", "Inter", system-ui, sans-serif',
          flowchart: { curve: "basis", htmlLabels: true },
          themeVariables: {
            primaryColor: "#fdf6f1",
            primaryTextColor: "#212121",
            primaryBorderColor: "#c96442",
            lineColor: "#5e5d59",
            secondaryColor: "#e8e6dc",
            tertiaryColor: "#f0eee6",
            background: "transparent",
          },
        });
        mermaidInitialised = true;
      }
      return mod;
    });
  }
  return mermaidPromise;
}

let _idSeq = 0;
function nextId() {
  _idSeq += 1;
  return `mmd-${Date.now().toString(36)}-${_idSeq}`;
}

interface Props {
  payload: MermaidPayload;
}

export function MermaidCard({ payload }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [error, setError] = useState<string | null>(null);
  const [renderingId] = useState(() => nextId());

  useEffect(() => {
    let cancelled = false;
    setError(null);
    (async () => {
      try {
        const mod = await loadMermaid();
        if (cancelled) return;
        const { svg } = await mod.default.render(renderingId, payload.source);
        if (cancelled) return;
        if (containerRef.current) {
          containerRef.current.innerHTML = svg;
        }
      } catch (e: unknown) {
        if (cancelled) return;
        const msg =
          e && typeof e === "object" && "message" in (e as Record<string, unknown>)
            ? String((e as { message: unknown }).message)
            : String(e);
        // Truncate; mermaid's parser errors can be enormous AST dumps.
        setError(msg.length > 240 ? msg.slice(0, 240) + "…" : msg);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [payload.source, renderingId]);

  return (
    <div className="space-y-2">
      {payload.caption && (
        <p className="text-[11px] font-medium text-muted-foreground italic">
          {payload.caption}
        </p>
      )}
      {error ? (
        <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 flex items-start gap-2">
          <AlertTriangle size={12} className="text-amber-700 shrink-0 mt-0.5" />
          <div className="flex-1 min-w-0">
            <p className="text-[11px] font-medium text-amber-900 mb-1">
              Couldn't render diagram
            </p>
            <p className="text-[10.5px] text-amber-800 leading-relaxed font-mono break-words">
              {error}
            </p>
            <details className="mt-2">
              <summary className="text-[10px] text-amber-800/80 cursor-pointer hover:text-amber-900">
                Show source
              </summary>
              <pre className="mt-1.5 text-[10px] text-amber-900/80 bg-white/40 border border-amber-100 rounded p-2 overflow-x-auto whitespace-pre">
                {payload.source}
              </pre>
            </details>
          </div>
        </div>
      ) : (
        <div
          ref={containerRef}
          className="overflow-x-auto rounded-lg border border-border bg-card/40 p-3 [&_svg]:max-w-full [&_svg]:h-auto [&_svg]:mx-auto"
        />
      )}
    </div>
  );
}
