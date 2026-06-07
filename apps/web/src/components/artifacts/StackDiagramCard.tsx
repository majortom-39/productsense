/**
 * StackDiagramCard — Theo's natural shape for "here's the recommended
 * tech stack". Stacked horizontal bands (frontend / backend / data /
 * infra) with the chosen items as pills inside each layer.
 */
import type { StackDiagramPayload } from "./types";

const LAYER_TINTS = [
  "bg-sky-50 border-sky-200 text-sky-900",
  "bg-emerald-50 border-emerald-200 text-emerald-900",
  "bg-amber-50 border-amber-200 text-amber-900",
  "bg-violet-50 border-violet-200 text-violet-900",
  "bg-rose-50 border-rose-200 text-rose-900",
  "bg-slate-50 border-slate-200 text-slate-900",
];

export function StackDiagramCard({ payload }: { payload: StackDiagramPayload }) {
  const { layers } = payload;
  if (layers.length === 0) {
    return (
      <p className="text-[12px] text-muted-foreground italic">
        Theo returned no layers.
      </p>
    );
  }
  return (
    <div className="flex flex-col gap-2">
      {layers.map((layer, i) => {
        const tint = LAYER_TINTS[i % LAYER_TINTS.length];
        return (
          <div
            key={i}
            className={`rounded-lg border ${tint} p-3`}
          >
            <div className="text-[10.5px] uppercase tracking-wider font-semibold mb-2 opacity-80">
              {layer.name}
            </div>
            <div className="flex flex-wrap gap-1.5">
              {layer.items.length === 0 ? (
                <span className="text-[11.5px] italic opacity-60">— empty layer —</span>
              ) : (
                layer.items.map((item, j) => (
                  <span
                    key={j}
                    className="px-2.5 py-1 rounded-md bg-white/70 backdrop-blur-sm text-[11.5px] font-medium border border-current/20"
                  >
                    {item}
                  </span>
                ))
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
