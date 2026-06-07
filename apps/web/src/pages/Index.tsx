import { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import {
  apiListProjects,
  apiCreateProject,
  apiDeleteProject,
  apiUpdateTask,
  type Project,
  type TaskStatus,
} from "@/lib/api";
import { Sidebar } from "@/components/Sidebar";
import { ChatPanel } from "@/components/ChatPanel";
import { RightPanel } from "@/components/RightPanel";
import { useMayaSession } from "@/hooks/useMayaSession";
import { useProjectArtifacts } from "@/hooks/useProjectArtifacts";
import { useProjectAssets } from "@/hooks/useProjectAssets";

// Neutral, project-agnostic icons. First one is the default for new projects.
const PROJECT_ICONS = ["💡", "🚀", "🌱", "🎯", "📦", "⚡", "🔮", "🎨"];

export default function Index() {
  const { projectId } = useParams();
  const navigate = useNavigate();
  const { user } = useAuth();
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [prdSelection, setPrdSelection] = useState<string | null>(null);
  // Workspace + chat panels can each be collapsed, but NEVER both at the same
  // time — togglers below enforce that at least one stays open. When the
  // founder closes the chat, the workspace fills the whole screen; when they
  // close the workspace, the chat fills the screen (existing behaviour).
  const [rightPanelOpen, setRightPanelOpen] = useState(true);
  const [chatPanelOpen, setChatPanelOpen] = useState(true);

  useEffect(() => {
    if (!user) return;
    apiListProjects()
      .then((p) => setProjects(p))
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [user]);

  const handleCreate = useCallback(async () => {
    setCreating(true);
    try {
      const icon = PROJECT_ICONS[projects.length % PROJECT_ICONS.length];
      const project = await apiCreateProject({
        name: `Untitled project ${projects.length + 1}`,
        icon,
      });
      setProjects((prev) => [project, ...prev]);
      navigate(`/projects/${project.id}`);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setCreating(false);
    }
  }, [projects.length, navigate]);

  const handleDelete = useCallback(
    async (id: string) => {
      try {
        await apiDeleteProject(id);
        setProjects((prev) => prev.filter((p) => p.id !== id));
        if (projectId === id) navigate("/");
      } catch (e: any) {
        setError(e.message);
      }
    },
    [projectId, navigate],
  );

  const activeProject = projects.find((p) => p.id === projectId) ?? null;
  const maya = useMayaSession(activeProject?.id ?? null);
  const artifacts = useProjectArtifacts(activeProject?.id ?? null);
  const projectAssets = useProjectAssets(activeProject?.id ?? null);

  // When Maya emits an artifact hint, drain the inline delta queue (each
  // event merges directly into local state — no refetch round-trip, so no
  // PostgREST read-after-write race). When a hint arrives WITHOUT an
  // inline delta (PRD / sprint, or older paths), fall back to refetch.
  // The queue pattern survives bursty events (e.g. Maya pins 2 artifacts
  // in one response) — the previous single-field design dropped intermediate
  // events when nonces fired in the same React render.
  useEffect(() => {
    if (!maya.artifactHint) return;
    const deltas = maya.consumeArtifactDeltas();
    if (deltas.length > 0) {
      for (const d of deltas) {
        if (d.kind === "discovery") {
          if (d.op === "delete") {
            artifacts.mergeArtifact("delete", d.id);
          } else if (d.op === "upsert") {
            artifacts.mergeArtifact(
              "upsert",
              d.id,
              d.item as unknown as import("@/lib/api").DiscoveryArtifact,
            );
          }
          // discovery has no upsert_batch path currently
        } else if (d.kind === "decisions") {
          if (d.op === "delete") {
            artifacts.mergeDecision("delete", d.id);
          } else if (d.op === "upsert") {
            artifacts.mergeDecision(
              "upsert",
              d.id,
              d.item as unknown as import("@/lib/api").Decision,
            );
          } else if (d.op === "upsert_batch") {
            artifacts.mergeDecisionsBatch(
              d.items as unknown as import("@/lib/api").Decision[],
            );
          }
        }
      }
    } else {
      // No inline data — refetch the panel that changed.
      artifacts.refreshOne(maya.artifactHint.kind);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [maya.artifactHint?.nonce]);

  const activeSprint = artifacts.sprints.find((s) => s.status === "active") ?? null;
  // Header label still highlights the active sprint (the one the coding agent
  // is shipping); the Sprint board internally switches between all sprints.
  const sprintLabel = activeSprint?.name
    ? `${activeSprint.name} active${
        artifacts.sprints.length > 1 ? ` · ${artifacts.sprints.length - 1} queued` : ""
      }`
    : null;

  async function handleTaskAdvance(taskId: string, next: TaskStatus) {
    if (!activeProject) return;
    try {
      await apiUpdateTask(activeProject.id, taskId, { status: next });
      artifacts.refreshOne("sprint");
    } catch (e: any) {
      setError(e.message);
    }
  }

  return (
    <div className="dot-bg flex h-screen overflow-hidden bg-background gap-3 p-3">
      <Sidebar
        projects={projects}
        activeProjectId={projectId ?? null}
        onSelectProject={(id) => navigate(`/projects/${id}`)}
        onCreateProject={handleCreate}
        onDeleteProject={handleDelete}
        loading={loading}
        creating={creating}
      />

      {activeProject ? (
        <>
          {/* Chat panel — mirror of the workspace's collapse pattern.
              When closed, the workspace fills the rest of the screen. */}
          <div
            className={`relative h-full transition-all duration-300 ease-out overflow-hidden ${
              chatPanelOpen
                ? "flex-1 opacity-100"
                : "flex-[0_0_0px] opacity-0 -mr-3 pointer-events-none"
            }`}
            aria-hidden={!chatPanelOpen}
          >
            <div className="w-full h-full flex">
              <ChatPanel
                projectName={activeProject.name}
                projectIcon={activeProject.icon}
                sprintLabel={sprintLabel}
                items={maya.items}
                isStreaming={maya.isStreaming}
                awaitingInput={maya.awaitingInput}
                activeAgent={maya.activeAgent}
                liveThinking={maya.liveThinking}
                liveText={maya.liveText}
                pendingAsk={maya.pendingAsk}
                error={maya.error || error || artifacts.refreshError}
                prefillText={prdSelection}
                onPrefillConsumed={() => setPrdSelection(null)}
                onSend={(text, quoted) => maya.sendMessage(text, quoted)}
                onCancelTurn={maya.cancelTurn}
                onQueueMessage={maya.queueMessage}
                onClearQueuedMessage={maya.clearQueuedMessage}
                queuedMessage={maya.queuedMessage}
                workspaceOpen={rightPanelOpen}
                onToggleWorkspace={() => setRightPanelOpen((o) => !o)}
                assets={projectAssets.assets}
                onUploadFile={projectAssets.upload}
                onRemoveAsset={projectAssets.remove}
                assetError={projectAssets.error}
                onClearAssetError={projectAssets.clearError}
              />
            </div>
          </div>

          {/* Right panel — animates via flex trick.
              When collapsed: width 0, hidden. When open: takes ~62% of remaining
              space if chat is also open; full width if chat is closed. */}
          <div
            className={`relative h-full transition-all duration-300 ease-out overflow-hidden ${
              rightPanelOpen
                ? chatPanelOpen
                  ? "flex-[1.6] opacity-100"
                  : "flex-1 opacity-100"          // chat hidden → take everything
                : "flex-[0_0_0px] opacity-0 -ml-3 pointer-events-none"
            }`}
            aria-hidden={!rightPanelOpen}
          >
            <div className="w-full h-full min-w-[420px] flex">
              <RightPanel
                discovery={artifacts.discovery}
                prd={artifacts.prd}
                tasks={artifacts.tasks}
                sprints={artifacts.sprints}
                decisions={artifacts.decisions}
                solutions={artifacts.solutions}
                features={artifacts.features}
                reviews={artifacts.reviews}
                agentRuns={maya.items}
                todos={maya.todos}
                northStar={activeProject.north_star}
                // The workspace's single button toggles CHAT visibility
                // (mirror of how chat's button toggles workspace).
                chatOpen={chatPanelOpen}
                onToggleChat={() => setChatPanelOpen((o) => !o)}
                onAskMaya={(text) => setPrdSelection(text)}
                onTaskAdvance={handleTaskAdvance}
              />
            </div>
          </div>
        </>
      ) : (
        <div className="flex-1 flex items-center justify-center rounded-3xl bg-card border border-border">
          <div className="text-center max-w-md">
            <p className="text-sm font-medium text-foreground mb-1">Select a project</p>
            <p className="text-xs text-muted-foreground leading-relaxed">
              Or create a new one to start a session with Maya.
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
