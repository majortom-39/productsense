import { CheckCircle2, Circle, Loader2, ListChecks } from "lucide-react";
import type { Todo } from "@/hooks/useMayaSession";

interface Props {
  todos: Todo[];
}

/** PlanTab — Maya's live plan, mirrored from her `write_todos` tool
 *  (deepagent harness). This is the founder-readable view of how Maya is
 *  sequencing the work: each item is a plain-language step she's about to
 *  do, is doing, or has done. It updates live as the turn runs and persists
 *  for the session via the SSE `todos` event.
 *
 *  No time, no estimates — just what's done vs. what's next (founder hard
 *  rule). When Maya hasn't planned anything yet the tab shows an empty hint. */
export function PlanTab({ todos }: Props) {
  const done = todos.filter((t) => t.status === "completed").length;
  const total = todos.length;

  return (
    <div className="h-full flex flex-col">
      <div className="px-5 py-4 border-b border-border flex items-center justify-between flex-shrink-0">
        <div className="flex items-center gap-2">
          <ListChecks size={14} className="text-muted-foreground" />
          <h3 className="text-sm font-semibold text-foreground">Plan</h3>
          {total > 0 && (
            <span className="px-2 py-0.5 rounded-md bg-muted text-muted-foreground text-[10px] font-medium border border-border">
              {done} of {total} done
            </span>
          )}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-6 py-6">
        <div className="max-w-[680px] mx-auto">
          {total === 0 ? (
            <div className="rounded-xl bg-muted/30 border border-dashed border-border p-8 text-center">
              <p className="text-[12px] font-medium text-foreground/80 mb-1">
                No plan yet
              </p>
              <p className="text-[11px] text-muted-foreground leading-relaxed">
                When Maya maps out the steps for a piece of work, they show up
                here — done, in progress, and what's next.
              </p>
            </div>
          ) : (
            <>
              <p className="text-[11px] text-muted-foreground leading-relaxed italic mb-4">
                How Maya is sequencing the work right now. This updates live as
                she goes.
              </p>
              <ol className="space-y-1.5">
                {todos.map((t, i) => (
                  <PlanRow key={i} todo={t} />
                ))}
              </ol>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

const PlanRow: React.FC<{ todo: Todo }> = ({ todo }) => {
  const isDone = todo.status === "completed";
  const isActive = todo.status === "in_progress";

  return (
    <li
      className={`flex items-start gap-2.5 rounded-xl border px-3.5 py-2.5 transition-colors ${
        isActive
          ? "bg-blue-50/60 border-blue-200"
          : isDone
          ? "bg-card border-border"
          : "bg-card border-border"
      }`}
    >
      <span className="mt-0.5 shrink-0">
        {isDone ? (
          <CheckCircle2 size={15} className="text-emerald-600" />
        ) : isActive ? (
          <Loader2 size={15} className="text-blue-600 animate-spin" />
        ) : (
          <Circle size={15} className="text-muted-foreground/50" />
        )}
      </span>
      <span
        className={`text-[13px] leading-snug ${
          isDone
            ? "text-muted-foreground line-through decoration-muted-foreground/40"
            : isActive
            ? "text-foreground font-medium"
            : "text-foreground/85"
        }`}
      >
        {todo.content}
      </span>
    </li>
  );
};
