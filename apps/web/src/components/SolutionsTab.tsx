import { useMemo } from "react";
import {
  Lightbulb,
  Check,
  Star,
  AlertTriangle,
  Sparkles,
  ListTree,
  CircleDot,
} from "lucide-react";
import type { Solution, Feature } from "@/lib/api";

/** SolutionsTab — the product-arc surface (deepagent §6). It walks the
 *  founder through Maya's thinking in the order she does it:
 *    1. Solutions — the candidate approaches she weighed, with trade-offs
 *       and her recommendation.
 *    2. Features — the capabilities that fall out of the chosen direction.
 *    3. The MVP cut — which of those features make the first build vs.
 *       what's parked for later.
 *
 *  Anything Maya flagged for a second look (needs_review) gets an amber
 *  marker so the founder knows where her confidence is soft. No time,
 *  no estimates (founder hard rule) — just what's in, what's out, and why. */

interface Props {
  solutions: Solution[];
  features: Feature[];
  onAskMaya?: (text: string) => void;
}

const SolutionCard: React.FC<{ s: Solution; onAskMaya?: (t: string) => void }> = ({
  s,
  onAskMaya,
}) => {
  const tradeoffs = (s.tradeoffs ?? {}) as { pros?: string[]; cons?: string[] };
  const pros = Array.isArray(tradeoffs.pros) ? tradeoffs.pros : [];
  const cons = Array.isArray(tradeoffs.cons) ? tradeoffs.cons : [];

  return (
    <div
      className={`relative rounded-2xl border p-4 transition-colors hover:border-border/80 ${
        s.recommended
          ? "bg-emerald-50/50 border-emerald-200"
          : "bg-card border-border"
      }`}
    >
      <div className="flex items-start justify-between gap-3 mb-1.5 flex-wrap">
        <div className="flex items-center gap-1.5">
          <span className="px-2 py-0.5 rounded-md bg-muted text-[10px] font-mono text-foreground/80 border border-border">
            {s.display_id}
          </span>
          {s.recommended && (
            <span className="flex items-center gap-1 px-2 py-0.5 rounded-md bg-emerald-100 text-emerald-800 text-[10px] font-medium border border-emerald-200">
              <Star size={9} className="fill-emerald-700 text-emerald-700" />
              Maya recommends
            </span>
          )}
        </div>
        {s.needs_review && (
          <span
            className="flex items-center gap-1 px-2 py-0.5 rounded-md bg-amber-50 text-amber-700 text-[10px] font-medium border border-amber-200"
            title={s.needs_review_why ?? "Maya flagged this for another look"}
          >
            <AlertTriangle size={9} />
            Needs a look
          </span>
        )}
      </div>

      <h4 className="text-[13.5px] font-semibold text-foreground leading-snug mb-1.5">
        {s.title}
      </h4>
      {s.summary && (
        <p className="text-[12px] text-foreground/85 leading-relaxed mb-3 whitespace-pre-line">
          {s.summary}
        </p>
      )}

      {(pros.length > 0 || cons.length > 0) && (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5 mb-3">
          {pros.length > 0 && (
            <div className="rounded-lg bg-emerald-50/60 border border-emerald-100 p-2.5">
              <p className="text-[10px] uppercase tracking-wide text-emerald-700 font-semibold mb-1.5">
                Pros
              </p>
              <ul className="space-y-1">
                {pros.map((p, i) => (
                  <li key={i} className="flex items-start gap-1.5 text-[11.5px] text-foreground/80">
                    <Check size={11} className="mt-0.5 shrink-0 text-emerald-600" />
                    <span className="leading-snug">{p}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {cons.length > 0 && (
            <div className="rounded-lg bg-rose-50/50 border border-rose-100 p-2.5">
              <p className="text-[10px] uppercase tracking-wide text-rose-700 font-semibold mb-1.5">
                Trade-offs
              </p>
              <ul className="space-y-1">
                {cons.map((c, i) => (
                  <li key={i} className="flex items-start gap-1.5 text-[11.5px] text-foreground/80">
                    <CircleDot size={10} className="mt-0.5 shrink-0 text-rose-500" />
                    <span className="leading-snug">{c}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      {s.needs_review && s.needs_review_why && (
        <div className="text-[11px] text-amber-700 leading-relaxed pl-3 border-l-2 border-amber-200 mb-3">
          {s.needs_review_why}
        </div>
      )}

      {onAskMaya && (
        <div className="flex items-center gap-2 pt-2 border-t border-border">
          <button
            className="px-3 py-1.5 rounded-md text-[10.5px] font-medium text-muted-foreground hover:text-foreground hover:bg-muted transition-colors flex items-center gap-1.5"
            onClick={() =>
              onAskMaya(`${s.display_id} — ${s.title}\n\n${s.summary ?? ""}`)
            }
          >
            <Sparkles size={10} />
            Discuss
          </button>
        </div>
      )}
    </div>
  );
};

const FeatureRow: React.FC<{ f: Feature; onAskMaya?: (t: string) => void }> = ({
  f,
  onAskMaya,
}) => (
  <div
    className={`flex items-start gap-2.5 rounded-xl border px-3.5 py-2.5 transition-colors ${
      f.in_mvp ? "bg-card border-border" : "bg-muted/30 border-dashed border-border"
    }`}
  >
    <span className="mt-0.5 shrink-0">
      {f.in_mvp ? (
        <Check size={14} className="text-emerald-600" />
      ) : (
        <CircleDot size={13} className="text-muted-foreground/50" />
      )}
    </span>
    <div className="min-w-0 flex-1">
      <div className="flex items-center gap-1.5 flex-wrap">
        <span className="px-1.5 py-0.5 rounded bg-muted text-[9.5px] font-mono text-muted-foreground border border-border">
          {f.display_id}
        </span>
        <span
          className={`text-[12.5px] leading-snug ${
            f.in_mvp ? "text-foreground font-medium" : "text-foreground/70"
          }`}
        >
          {f.title}
        </span>
        {f.needs_review && (
          <span
            className="flex items-center gap-0.5 text-[9.5px] text-amber-600"
            title={f.needs_review_why ?? "Flagged for another look"}
          >
            <AlertTriangle size={9} />
          </span>
        )}
      </div>
      {f.description && (
        <p className="text-[11px] text-muted-foreground leading-snug mt-0.5">
          {f.description}
        </p>
      )}
    </div>
    {onAskMaya && (
      <button
        className="shrink-0 px-2 py-1 rounded-md text-[10px] font-medium text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
        onClick={() => onAskMaya(`${f.display_id} — ${f.title}\n\n${f.description ?? ""}`)}
      >
        Discuss
      </button>
    )}
  </div>
);

export function SolutionsTab({ solutions, features, onAskMaya }: Props) {
  const mvp = useMemo(() => features.filter((f) => f.in_mvp), [features]);
  const parked = useMemo(() => features.filter((f) => !f.in_mvp), [features]);
  const isEmpty = solutions.length === 0 && features.length === 0;

  return (
    <div className="h-full flex flex-col">
      <div className="px-5 py-4 border-b border-border flex items-center justify-between flex-shrink-0">
        <div className="flex items-center gap-2">
          <Lightbulb size={14} className="text-muted-foreground" />
          <h3 className="text-sm font-semibold text-foreground">Solutions & scope</h3>
          {features.length > 0 && (
            <span className="px-2 py-0.5 rounded-md bg-muted text-muted-foreground text-[10px] font-medium border border-border">
              {mvp.length} in MVP · {parked.length} parked
            </span>
          )}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-6 py-6">
        <div className="max-w-[680px] mx-auto space-y-8">
          {isEmpty ? (
            <div className="rounded-xl bg-muted/30 border border-dashed border-border p-8 text-center">
              <p className="text-[12px] font-medium text-foreground/80 mb-1">
                No solutions yet
              </p>
              <p className="text-[11px] text-muted-foreground leading-relaxed">
                Once Maya weighs the ways to build this, the approaches she
                considered — and the features that fall out of the one she
                picks — show up here.
              </p>
            </div>
          ) : (
            <>
              {solutions.length > 0 && (
                <section>
                  <div className="flex items-center gap-2 mb-3">
                    <Lightbulb size={12} className="text-foreground" />
                    <h2 className="text-[11px] font-semibold uppercase tracking-wider text-foreground">
                      Approaches Maya weighed
                    </h2>
                    <span className="px-1.5 py-0.5 rounded-full bg-muted text-muted-foreground text-[10px] font-semibold">
                      {solutions.length}
                    </span>
                  </div>
                  <div className="space-y-3">
                    {solutions.map((s) => (
                      <SolutionCard key={s.id} s={s} onAskMaya={onAskMaya} />
                    ))}
                  </div>
                </section>
              )}

              {mvp.length > 0 && (
                <section>
                  <div className="flex items-center gap-2 mb-3">
                    <ListTree size={12} className="text-emerald-600" />
                    <h2 className="text-[11px] font-semibold uppercase tracking-wider text-emerald-700">
                      In the first build
                    </h2>
                    <span className="px-1.5 py-0.5 rounded-full bg-emerald-100 text-emerald-800 text-[10px] font-semibold">
                      {mvp.length}
                    </span>
                  </div>
                  <div className="space-y-2">
                    {mvp.map((f) => (
                      <FeatureRow key={f.id} f={f} onAskMaya={onAskMaya} />
                    ))}
                  </div>
                </section>
              )}

              {parked.length > 0 && (
                <section>
                  <div className="flex items-center gap-2 mb-3">
                    <CircleDot size={11} className="text-muted-foreground" />
                    <h2 className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                      Parked for later
                    </h2>
                    <span className="px-1.5 py-0.5 rounded-full bg-muted text-muted-foreground text-[10px] font-semibold">
                      {parked.length}
                    </span>
                  </div>
                  <div className="space-y-2">
                    {parked.map((f) => (
                      <FeatureRow key={f.id} f={f} onAskMaya={onAskMaya} />
                    ))}
                  </div>
                </section>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
