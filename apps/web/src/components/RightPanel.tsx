import { useEffect, useMemo, useState } from "react";
import { Search, FileText, KanbanSquare, History, ChevronLeft, ChevronRight, Layout } from "lucide-react";
import { DiscoveryTab } from "@/components/DiscoveryTab";
import { ScreensTab } from "@/components/ScreensTab";
import { PrdViewer } from "@/components/PrdViewer";
import { SprintBoard } from "@/components/SprintBoard";
import { DecisionsTab } from "@/components/DecisionsTab";
import { RepoControl } from "@/components/RepoControl";
import type { Decision, Prd, DiscoveryArtifact, Task, TaskStatus, Sprint, Solution, Feature, ReviewItem } from "@/lib/api";
import type { ChatItem, Todo } from "@/hooks/useMayaSession";

// Five essential surfaces. (Plan/Solutions/Guardrails/Activity were retired:
// guardrails + the MVP feature list now live INSIDE the PRD; live todos show in
// chat; the activity log is observability, not a founder deliverable.)
type Tab = "discovery" | "screens" | "prd" | "decisions" | "sprint";

interface Props {
  /** The project this workspace belongs to — used by the top-right repo picker. */
  projectId: string;
  discovery: DiscoveryArtifact[];
  prd: Prd | null;
  tasks: Task[];
  /** All sprints for the project. SprintBoard switches between them. */
  sprints: Sprint[];
  decisions: Decision[];
  /** Capabilities that fell out of the chosen solution + the MVP cut. Surfaced
   *  at the top of the PRD ("what we're building"). */
  features: Feature[];
  /** Nodes the coherence engine flagged for another look → attention badges. */
  reviews: ReviewItem[];
  /** Project-level macro — passed to SprintBoard. */
  northStar?: string | null;
  /** Candidate approaches Maya weighed. No longer a tab; kept on the contract
   *  (the data still exists; we just don't surface it as its own surface). */
  solutions?: Solution[];
  /** Maya's live plan (write_todos) — now shown inline in chat, not a tab. */
  todos?: Todo[];
  /** Maya's dispatch/work stream — observability, not surfaced as a tab. */
  agentRuns?: ChatItem[];
  chatOpen?: boolean;
  onToggleChat?: () => void;
  /** Generic "quote this into chat" — every card's "Add to chat" funnels here;
   *  the ChatPanel receives it via `prefillText` (appended, so several can stack). */
  onAskMaya: (text: string) => void;
  onTaskAdvance: (taskId: string, next: TaskStatus) => void;
}

function countPrdSections(md: string | undefined): number {
  if (!md) return 0;
  return (md.match(/^##\s+.+/gm) ?? []).length;
}

export function RightPanel({
  projectId,
  discovery,
  prd,
  tasks,
  sprints,
  decisions,
  features,
  reviews,
  northStar,
  chatOpen,
  onToggleChat,
  onAskMaya,
  onTaskAdvance,
}: Props) {
  // Decisions tab excludes guardrails (those now render inside the PRD).
  const decisionsExGuardrails = useMemo(
    () => decisions.filter((d) => d.tag !== "guardrail"),
    [decisions],
  );
  const openDecisions = decisionsExGuardrails.filter((d) => d.status === "open").length;
  const prdSectionCount = countPrdSections(prd?.body_md);
  const [activeTab, setActiveTab] = useState<Tab>("discovery");

  // Auto-jump on first appearance of major artifacts.
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

  // Screens tab = wireframe_flow artifacts; Discovery feed = everything else.
  const screenFlows = useMemo(
    () => discovery.filter((r) => r.render_kind === "wireframe_flow"),
    [discovery],
  );
  const discoveryExFlows = useMemo(
    () => discovery.filter((r) => r.render_kind !== "wireframe_flow"),
    [discovery],
  );
  const firstFlowId = useMemo(() => screenFlows[0]?.id ?? null, [screenFlows]);
  useEffect(() => {
    if (firstFlowId && activeTab === "discovery") setActiveTab("screens");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [firstFlowId]);

  // Coherence "needs another look" flags, bucketed onto the surface they live on.
  // Solutions/features now live in the PRD, so their flags surface on PRD.
  const reviewCounts = useMemo(() => {
    const c = { discovery: 0, prd: 0, decisions: 0, sprint: 0 };
    for (const r of reviews) {
      switch (r.type) {
        case "artifact":
          c.discovery++;
          break;
        case "solution":
        case "feature":
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

  const tone = (base: number, hasReview: boolean): "default" | "attention" =>
    hasReview || base > 0 ? "attention" : "default";

  const tabs: {
    id: Tab;
    label: string;
    icon: React.ReactNode;
    count: number;
    countTone?: "default" | "attention";
  }[] = [
    { id: "discovery", label: "Discovery", icon: <Search size={12} />, count: discoveryExFlows.length, countTone: tone(0, reviewCounts.discovery > 0) },
    { id: "screens", label: "Screens", icon: <Layout size={12} />, count: screenFlows.length },
    { id: "prd", label: "PRD", icon: <FileText size={12} />, count: prdSectionCount, countTone: tone(0, reviewCounts.prd > 0) },
    { id: "decisions", label: "Decisions", icon: <History size={12} />, count: openDecisions, countTone: tone(openDecisions, reviewCounts.decisions > 0) },
    { id: "sprint", label: "Sprint", icon: <KanbanSquare size={12} />, count: tasks.length, countTone: tone(0, reviewCounts.sprint > 0) },
  ];

  return (
    <div className="flex-1 flex flex-col h-full min-w-0 rounded-3xl bg-card border border-border overflow-hidden">
      <div className="px-3 pt-3 pb-0 flex-shrink-0 flex items-center gap-2">
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
        {/* Per-project repo picker — the repo↔project link lives with the
            project, not in global Settings. */}
        <div className="shrink-0">
          <RepoControl projectId={projectId} />
        </div>
      </div>

      <div className="flex-1 min-h-0">
        {activeTab === "discovery" && (
          <DiscoveryTab items={discoveryExFlows} onAddToChat={onAskMaya} />
        )}
        {activeTab === "screens" && (
          <ScreensTab items={screenFlows} onAddToChat={onAskMaya} />
        )}
        {activeTab === "prd" && (
          <PrdViewer prd={prd} decisions={decisions} features={features} onAskMaya={onAskMaya} />
        )}
        {activeTab === "decisions" && (
          <DecisionsTab
            decisions={decisionsExGuardrails}
            tasks={tasks}
            onDiscuss={(d) => onAskMaya(`${d.display_id} — ${d.title}\n\n${d.detail}`)}
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
