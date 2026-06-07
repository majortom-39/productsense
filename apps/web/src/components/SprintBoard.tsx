import { useState, useEffect, useMemo } from "react";
import {
  Loader2,
  CheckCircle2,
  Circle,
  FileCode2,
  Ban,
  Link2,
  ChevronRight,
  ChevronDown,
  AlertCircle,
  Check,
  Wrench,
  ClipboardCheck,
  AlertTriangle,
  Key,
  ExternalLink,
  Sparkles,
  MessageSquarePlus,
} from "lucide-react";
import type { Task, TaskStatus, Decision, Sprint } from "@/lib/api";

const lanes: { id: TaskStatus; label: string; tone: string; icon: React.ReactNode }[] = [
  { id: "in_progress", label: "In progress", tone: "text-blue-700",      icon: <Loader2 size={11} className="animate-spin" /> },
  { id: "todo",        label: "To do",       tone: "text-muted-foreground", icon: <Circle size={11} /> },
  { id: "done",        label: "Done",        tone: "text-emerald-700",   icon: <CheckCircle2 size={11} /> },
];

interface Props {
  tasks: Task[];
  /** ALL sprints for the project. SprintBoard owns the selected-sprint state
   *  internally — defaulting to the one with status='active'. Past-MVP we
   *  may add per-user selected-sprint persistence; for now selection is
   *  ephemeral. Accepts the legacy `sprint?` for back-compat with any
   *  caller that still passes a single sprint. */
  sprints?: Sprint[];
  /** @deprecated Pass `sprints` instead. Single-sprint callers still work. */
  sprint?: Sprint | null;
  decisions: Decision[];
  /** Project-level macro (north_star, brief). Shown above the lanes. */
  northStar?: string | null;
  onAdvance?: (taskId: string, next: TaskStatus) => void;
  onDiscussDecision?: (decision: Decision) => void;
  /** "Add this task to chat" — quotes the task into the chat input so the
   *  founder can ask Maya about it (refine scope, mark blocked, etc.). */
  onDiscussTask?: (task: Task) => void;
}

const OpenDecisionChip: React.FC<{ decision: Decision; onClick?: () => void }> = ({
  decision,
  onClick,
}) => (
  <button
    onClick={onClick}
    className="w-full text-left flex items-start gap-2 px-2.5 py-2 rounded-md border bg-amber-50 border-amber-200 text-amber-900 hover:bg-amber-100 transition-colors"
  >
    <AlertCircle size={11} className="flex-shrink-0 mt-0.5" />
    <div className="flex-1 min-w-0">
      <p className="text-[10px] uppercase tracking-wide font-medium leading-none mb-1">
        Needs your judgment with Maya
      </p>
      <p className="text-[11px] leading-snug">
        <span className="font-mono">{decision.display_id}</span> · {decision.title}
      </p>
    </div>
    <ChevronRight size={11} className="flex-shrink-0 mt-0.5 opacity-60" />
  </button>
);

const TaskCard: React.FC<{
  task: Task;
  decisions: Decision[];
  onAdvance?: Props["onAdvance"];
  onDiscussDecision?: Props["onDiscussDecision"];
  onDiscussTask?: Props["onDiscussTask"];
}> = ({ task, decisions, onAdvance, onDiscussDecision, onDiscussTask }) => {
  const isDone = task.status === "done";
  const openDecision = task.open_decision_id
    ? decisions.find((d) => d.id === task.open_decision_id && d.status === "open")
    : null;
  const next: TaskStatus | undefined =
    task.status === "todo" ? "in_progress" : task.status === "in_progress" ? "done" : undefined;

  return (
    <div className="rounded-xl bg-card border border-border p-3 hover:border-border/80 transition-colors space-y-2">
      <div className="flex items-start justify-between gap-2">
        <h4 className="text-[12.5px] font-semibold text-foreground leading-snug flex-1">
          {task.title}
        </h4>
        <span className="text-[10px] text-muted-foreground font-mono flex-shrink-0">
          {task.display_id}
        </span>
      </div>

      {task.goal && (
        <p className="text-[11px] text-foreground/70 leading-relaxed italic">
          <span className="not-italic font-medium text-foreground/60">goal · </span>
          {task.goal}
        </p>
      )}

      {openDecision && (
        <OpenDecisionChip
          decision={openDecision}
          onClick={() => onDiscussDecision?.(openDecision)}
        />
      )}

      {!isDone && task.blocked_by && task.blocked_by.length > 0 && (
        <div className="flex items-center gap-1 text-[10px] text-muted-foreground flex-wrap">
          <Link2 size={9} />
          <span>blocked by</span>
          {task.blocked_by.map((id) => (
            <span key={id} className="font-mono bg-muted/60 px-1 py-0.5 rounded">
              {id}
            </span>
          ))}
        </div>
      )}

      {isDone && task.completion_summary && (
        <div className="px-2.5 py-2 rounded-md bg-emerald-50 border border-emerald-100 text-[11px] text-emerald-900 leading-relaxed">
          <p className="flex items-center gap-1 font-medium text-emerald-700 text-[10px] uppercase tracking-wide mb-1">
            <Check size={9} />
            What was built
          </p>
          {task.completion_summary}
        </div>
      )}

      {!isDone && task.prd_context && (
        <div className="px-2.5 py-1.5 rounded-md bg-primary/5 border border-primary/15 text-[10.5px] text-foreground/80 leading-relaxed">
          <span className="text-primary font-medium">PRD: </span>
          {task.prd_context}
        </div>
      )}

      {/* Tech decisions Maya already locked — coding agent treats as fixed */}
      {!isDone && task.tech_decisions && Object.keys(task.tech_decisions).length > 0 && (
        <div className="px-2.5 py-1.5 rounded-md bg-violet-50 border border-violet-100 text-[10.5px] text-violet-900 leading-relaxed">
          <p className="flex items-center gap-1 font-medium text-violet-700 text-[10px] uppercase tracking-wide mb-1">
            <Wrench size={9} />
            tech (locked)
          </p>
          <ul className="space-y-0.5">
            {Object.entries(task.tech_decisions).map(([k, v]) => (
              <li key={k} className="pl-2 relative">
                <span className="absolute left-0 top-1 w-0.5 h-0.5 rounded-full bg-violet-400" />
                <span className="font-mono text-violet-700">{k}:</span>{" "}
                <span>{typeof v === "string" ? v : JSON.stringify(v)}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Prompt brief — for AI-feature tasks */}
      {!isDone && task.prompt_brief && (
        <div className="px-2.5 py-1.5 rounded-md bg-amber-50 border border-amber-100 text-[10.5px] text-amber-900 leading-relaxed">
          <p className="flex items-center gap-1 font-medium text-amber-700 text-[10px] uppercase tracking-wide mb-1">
            <Sparkles size={9} />
            prompt brief — expand before shipping
          </p>
          <p className="leading-snug">{task.prompt_brief}</p>
        </div>
      )}

      {/* Verification steps */}
      {!isDone && task.verification && task.verification.length > 0 && (
        <details className="text-[10.5px]">
          <summary className="cursor-pointer text-foreground/70 hover:text-foreground flex items-center gap-1 font-medium uppercase tracking-wide text-[10px]">
            <ClipboardCheck size={9} className="text-emerald-600" />
            How to verify ({task.verification.length})
          </summary>
          <ol className="mt-1 pl-4 space-y-0.5 text-foreground/75">
            {task.verification.map((v, i) => (
              <li key={i} className="leading-snug">{v}</li>
            ))}
          </ol>
        </details>
      )}

      {/* Pitfalls */}
      {!isDone && task.pitfalls && task.pitfalls.length > 0 && (
        <details className="text-[10.5px]">
          <summary className="cursor-pointer text-rose-700 hover:text-rose-900 flex items-center gap-1 font-medium uppercase tracking-wide text-[10px]">
            <AlertTriangle size={9} />
            Pitfalls ({task.pitfalls.length})
          </summary>
          <ul className="mt-1 pl-4 space-y-0.5 text-foreground/75">
            {task.pitfalls.map((p, i) => (
              <li key={i} className="leading-snug pl-2 relative">
                <span className="absolute left-0 top-1 w-0.5 h-0.5 rounded-full bg-rose-400" />
                {p}
              </li>
            ))}
          </ul>
        </details>
      )}

      {/* Secrets required */}
      {!isDone && task.secrets_required && task.secrets_required.length > 0 && (
        <div className="flex items-center gap-1 flex-wrap">
          <Key size={9} className="text-muted-foreground" />
          {task.secrets_required.map((s) => (
            <span
              key={s}
              className="text-[9.5px] font-mono text-amber-800 bg-amber-50 border border-amber-100 px-1.5 py-0.5 rounded"
            >
              {s}
            </span>
          ))}
        </div>
      )}

      {/* References */}
      {!isDone && task.refs && task.refs.length > 0 && (
        <div className="flex flex-wrap gap-1.5 pt-0.5">
          {task.refs.map((r, i) => (
            <a
              key={i}
              href={r.url}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1 text-[10px] text-blue-700 hover:underline"
            >
              <ExternalLink size={9} />
              {r.label}
            </a>
          ))}
        </div>
      )}

      {/* Complexity badge */}
      {task.complexity && (
        <span
          className={`inline-block text-[9.5px] uppercase tracking-wide font-medium px-1.5 py-0.5 rounded border ${
            task.complexity === "high"
              ? "bg-rose-50 text-rose-700 border-rose-100"
              : task.complexity === "medium"
              ? "bg-amber-50 text-amber-700 border-amber-100"
              : "bg-emerald-50 text-emerald-700 border-emerald-100"
          }`}
        >
          {task.complexity} complexity
        </span>
      )}

      {!isDone && task.do_not && task.do_not.length > 0 && (
        <div className="px-2.5 py-1.5 rounded-md bg-rose-50 border border-rose-100 text-[10.5px] text-rose-900 leading-relaxed">
          <p className="flex items-center gap-1 font-medium text-rose-700 text-[10px] uppercase tracking-wide mb-1">
            <Ban size={9} />
            do not
          </p>
          <ul className="space-y-0.5">
            {task.do_not.map((d, i) => (
              <li key={i} className="pl-2 relative">
                <span className="absolute left-0 top-1 w-0.5 h-0.5 rounded-full bg-rose-400" />
                {d}
              </li>
            ))}
          </ul>
        </div>
      )}

      {!isDone && task.agent_note && (
        <div className="px-2.5 py-1.5 rounded-md bg-muted/60 border border-border text-[10.5px] text-muted-foreground leading-relaxed italic">
          <span className="not-italic font-medium text-foreground/70">agent · </span>
          {task.agent_note}
        </div>
      )}

      {task.files_touched && task.files_touched.length > 0 && (
        <div className="flex items-center gap-1 flex-wrap pt-1">
          <FileCode2 size={9} className="text-muted-foreground" />
          {task.files_touched.slice(0, 3).map((f, i) => (
            <span
              key={i}
              className="text-[9.5px] font-mono text-muted-foreground bg-muted/60 px-1.5 py-0.5 rounded"
            >
              {f}
            </span>
          ))}
          {task.files_touched.length > 3 && (
            <span className="text-[9.5px] text-muted-foreground">
              +{task.files_touched.length - 3}
            </span>
          )}
        </div>
      )}

      <div className="flex items-center justify-between gap-2 pt-1">
        {next && onAdvance ? (
          <button
            onClick={() => onAdvance(task.id, next)}
            className="text-[10.5px] text-primary font-medium hover:underline"
          >
            Mark {next === "in_progress" ? "in progress" : "done"} →
          </button>
        ) : (
          <span />
        )}
        {onDiscussTask && (
          <button
            onClick={() => onDiscussTask(task)}
            title="Quote this task in the chat — ask Maya to refine scope, mark blocked, etc."
            className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[10.5px] font-medium text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
          >
            <MessageSquarePlus size={10} />
            Add to chat
          </button>
        )}
      </div>
    </div>
  );
};

const EmptyLane: React.FC<{ laneId: TaskStatus }> = ({ laneId }) => {
  const m =
    laneId === "in_progress"
      ? { headline: "Idle", sub: "No task is being worked on right now." }
      : laneId === "todo"
      ? { headline: "Queue is clear", sub: "No upcoming tasks." }
      : { headline: "Nothing finished yet", sub: "Completed tasks will land here." };
  return (
    <div className="rounded-xl bg-card/60 border border-dashed border-border p-4 text-center">
      <p className="text-[11px] font-medium text-foreground/80 mb-1">{m.headline}</p>
      <p className="text-[10.5px] text-muted-foreground leading-relaxed">{m.sub}</p>
    </div>
  );
};

const DoneCollapsedList: React.FC<{ tasks: Task[]; onExpand: () => void }> = ({
  tasks,
  onExpand,
}) => {
  if (tasks.length === 0) return <EmptyLane laneId="done" />;
  return (
    <button
      onClick={onExpand}
      className="w-full text-left rounded-xl bg-card border border-border p-2.5 hover:border-border/80 hover:bg-muted/40 transition-colors space-y-1.5"
    >
      {tasks.map((t) => (
        <div key={t.id} className="flex items-start gap-2 text-[11px] text-foreground/80">
          <CheckCircle2 size={11} className="text-emerald-600 flex-shrink-0 mt-0.5" />
          <span className="flex-1 leading-snug truncate">{t.title}</span>
          <span className="text-[9.5px] text-muted-foreground font-mono flex-shrink-0">
            {t.display_id}
          </span>
        </div>
      ))}
      <p className="text-[10px] text-muted-foreground pt-1.5 border-t border-border mt-1.5 flex items-center gap-1">
        <ChevronRight size={9} />
        Click to see details
      </p>
    </button>
  );
};

export function SprintBoard({
  tasks,
  sprints: sprintsProp,
  sprint: sprintProp,
  decisions,
  northStar,
  onAdvance,
  onDiscussDecision,
  onDiscussTask,
}: Props) {
  // Normalise the input: prefer the array, fall back to the legacy single-sprint prop.
  const allSprints = useMemo<Sprint[]>(() => {
    if (sprintsProp && sprintsProp.length > 0) {
      return [...sprintsProp].sort((a, b) => a.number - b.number);
    }
    return sprintProp ? [sprintProp] : [];
  }, [sprintsProp, sprintProp]);

  // Default selection: the active sprint (status='active'), else the first by number.
  const defaultSprintId =
    allSprints.find((s) => s.status === "active")?.id ?? allSprints[0]?.id ?? null;
  const [selectedSprintId, setSelectedSprintId] = useState<string | null>(defaultSprintId);

  // If the underlying sprints list changes (e.g. Kai generated more), reselect
  // the active one unless the user explicitly picked something different.
  useEffect(() => {
    if (!selectedSprintId || !allSprints.some((s) => s.id === selectedSprintId)) {
      setSelectedSprintId(defaultSprintId);
    }
  }, [defaultSprintId, selectedSprintId, allSprints]);

  const sprint = allSprints.find((s) => s.id === selectedSprintId) ?? null;
  // Tasks belonging to the selected sprint only. We never mix tasks across
  // sprints — each sprint is independently shippable.
  const sprintTasks = useMemo(
    () => (sprint ? tasks.filter((t) => t.sprint_id === sprint.id) : tasks),
    [tasks, sprint],
  );

  const [doneOpen, setDoneOpen] = useState(false);
  const inProgressCount = sprintTasks.filter((t) => t.status === "in_progress").length;
  const techStack = (sprint?.tech_stack ?? {}) as Record<string, unknown>;
  const stackPills: string[] = [];
  if (typeof techStack.framework === "string") stackPills.push(techStack.framework);
  if (Array.isArray(techStack.services)) {
    for (const s of techStack.services as Array<Record<string, unknown>>) {
      if (typeof s.name === "string") stackPills.push(s.name as string);
    }
  }

  if (allSprints.length === 0 || tasks.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-2 text-center px-6">
        <p className="text-sm font-medium text-foreground">Sprint board empty</p>
        <p className="text-xs text-muted-foreground max-w-[260px] leading-relaxed">
          Tasks appear here once Maya generates a sprint from the PRD.
        </p>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col">
      <div className="px-5 py-4 border-b border-border flex-shrink-0 space-y-2.5">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <h3 className="text-[14px] font-semibold text-foreground leading-tight">
              {sprint ? `${sprint.name}${sprint.subtitle ? ` · ${sprint.subtitle}` : ""}` : "Sprint"}
            </h3>
            {northStar && (
              <p className="text-[11.5px] text-foreground/70 italic mt-1 leading-snug">
                <span className="text-primary font-medium not-italic">★ </span>
                {northStar}
              </p>
            )}
          </div>
          {inProgressCount > 0 && (
            <div className="flex items-center gap-2 flex-shrink-0 px-3 py-1.5 rounded-xl bg-emerald-50 border border-emerald-100">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
              <span className="text-[11px] font-medium text-emerald-800 leading-none">
                Coding agent live
              </span>
              <span className="text-[10.5px] text-emerald-700/70 leading-none">
                · {inProgressCount} in progress
              </span>
            </div>
          )}
        </div>
        {stackPills.length > 0 && (
          <div className="flex items-center gap-1.5 flex-wrap">
            <span className="text-[10px] uppercase tracking-wider text-muted-foreground font-medium">
              Stack
            </span>
            {stackPills.map((p) => (
              <span
                key={p}
                className="text-[10.5px] font-mono text-foreground/80 bg-muted px-2 py-0.5 rounded-md border border-border"
              >
                {p}
              </span>
            ))}
            {sprint?.repo_layout && (
              <details className="ml-2">
                <summary className="text-[10.5px] text-muted-foreground hover:text-foreground cursor-pointer">
                  repo layout
                </summary>
                <pre className="mt-2 text-[10px] font-mono text-foreground/75 bg-muted/40 border border-border rounded-md p-3 whitespace-pre overflow-x-auto">
                  {sprint.repo_layout}
                </pre>
              </details>
            )}
          </div>
        )}

        {/* Sprint switcher: only renders when there are 2+ sprints (i.e. Kai
            produced a multi-sprint backlog). Status pill on each tab marks
            the currently-active sprint distinct from queued ones. */}
        {allSprints.length > 1 && (
          <div className="flex items-center gap-1 pt-1 -mb-1 overflow-x-auto">
            {allSprints.map((s) => {
              const isSelected = s.id === selectedSprintId;
              const sTaskCount = tasks.filter((t) => t.sprint_id === s.id).length;
              return (
                <button
                  key={s.id}
                  onClick={() => setSelectedSprintId(s.id)}
                  className={`flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[11px] font-medium border transition-colors whitespace-nowrap ${
                    isSelected
                      ? "bg-foreground text-background border-foreground"
                      : "bg-card text-muted-foreground border-border hover:text-foreground hover:bg-muted"
                  }`}
                  title={s.subtitle ?? undefined}
                >
                  <span>Sprint {s.number}</span>
                  {s.status === "active" && (
                    <span
                      className={`w-1.5 h-1.5 rounded-full ${
                        isSelected ? "bg-emerald-300" : "bg-emerald-500 animate-pulse"
                      }`}
                      title="Active sprint"
                    />
                  )}
                  <span
                    className={`px-1.5 rounded-full text-[10px] ${
                      isSelected ? "bg-background/20" : "bg-muted-foreground/10"
                    }`}
                  >
                    {sTaskCount}
                  </span>
                </button>
              );
            })}
          </div>
        )}
      </div>

      <div className="flex-1 overflow-x-auto overflow-y-hidden">
        <div className="flex gap-3 px-4 py-4 h-full min-w-max items-stretch">
          {lanes.map((lane) => {
            const laneTasks = sprintTasks.filter((t) => t.status === lane.id);
            const isDone = lane.id === "done";
            const isCollapsed = isDone && !doneOpen;

            return (
              <div
                key={lane.id}
                className={`flex-shrink-0 flex flex-col ${isCollapsed ? "w-[200px]" : "w-[300px]"}`}
              >
                <div className="flex items-center justify-between mb-2 px-1">
                  <button
                    onClick={() => isDone && setDoneOpen(!doneOpen)}
                    className={`flex items-center gap-1.5 ${lane.tone} ${
                      isDone ? "cursor-pointer hover:opacity-80" : ""
                    }`}
                  >
                    {isDone && (doneOpen ? <ChevronDown size={11} /> : <ChevronRight size={11} />)}
                    {!isDone && lane.icon}
                    {isDone && <CheckCircle2 size={11} />}
                    <span className="text-[11px] font-semibold uppercase tracking-wide">{lane.label}</span>
                  </button>
                  <span className="text-[11px] font-semibold px-2 py-0.5 rounded-full min-w-[22px] text-center bg-muted text-muted-foreground">
                    {laneTasks.length}
                  </span>
                </div>
                <div className="flex-1 overflow-y-auto space-y-2 pb-1 pr-1 px-1">
                  {isCollapsed ? (
                    <DoneCollapsedList tasks={laneTasks} onExpand={() => setDoneOpen(true)} />
                  ) : laneTasks.length === 0 ? (
                    <EmptyLane laneId={lane.id} />
                  ) : (
                    laneTasks.map((t) => (
                      <TaskCard
                        key={t.id}
                        task={t}
                        decisions={decisions}
                        onAdvance={onAdvance}
                        onDiscussDecision={onDiscussDecision}
                        onDiscussTask={onDiscussTask}
                      />
                    ))
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
