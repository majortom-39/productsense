import { useMemo, useState } from "react";
import {
  History,
  User,
  Sparkles,
  AlertTriangle,
  Search,
  Pin,
  Link2,
  RotateCcw,
  Code2,
  Replace,
} from "lucide-react";
import type { Decision, Task } from "@/lib/api";

const decidedByConfig: Record<
  string,
  { label: string; icon: React.ReactNode; tone: string }
> = {
  maya_autonomous: {
    // Fires in two cases:
    //   1. Maya proactively logs a decision during chat (her default path)
    //   2. Coding agent asks her via MCP → she answers without escalating
    // The old label only described case 2 and read as "mock data" to the
    // founder when it was actually their own chat decisions. This label
    // covers both honestly.
    label: "Maya decided autonomously",
    icon: <Sparkles size={10} />,
    tone: "text-violet-700",
  },
  agent_with_user: {
    label: "You + coding agent · resolved in your IDE",
    icon: <Code2 size={10} />,
    tone: "text-blue-700",
  },
  maya_with_user: {
    label: "You + Maya · brainstormed in chat",
    icon: <Sparkles size={10} />,
    tone: "text-primary",
  },
  user: {
    label: "You alone",
    icon: <User size={10} />,
    tone: "text-foreground",
  },
  agent_flagged: {
    label: "Open question · escalated to Maya",
    icon: <AlertTriangle size={10} />,
    tone: "text-amber-700",
  },
};

const tagStyles: Record<string, string> = {
  guardrail: "bg-rose-50 text-rose-700 border-rose-100",
  scope: "bg-blue-50 text-blue-700 border-blue-100",
  technical: "bg-violet-50 text-violet-700 border-violet-100",
  flagged: "bg-amber-50 text-amber-700 border-amber-100",
};

type FilterId = "all" | "open" | "pinned" | "scope" | "technical";

// Guardrails have their own dedicated tab now — DecisionsTab is for
// judgment-call decisions only (scope, technical, open questions, etc.).
const filters: { id: FilterId; label: string }[] = [
  { id: "all", label: "All" },
  { id: "open", label: "Open questions" },
  { id: "pinned", label: "Pinned" },
  { id: "scope", label: "Scope" },
  { id: "technical", label: "Technical" },
];

const Card: React.FC<{
  d: Decision;
  tasks: Task[];
  decisionsById: Map<string, Decision>;
  onDiscuss?: (d: Decision) => void;
}> = ({ d, tasks, decisionsById, onDiscuss }) => {
  const cfg = decidedByConfig[d.decided_by] ?? decidedByConfig["user"];
  const isOpen = d.status === "open";
  // If this decision replaces a prior one, surface it. We look up by uuid;
  // if the prior row was hard-deleted or is loaded outside the current view,
  // we fall back to "an earlier decision".
  const replaced = d.supersedes ? decisionsById.get(d.supersedes) : null;

  const affectedTasks = (d.affects ?? [])
    .map((id: string) => tasks.find((t) => t.id === id || t.display_id === id))
    .filter(Boolean) as Task[];

  return (
    <div
      className={`relative rounded-2xl border p-4 hover:border-border/80 transition-colors ${
        isOpen ? "bg-amber-50/50 border-amber-200" : "bg-card border-border"
      }`}
    >
      {d.pinned && (
        <div className="absolute -top-1.5 -right-1.5 w-5 h-5 rounded-full bg-foreground text-background flex items-center justify-center">
          <Pin size={9} className="rotate-45" />
        </div>
      )}

      <div className="flex items-start justify-between gap-3 mb-1.5 flex-wrap">
        <div className={`flex items-center gap-1.5 text-[10.5px] ${cfg.tone}`}>
          {cfg.icon}
          <span className="font-medium">{cfg.label}</span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="px-2 py-0.5 rounded-md bg-muted text-[10px] font-mono text-foreground/80 border border-border">
            {d.display_id}
          </span>
          {d.tag && (
            <span
              className={`px-2 py-0.5 rounded-md text-[10px] font-medium border ${
                tagStyles[d.tag] ?? "bg-muted text-muted-foreground border-border"
              }`}
            >
              {d.tag}
            </span>
          )}
        </div>
      </div>

      <h4 className="text-[13.5px] font-semibold text-foreground leading-snug mb-1.5">
        {d.title}
      </h4>
      {d.supersedes && (
        <div className="flex items-center gap-1.5 text-[10.5px] text-muted-foreground mb-1.5">
          <Replace size={10} />
          <span>
            Replaces{" "}
            {replaced ? (
              <span className="font-mono text-foreground/70">{replaced.display_id}</span>
            ) : (
              "an earlier decision"
            )}
            {replaced?.title ? <> — <span className="italic">{replaced.title}</span></> : null}
          </span>
        </div>
      )}
      <p className="text-[12px] text-foreground/85 leading-relaxed mb-2 whitespace-pre-line">{d.detail}</p>
      {d.why && (
        <div className="text-[11.5px] text-muted-foreground leading-relaxed pl-3 border-l-2 border-border mb-3">
          <span className="font-medium text-foreground/70">Why: </span>
          {d.why}
        </div>
      )}

      {affectedTasks.length > 0 && (
        <div className="flex items-center gap-1.5 flex-wrap mb-3">
          <span className="flex items-center gap-1 text-[10px] uppercase tracking-wider text-muted-foreground font-medium">
            <Link2 size={9} /> Affects
          </span>
          {affectedTasks.map((t) => (
            <span
              key={t.id}
              className="px-2 py-0.5 rounded-md bg-muted text-[10.5px] text-foreground/80 border border-border flex items-center gap-1"
              title={t.title}
            >
              <span className="font-mono text-muted-foreground">{t.display_id}</span>
              <span className="truncate max-w-[140px]">{t.title}</span>
            </span>
          ))}
        </div>
      )}

      {isOpen ? (
        <div className="pt-3 border-t border-amber-200 space-y-2">
          <p className="flex items-center gap-1 text-[10px] uppercase tracking-wide text-amber-800 font-medium">
            <AlertTriangle size={9} />
            Coding agent paused on the related task — needs your judgment
          </p>
          {onDiscuss && (
            <button
              className="w-full flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg bg-primary text-primary-foreground text-[11px] font-medium hover:bg-primary/90 transition-colors"
              onClick={() => onDiscuss(d)}
            >
              <Sparkles size={11} />
              Discuss with Maya
            </button>
          )}
        </div>
      ) : (
        onDiscuss && (
          <div className="flex items-center gap-2 pt-2 border-t border-border">
            <button
              className="px-3 py-1.5 rounded-md text-[10.5px] font-medium text-muted-foreground hover:text-foreground hover:bg-muted transition-colors flex items-center gap-1.5"
              onClick={() => onDiscuss(d)}
            >
              <RotateCcw size={10} />
              Revisit
            </button>
            <button
              className="px-3 py-1.5 rounded-md text-[10.5px] font-medium text-muted-foreground hover:text-foreground hover:bg-muted transition-colors flex items-center gap-1.5"
              onClick={() => onDiscuss(d)}
            >
              <Sparkles size={10} />
              Discuss
            </button>
          </div>
        )
      )}
    </div>
  );
};

interface Props {
  decisions: Decision[];
  tasks: Task[];
  onDiscuss?: (d: Decision) => void;
}

export function DecisionsTab({ decisions, tasks, onDiscuss }: Props) {
  const [filter, setFilter] = useState<FilterId>("all");
  const [search, setSearch] = useState("");

  // Index by uuid so cards can resolve their `supersedes` pointer cheaply.
  // Note: superseded rows are filtered out server-side by default, so the
  // pointed-to row may not be in the local list — Card handles that gracefully.
  const decisionsById = useMemo(
    () => new Map(decisions.map((d) => [d.id, d])),
    [decisions],
  );

  const open = useMemo(() => decisions.filter((d) => d.status === "open"), [decisions]);
  const pinned = useMemo(
    () => decisions.filter((d) => d.status === "decided" && d.pinned),
    [decisions],
  );
  const recent = useMemo(
    () => decisions.filter((d) => d.status === "decided" && !d.pinned),
    [decisions],
  );

  const matches = (d: Decision) => {
    const q = search.trim().toLowerCase();
    if (q) {
      const hay = `${d.title} ${d.detail} ${d.why} ${d.tag ?? ""} ${d.display_id}`.toLowerCase();
      if (!hay.includes(q)) return false;
    }
    if (filter === "all") return true;
    if (filter === "open") return d.status === "open";
    if (filter === "pinned") return d.pinned === true;
    return d.tag === filter;
  };

  const fOpen = open.filter(matches);
  const fPinned = pinned.filter(matches);
  const fRecent = recent.filter(matches);
  const total = fOpen.length + fPinned.length + fRecent.length;

  return (
    <div className="h-full flex flex-col">
      <div className="px-5 py-4 border-b border-border flex items-center justify-between flex-shrink-0">
        <div className="flex items-center gap-2">
          <History size={14} className="text-muted-foreground" />
          <h3 className="text-sm font-semibold text-foreground">decisions.md</h3>
          <span className="px-2 py-0.5 rounded-md bg-muted text-muted-foreground text-[10px] font-medium border border-border">
            {total} of {decisions.length}
          </span>
        </div>
      </div>

      <div className="px-5 pt-4 pb-3 border-b border-border flex flex-col gap-2.5 flex-shrink-0">
        <div className="flex items-center gap-2 bg-muted/40 rounded-lg border border-border px-2.5 py-1.5">
          <Search size={12} className="text-muted-foreground" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search decisions by title, reason, or tag…"
            className="flex-1 bg-transparent outline-none text-[12px] text-foreground placeholder:text-muted-foreground"
          />
        </div>
        <div className="flex flex-wrap gap-1.5">
          {filters.map((f) => {
            const active = filter === f.id;
            return (
              <button
                key={f.id}
                onClick={() => setFilter(f.id)}
                className={`px-2.5 py-1 rounded-md text-[10.5px] font-medium border transition-colors ${
                  active
                    ? "bg-foreground text-background border-foreground"
                    : "bg-card text-muted-foreground border-border hover:text-foreground hover:bg-muted"
                }`}
              >
                {f.label}
                {f.id === "open" && open.length > 0 && (
                  <span
                    className={`ml-1 px-1.5 rounded ${
                      active ? "bg-background/20" : "bg-amber-100 text-amber-800"
                    }`}
                  >
                    {open.length}
                  </span>
                )}
              </button>
            );
          })}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-6 py-6">
        <div className="max-w-[680px] mx-auto space-y-6">
          {decisions.length > 0 && (
            <p className="text-[11px] text-muted-foreground leading-relaxed italic">
              Stack picks + load-bearing constraints your coding agent reads as
              ground truth via MCP. Feature lists and UI structure live in the PRD;
              runtime "do not" rules live in Guardrails.
            </p>
          )}

          {fOpen.length > 0 && (
            <section>
              <div className="flex items-center gap-2 mb-3">
                <AlertTriangle size={12} className="text-amber-600" />
                <h2 className="text-[11px] font-semibold uppercase tracking-wider text-amber-700">
                  Open questions · need your attention
                </h2>
                <span className="px-1.5 py-0.5 rounded-full bg-amber-100 text-amber-800 text-[10px] font-semibold">
                  {fOpen.length}
                </span>
              </div>
              <div className="space-y-3">
                {fOpen.map((d) => (
                  <Card key={d.id} d={d} tasks={tasks} decisionsById={decisionsById} onDiscuss={onDiscuss} />
                ))}
              </div>
            </section>
          )}

          {fPinned.length > 0 && (
            <section>
              <div className="flex items-center gap-2 mb-3">
                <Pin size={11} className="text-foreground rotate-45" />
                <h2 className="text-[11px] font-semibold uppercase tracking-wider text-foreground">
                  Pinned · foundational decisions
                </h2>
                <span className="px-1.5 py-0.5 rounded-full bg-muted text-muted-foreground text-[10px] font-semibold">
                  {fPinned.length}
                </span>
              </div>
              <div className="space-y-3">
                {fPinned.map((d) => (
                  <Card key={d.id} d={d} tasks={tasks} decisionsById={decisionsById} onDiscuss={onDiscuss} />
                ))}
              </div>
            </section>
          )}

          {fRecent.length > 0 && (
            <section>
              <div className="flex items-center gap-2 mb-3">
                <h2 className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                  Recent decisions · newest at top
                </h2>
                <span className="px-1.5 py-0.5 rounded-full bg-muted text-muted-foreground text-[10px] font-semibold">
                  {fRecent.length}
                </span>
              </div>
              <div className="space-y-3">
                {fRecent.map((d) => (
                  <Card key={d.id} d={d} tasks={tasks} decisionsById={decisionsById} onDiscuss={onDiscuss} />
                ))}
              </div>
            </section>
          )}

          {decisions.length === 0 ? (
            <div className="rounded-xl bg-muted/30 border border-dashed border-border p-8 text-center">
              <p className="text-[12px] font-medium text-foreground/80 mb-1">No decisions yet</p>
              <p className="text-[11px] text-muted-foreground">
                Choices Maya makes (or flags for you) appear here.
              </p>
            </div>
          ) : (
            total === 0 && (
              <div className="rounded-xl bg-muted/30 border border-dashed border-border p-8 text-center">
                <p className="text-[12px] font-medium text-foreground/80 mb-1">No decisions match</p>
                <p className="text-[11px] text-muted-foreground">
                  Try a different filter or clear the search.
                </p>
              </div>
            )
          )}
        </div>
      </div>
    </div>
  );
}
