import { useEffect, useMemo, useState } from "react";
import { Search, FileText, KanbanSquare, History, ChevronLeft, ChevronRight, ShieldAlert, Layout, Lightbulb, ListChecks, Activity } from "lucide-react";
import { DiscoveryTab } from "@/components/DiscoveryTab";
import { ScreensTab } from "@/components/ScreensTab";
import { PrdViewer } from "@/components/PrdViewer";
import { SprintBoard } from "@/components/SprintBoard";
import { DecisionsTab } from "@/components/DecisionsTab";
import { GuardrailsTab } from "@/components/GuardrailsTab";
import { PlanTab } from "@/components/PlanTab";
import { SolutionsTab } from "@/components/SolutionsTab";
import { ActivityTab } from "@/components/ActivityTab";
import type { Decision, Prd, DiscoveryArtifact, Task, TaskStatus, Sprint, Solution, Feature, ReviewItem } from "@/lib/api";
import type { ChatItem, Todo } from "@/hooks/useMayaSession";

type Tab =
  | "plan"
  | "discovery"
  | "screens"
  | "solutions"
  | "prd"
  | "decisions"
  | "guardrails"
  | "sprint"
  | "activity";

interface Props {
  discovery: DiscoveryArtifact[];
  prd: Prd | null;
  tasks: Task[];
  /** All sprints for the project. SprintBoard switches between them. */
  sprints: Sprint[];
  decisions: Decision[];
  /** Candidate approaches Maya weighed (product-arc §6). */
  solutions: Solution[];
  /** Capabilities that fell out of the chosen solution + the MVP cut. */
  features: Feature[];
  /** Nodes the coherence engine flagged for another look. Surfaced as
   *  attention badges on the tabs they belong to. */
  reviews: ReviewItem[];
  /** Maya's live chronological work stream (same source as the chat) —
   *  the Activity tab projects out her dispatches + state changes. */
  agentRuns: ChatItem[];
  /** Maya's live plan, mirrored from write_todos. Drives the Plan tab. */
  todos: Todo[];
  /** Project-level macro — passed to SprintBoard. */
  northStar?: string | null;
  /** Whether the chat panel is currently visible. The button on this
   *  workspace's left edge always toggles the CHAT (not the workspace
   *  itself) — symmetric to the chat header's button which toggles
   *  the workspace. Chevron direction reflects which way the divider
   *  moves on click. */
  chatOpen?: boolean;
  onToggleChat?: () => void;
  /** Generic "quote this into chat" — used by PRD selection + per-section
   *  PRD button + decision Discuss + discovery card Add to chat + sprint
   *  task Add to chat. All four panels funnel through this one path so the
   *  ChatPanel always knows what's coming in via its `prefillText` prop. */
  onAskMaya: (text: string) => void;
  onTaskAdvance: (taskId: string, next: TaskStatus) => void;
}

function countPrdSections(md: string | undefined): number {
  if (!md) return 0;
  return (md.match(/^##\s+.+/gm) ?? []).length;
}

export function RightPanel({
  discovery,
  prd,
  tasks,
  sprints,
  decisions,
  solutions,
  features,
  reviews,
  agentRuns,
  todos,
  northStar,
  chatOpen,
  onToggleChat,
  onAskMaya,
  onTaskAdvance,
}: Props) {
  // Guardrails are decisions with tag='guardrail'. Split them out so each
  // tab is focused: Decisions = judgment calls, Guardrails = rules.
  const guardrails = useMemo(
    () => decisions.filter((d) => d.tag === "guardrail" && d.status === "decided"),
    [decisions],
  );
  const decisionsExGuardrails = useMemo(
    () => decisions.filter((d) => d.tag !== "guardrail"),
    [decisions],
  );
  const openDecisions = decisionsExGuardrails.filter((d) => d.status === "open").length;
  const prdSectionCount = countPrdSections(prd?.body_md);
  const [activeTab, setActiveTab] = useState<Tab>("discovery");

  // Auto-jump on first appearance of major artifacts. Each guard only fires
  // when the user is still on an "earlier" tab — once they manually navigate
  // away (e.g. back to Discovery) we leave them alone.
  useEffect(() => {
    if (prd && (activeTab === "discovery" || activeTab === "screens")) setActiveTab("prd");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [prd?.id]);
  useEffect(() => {
    if (tasks.length > 0 && (activeTab === "discovery" || activeTab === "screens" || activeTab === "prd")) {
      setActiveTab("sprint");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tasks.length > 0]);

  // Screens tab is fed by wireframe_flow artifacts; the Discovery feed shows
  // everything else. Split so UX walkthroughs get their own room.
  const screenFlows = useMemo(
    () => discovery.filter((r) => r.render_kind === "wireframe_flow"),
    [discovery],
  );
  const discoveryExFlows = useMemo(
    () => discovery.filter((r) => r.render_kind !== "wireframe_flow"),
    [discovery],
  );
  // First flow drawn → jump to Screens so the founder sees it immediately.
  const firstFlowId = useMemo(() => screenFlows[0]?.id ?? null, [screenFlows]);
  useEffect(() => {
    if (firstFlowId && activeTab === "discovery") setActiveTab("screens");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [firstFlowId]);

  // Coherence-engine review flags, bucketed by the surface they live on, so
  // each tab can show an amber attention badge when one of its nodes was
  // marked needs_review. Maps node `type` → tab.
  const reviewCounts = useMemo(() => {
    const c = { discovery: 0, solutions: 0, prd: 0, decisions: 0, sprint: 0 };
    for (const r of reviews) {
      switch (r.type) {
        case "artifact":
          c.discovery++;
          break;
        case "solution":
        case "feature":
          c.solutions++;
          break;
        case "prd_section":
          c.prd++;
          break;
        case "decision":
        case "guardrail":
          c.decisions++;
          break;
        case "task":
          c.sprint++;
          break;
      }
    }
    return c;
  }, [reviews]);

  const activeTodos = useMemo(
    () => todos.filter((t) => t.status !== "completed").length,
    [todos],
  );

  // A surface's badge goes amber when it has open items OR a review flag.
  const tone = (base: number, hasReview: boolean): "default" | "attention" =>
    hasReview || base > 0 ? "attention" : "default";

  const tabs: {
    id: Tab;
    label: string;
    icon: React.ReactNode;
    count: number;
    countTone?: "default" | "attention";
  }[] = [
    { id: "plan",     label: "Plan",     icon: <ListChecks size={12} />, count: activeTodos, countTone: activeTodos > 0 ? "attention" : "default" },
    { id: "discovery", label: "Discovery", icon: <Search size={12} />, count: discoveryExFlows.length, countTone: tone(0, reviewCounts.discovery > 0) },
    { id: "screens",  label: "Screens",  icon: <Layout size={12} />, count: screenFlows.length },
    { id: "solutions", label: "Solutions", icon: <Lightbulb size={12} />, count: solutions.length + features.length, countTone: tone(0, reviewCounts.solutions > 0) },
    { id: "prd",      label: "PRD",      icon: <FileText size={12} />, count: prdSectionCount, countTone: tone(0, reviewCounts.prd > 0) },
    {
      id: "decisions",
      label: "Decisions",
      icon: <History size={12} />,
      count: openDecisions,
      countTone: tone(openDecisions, reviewCounts.decisions > 0),
    },
    {
      id: "guardrails",
      label: "Guardrails",
      icon: <ShieldAlert size={12} />,
      count: guardrails.length,
    },
    { id: "sprint",   label: "Sprint", icon: <KanbanSquare size={12} />, count: tasks.length, countTone: tone(0, reviewCounts.sprint > 0) },
    { id: "activity", label: "Activity", icon: <Activity size={12} />, count: agentRuns.filter((i) => i.kind === "agent_call").length },
  ];

  return (
    <div className="flex-1 flex flex-col h-full min-w-0 rounded-3xl bg-card border border-border overflow-hidden">
      <div className="px-3 pt-3 pb-0 flex-shrink-0 flex items-center gap-2">
        {/* Single divider toggle on the workspace's left edge. Always
            controls the chat (the other panel). Chevron direction shows
            where the divider moves on click. */}
        {onToggleChat && (
          <button
            onClick={onToggleChat}
            title={chatOpen ? "Hide chat" : "Show chat"}
            aria-label={chatOpen ? "Hide chat panel" : "Show chat panel"}
            className="shrink-0 w-8 h-8 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted transition-colors flex items-center justify-center"
          >
            {chatOpen ? <ChevronLeft size={17} /> : <ChevronRight size={17} />}
          </button>
        )}
        <div className="flex-1 flex flex-wrap gap-1 bg-muted/40 rounded-2xl p-1">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex-1 min-w-[88px] px-2.5 py-2 text-xs font-medium rounded-xl transition-all duration-200 flex items-center justify-center gap-1.5 ${
                activeTab === tab.id
                  ? "bg-card text-foreground shadow-sm"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              {tab.icon}
              <span>{tab.label}</span>
              {tab.count > 0 && (
                <span
                  className={`text-[10px] font-semibold px-1.5 py-0.5 rounded-md ${
                    tab.countTone === "attention"
                      ? "bg-amber-100 text-amber-800"
                      : activeTab === tab.id
                      ? "bg-muted text-foreground"
                      : "bg-muted/60 text-muted-foreground"
                  }`}
                >
                  {tab.count}
                </span>
              )}
            </button>
          ))}
        </div>
      </div>

      <div className="flex-1 min-h-0">
        {activeTab === "plan" && <PlanTab todos={todos} />}
        {activeTab === "discovery" && (
          <DiscoveryTab items={discoveryExFlows} onAddToChat={onAskMaya} />
        )}
        {activeTab === "screens" && (
          <ScreensTab items={screenFlows} onAddToChat={onAskMaya} />
        )}
        {activeTab === "solutions" && (
          <SolutionsTab
            solutions={solutions}
            features={features}
            onAskMaya={onAskMaya}
          />
        )}
        {activeTab === "activity" && <ActivityTab items={agentRuns} />}
        {activeTab === "prd" && (
          <PrdViewer prd={prd} decisions={decisions} onAskMaya={onAskMaya} />
        )}
        {activeTab === "decisions" && (
          <DecisionsTab
            decisions={decisionsExGuardrails}
            tasks={tasks}
            onDiscuss={(d) => onAskMaya(`${d.display_id} — ${d.title}\n\n${d.detail}`)}
          />
        )}
        {activeTab === "guardrails" && (
          <GuardrailsTab
            decisions={decisions}
            onDiscuss={(d) => onAskMaya(`Guardrail ${d.display_id} — ${d.title}\n\n${d.detail}`)}
          />
        )}
        {activeTab === "sprint" && (
          <SprintBoard
            tasks={tasks}
            sprints={sprints}
            decisions={decisions}
            northStar={northStar}
            onAdvance={onTaskAdvance}
            onDiscussDecision={(d) => onAskMaya(`${d.display_id} — ${d.title}\n\n${d.detail}`)}
            onDiscussTask={(t) =>
              onAskMaya(
                `Task ${t.display_id} · ${t.title}` +
                  (t.goal ? `\nGoal: ${t.goal}` : "") +
                  (t.agent_note ? `\nNote: ${t.agent_note}` : "")
              )
            }
          />
        )}
      </div>
    </div>
  );
}
