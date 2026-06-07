/**
 * GuardrailsTab — first-class surface for the project's guardrails.
 *
 * Guardrails ARE decisions (with `tag='guardrail'`) under the hood —
 * same table, same lifecycle. But conceptually they're rules-to-engineer-
 * against, not "we picked X over Y" judgments. Splitting them into their
 * own tab keeps the Decisions tab focused on judgment calls and gives
 * Wes's compiled rules a dedicated home.
 *
 * The DecisionsTab automatically filters guardrails out so they don't
 * show in two places. The PRD viewer still auto-renders the guardrails
 * as a §Guardrails section for read-aloud context.
 *
 * No founder-edits — guardrails are written by Wes (or by Maya via
 * `log_decision(tag='guardrail')` if she's compiling them directly).
 * "Discuss with Maya" is the only direct action; everything else flows
 * through chat.
 */
import { useMemo, useState } from "react";
import { Search, ShieldAlert, MessageSquarePlus, Sparkles } from "lucide-react";
import type { Decision } from "@/lib/api";

const Card: React.FC<{
  d: Decision;
  onDiscuss?: (d: Decision) => void;
}> = ({ d, onDiscuss }) => {
  return (
    <article className="rounded-2xl border border-rose-100 bg-rose-50/30 p-4 group hover:border-rose-200 transition-colors">
      <header className="flex items-start justify-between gap-3 mb-2 flex-wrap">
        <div className="flex items-center gap-2 min-w-0">
          <ShieldAlert size={13} className="text-rose-700 shrink-0" />
          <h3 className="text-[13.5px] font-semibold text-foreground leading-snug min-w-0">
            {d.title}
          </h3>
        </div>
        <span className="px-2 py-0.5 rounded-md bg-card text-[10px] font-mono text-muted-foreground border border-border shrink-0">
          {d.display_id}
        </span>
      </header>

      <p className="text-[12px] text-foreground/85 leading-relaxed mb-2 whitespace-pre-line">
        {d.detail}
      </p>
      {d.why && (
        <div className="text-[11.5px] text-muted-foreground leading-relaxed pl-3 border-l-2 border-rose-200 mb-2">
          <span className="font-medium text-foreground/70">Why: </span>
          {d.why}
        </div>
      )}

      {onDiscuss && (
        <div className="flex items-center justify-end pt-2 border-t border-rose-100/70">
          <button
            onClick={() => onDiscuss(d)}
            title="Quote this guardrail in chat — refine, scope, or revisit with Maya"
            className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[10.5px] font-medium text-muted-foreground hover:text-foreground hover:bg-rose-100/40 transition-colors"
          >
            <MessageSquarePlus size={11} />
            Discuss with Maya
          </button>
        </div>
      )}
    </article>
  );
};

interface Props {
  /** All decisions for the project — we filter to guardrails internally. */
  decisions: Decision[];
  onDiscuss?: (d: Decision) => void;
}

export function GuardrailsTab({ decisions, onDiscuss }: Props) {
  const [search, setSearch] = useState("");

  const guardrails = useMemo(
    () => decisions.filter((d) => d.tag === "guardrail" && d.status === "decided"),
    [decisions],
  );

  const visible = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return guardrails;
    return guardrails.filter((d) => {
      const hay = `${d.title} ${d.detail} ${d.why ?? ""} ${d.display_id}`.toLowerCase();
      return hay.includes(q);
    });
  }, [guardrails, search]);

  return (
    <div className="h-full flex flex-col">
      <div className="px-5 py-4 border-b border-border flex items-center justify-between flex-shrink-0">
        <div className="flex items-center gap-2">
          <ShieldAlert size={14} className="text-rose-700" />
          <h3 className="text-sm font-semibold text-foreground">Guardrails</h3>
          <span className="px-2 py-0.5 rounded-md bg-muted text-muted-foreground text-[10px] font-medium border border-border">
            {visible.length} of {guardrails.length}
          </span>
        </div>
      </div>

      <div className="px-5 pt-4 pb-3 border-b border-border flex flex-col gap-2.5 flex-shrink-0">
        <div className="flex items-center gap-2 bg-muted/40 rounded-lg border border-border px-2.5 py-1.5">
          <Search size={12} className="text-muted-foreground" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search guardrails…"
            className="flex-1 bg-transparent outline-none text-[12px] text-foreground placeholder:text-muted-foreground"
          />
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-5 py-5 space-y-3">
        {guardrails.length > 0 && (
          <p className="text-[11.5px] text-muted-foreground leading-relaxed flex items-start gap-1.5">
            <Sparkles size={11} className="text-muted-foreground/70 shrink-0 mt-0.5" />
            Runtime "must / must not" rules the BUILT product enforces — e.g. never
            score a claim without showing the source. The coding agent reads these
            via MCP and respects them on every task.
          </p>
        )}
        {visible.length === 0 ? (
          <div className="rounded-xl bg-muted/30 border border-dashed border-border p-8 text-center">
            <p className="text-[12px] font-medium text-foreground/80 mb-1">
              {guardrails.length === 0 ? "No guardrails yet" : "Nothing matches"}
            </p>
            <p className="text-[11px] text-muted-foreground leading-relaxed">
              {guardrails.length === 0
                ? "Once Wes compiles failure-mode research into rules, they'll appear here."
                : "Try a different search."}
            </p>
          </div>
        ) : (
          visible.map((d) => <Card key={d.id} d={d} onDiscuss={onDiscuss} />)
        )}
      </div>
    </div>
  );
}
