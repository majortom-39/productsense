import { useMemo } from "react";
import {
  Activity,
  Loader2,
  CheckCircle2,
  AlertTriangle,
  HelpCircle,
  Zap,
} from "lucide-react";
import type { ChatItem } from "@/hooks/useMayaSession";

/** ActivityTab — a behind-the-scenes feed of what Maya actually did this
 *  session: which specialists she dispatched, and the state changes that
 *  landed (decisions logged, cards pinned, stages locked). The chat shows
 *  Maya's voice; this shows her *work*. It's the founder's audit trail for
 *  "wait, when did that happen / who decided that?".
 *
 *  Fed by maya.items (the same chronological stream the chat renders) —
 *  we just project out the agent_call + state_update entries and drop the
 *  prose messages. No timestamps shown (founder hard rule: no time as a
 *  factor); order alone tells the story. */

interface Props {
  items: ChatItem[];
}

// Specialist display names. Keyed by the BARE name (live SSE keys cards by
// `subagent` = "iris"); hydrated entries arrive as "invoke_iris" so we strip
// the prefix before lookup.
const SPECIALIST_PRETTY: Record<string, string> = {
  iris: "Iris · Problem Validator",
  aiden: "Aiden · Competitor Mapper",
  hugo: "Hugo · Risk Researcher",
  zara: "Zara · User Researcher",
  theo: "Theo · Tech Advisor",
  nora: "Nora · PRD Writer",
  kai: "Kai · Sprint Planner",
  wes: "Wes · Guardrail Proposer",
};

function prettyAgent(tool: string): string {
  const bare = tool.startsWith("invoke_") ? tool.slice("invoke_".length) : tool;
  return SPECIALIST_PRETTY[bare] ?? bare.charAt(0).toUpperCase() + bare.slice(1);
}

type AgentStatus = "running" | "complete" | "clarification_needed" | "error";

const agentStatusIcon = (status: AgentStatus) => {
  switch (status) {
    case "running":
      return <Loader2 size={13} className="text-blue-600 animate-spin" />;
    case "clarification_needed":
      return <HelpCircle size={13} className="text-amber-600" />;
    case "error":
      return <AlertTriangle size={13} className="text-rose-600" />;
    default:
      return <CheckCircle2 size={13} className="text-emerald-600" />;
  }
};

const agentStatusLabel = (status: AgentStatus): string => {
  switch (status) {
    case "running":
      return "Working…";
    case "clarification_needed":
      return "Asked Maya a question";
    case "error":
      return "Hit a problem";
    default:
      return "Done";
  }
};

export function ActivityTab({ items }: Props) {
  // Project out just the work entries (dispatches + state changes), dropping
  // chat prose. Preserve the original chronological order.
  const feed = useMemo(
    () =>
      items.filter(
        (it) => it.kind === "agent_call" || it.kind === "state_update",
      ),
    [items],
  );

  return (
    <div className="h-full flex flex-col">
      <div className="px-5 py-4 border-b border-border flex items-center justify-between flex-shrink-0">
        <div className="flex items-center gap-2">
          <Activity size={14} className="text-muted-foreground" />
          <h3 className="text-sm font-semibold text-foreground">Activity</h3>
          {feed.length > 0 && (
            <span className="px-2 py-0.5 rounded-md bg-muted text-muted-foreground text-[10px] font-medium border border-border">
              {feed.length}
            </span>
          )}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-6 py-6">
        <div className="max-w-[680px] mx-auto">
          {feed.length === 0 ? (
            <div className="rounded-xl bg-muted/30 border border-dashed border-border p-8 text-center">
              <p className="text-[12px] font-medium text-foreground/80 mb-1">
                Nothing yet
              </p>
              <p className="text-[11px] text-muted-foreground leading-relaxed">
                As Maya pulls in her team and locks things down, every step
                shows up here — who she called and what changed.
              </p>
            </div>
          ) : (
            <ol className="relative space-y-2.5 before:absolute before:left-[6px] before:top-1 before:bottom-1 before:w-px before:bg-border">
              {feed.map((it) => {
                if (it.kind === "agent_call") {
                  const status = it.status as AgentStatus;
                  return (
                    <li key={it.id} className="relative flex items-start gap-3 pl-6">
                      <span className="absolute left-0 top-0.5 bg-card">
                        {agentStatusIcon(status)}
                      </span>
                      <div className="min-w-0 flex-1 rounded-xl border border-border bg-card px-3.5 py-2.5">
                        <div className="flex items-center justify-between gap-2 flex-wrap">
                          <span className="text-[12.5px] font-medium text-foreground leading-snug">
                            {prettyAgent(it.tool)}
                          </span>
                          <span
                            className={`text-[10px] font-medium ${
                              status === "running"
                                ? "text-blue-600"
                                : status === "clarification_needed"
                                ? "text-amber-700"
                                : status === "error"
                                ? "text-rose-600"
                                : "text-muted-foreground"
                            }`}
                          >
                            {agentStatusLabel(status)}
                          </span>
                        </div>
                        {it.turns.length > 1 && (
                          <p className="text-[10.5px] text-muted-foreground mt-0.5">
                            {it.turns.length} rounds with Maya
                          </p>
                        )}
                      </div>
                    </li>
                  );
                }
                // state_update
                const isError = it.status === "error";
                const isRefused = it.status === "stage_refused";
                return (
                  <li key={it.id} className="relative flex items-start gap-3 pl-6">
                    <span className="absolute left-0 top-0.5 bg-card">
                      {isError || isRefused ? (
                        <AlertTriangle size={13} className="text-amber-600" />
                      ) : (
                        <Zap size={13} className="text-violet-500" />
                      )}
                    </span>
                    <div className="min-w-0 flex-1 px-1 py-1">
                      <span className="text-[12px] text-foreground/85 leading-snug">
                        {it.label}
                      </span>
                      {it.summary && (
                        <p className="text-[11px] text-muted-foreground leading-snug mt-0.5 truncate">
                          {it.summary}
                        </p>
                      )}
                    </div>
                  </li>
                );
              })}
            </ol>
          )}
        </div>
      </div>
    </div>
  );
}
