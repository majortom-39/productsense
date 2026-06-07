/**
 * Settings page — workspace-level integrations.
 *
 * Today this means GitHub. The card on the right shows connection state
 * + a list of repos the user can link to specific projects. Per-project
 * linking happens in the chat panel's overflow menu (or, for now, the
 * "Linked repo" card at the bottom of this page when a project is selected).
 *
 * Future: notification preferences, project deletion, MCP setup help, etc.
 */
import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  ArrowLeft,
  Github,
  ExternalLink,
  Loader2,
  Trash2,
  Check,
  AlertTriangle,
} from "lucide-react";
import {
  apiGithubListConnections,
  apiGithubStart,
  apiGithubDeleteConnection,
  apiGithubListRepos,
  apiListProjects,
  apiGetRepoLink,
  apiLinkRepo,
  apiUnlinkRepo,
  type GithubConnection,
  type GithubRepo,
  type Project,
  type ProjectRepoLink,
} from "@/lib/api";


export default function Settings() {
  const navigate = useNavigate();
  const [connections, setConnections] = useState<GithubConnection[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);

  const refresh = async () => {
    setLoading(true);
    setError(null);
    try {
      const [c, p] = await Promise.all([apiGithubListConnections(), apiListProjects()]);
      setConnections(c.connections);
      setProjects(p);
    } catch (e: any) {
      setError(e.message ?? String(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refresh();
  }, []);

  async function startConnect() {
    setError(null);
    try {
      const { authorize_url, state } = await apiGithubStart();
      // Persist state so the callback page can verify it
      sessionStorage.setItem("github_oauth_state", state);
      window.location.href = authorize_url;
    } catch (e: any) {
      setError(e.message ?? "Failed to start GitHub OAuth");
    }
  }

  async function disconnect(id: string) {
    if (!confirm("Disconnect this GitHub account? Repos linked to projects will stay digested.")) return;
    try {
      await apiGithubDeleteConnection(id);
      setConnections((prev) => prev.filter((c) => c.id !== id));
    } catch (e: any) {
      setError(e.message ?? String(e));
    }
  }

  return (
    <div className="min-h-screen bg-background dot-bg">
      <div className="max-w-3xl mx-auto px-6 py-8">
        <button
          onClick={() => navigate("/")}
          className="mb-6 inline-flex items-center gap-1.5 text-[12px] text-muted-foreground hover:text-foreground transition-colors"
        >
          <ArrowLeft size={13} />
          Back to projects
        </button>

        <h1 className="text-2xl font-semibold text-foreground mb-1">Settings</h1>
        <p className="text-[13px] text-muted-foreground mb-8">
          Workspace integrations and account preferences.
        </p>

        {error && (
          <div className="mb-4 px-4 py-3 rounded-xl bg-rose-50 border border-rose-200 text-[12.5px] text-rose-800">
            {error}
          </div>
        )}

        <section className="rounded-2xl border border-border bg-card p-6 mb-6">
          <div className="flex items-start justify-between gap-4 mb-4 flex-wrap">
            <div>
              <h2 className="text-[15px] font-semibold text-foreground flex items-center gap-2">
                <Github size={16} />
                GitHub
              </h2>
              <p className="text-[12px] text-muted-foreground leading-relaxed mt-1 max-w-md">
                Connect a GitHub account to link repos to projects. Maya reads
                each linked repo's structure + key files as part of her context —
                useful when the founder shows up half-deep into an existing build.
              </p>
            </div>
            {connections.length === 0 ? (
              <button
                onClick={startConnect}
                className="px-3 py-1.5 rounded-lg bg-foreground text-background text-[12px] font-medium hover:bg-foreground/85 transition-colors flex items-center gap-1.5"
              >
                <Github size={12} />
                Connect GitHub
              </button>
            ) : (
              <button
                onClick={startConnect}
                className="px-3 py-1.5 rounded-lg border border-border text-foreground text-[12px] font-medium hover:bg-muted transition-colors"
              >
                Add another account
              </button>
            )}
          </div>

          {loading ? (
            <p className="text-[12px] text-muted-foreground flex items-center gap-2">
              <Loader2 size={12} className="animate-spin" />
              Loading…
            </p>
          ) : connections.length === 0 ? (
            <p className="text-[12px] text-muted-foreground italic">
              No GitHub connections yet. Connect to start linking repos.
            </p>
          ) : (
            <div className="space-y-2">
              {connections.map((c) => (
                <div
                  key={c.id}
                  className="flex items-center justify-between gap-3 rounded-lg border border-border bg-muted/30 px-3 py-2"
                >
                  <div className="flex items-center gap-2 min-w-0">
                    <Check size={12} className="text-emerald-600 shrink-0" />
                    <span className="text-[13px] font-medium text-foreground truncate">
                      {c.github_user_login}
                    </span>
                    <span className="text-[10.5px] text-muted-foreground font-mono shrink-0">
                      {c.scope ?? "—"}
                    </span>
                  </div>
                  <button
                    onClick={() => disconnect(c.id)}
                    title="Disconnect"
                    className="text-muted-foreground hover:text-rose-700 transition-colors"
                  >
                    <Trash2 size={13} />
                  </button>
                </div>
              ))}
            </div>
          )}
        </section>

        {connections.length > 0 && (
          <RepoLinkingSection
            connections={connections}
            projects={projects}
            onError={(e) => setError(e)}
          />
        )}

        <section className="rounded-2xl border border-border bg-card p-6">
          <h2 className="text-[15px] font-semibold text-foreground mb-2">Coding agent</h2>
          <p className="text-[12px] text-muted-foreground leading-relaxed mb-3 max-w-md">
            Maya talks to your coding agent (Claude Code, Cursor, etc.) over MCP. The
            MCP server runs locally; add it to your agent's MCP config to give it
            access to the project's PRD, sprint, decisions, and guardrails.
          </p>
          <p className="text-[11.5px] text-muted-foreground italic">
            Detailed setup snippets coming soon. For now, run{" "}
            <code className="px-1 py-0.5 rounded bg-muted">python apps/mcp/server.py</code>{" "}
            and configure your agent to connect to{" "}
            <code className="px-1 py-0.5 rounded bg-muted">http://localhost:8765</code>.
          </p>
        </section>
      </div>
    </div>
  );
}


/** Per-project repo linker. Each project gets a row showing whether it's
 *  linked to a repo + the option to link / unlink / re-sync. */
const RepoLinkingSection: React.FC<{
  connections: GithubConnection[];
  projects: Project[];
  onError: (msg: string) => void;
}> = ({ connections, projects, onError }) => {
  const [links, setLinks] = useState<Record<string, ProjectRepoLink | null>>({});
  const [repos, setRepos] = useState<GithubRepo[]>([]);
  const [reposLoading, setReposLoading] = useState(false);
  const [activeConn, setActiveConn] = useState<string>(connections[0]?.id ?? "");
  const [pendingProject, setPendingProject] = useState<string | null>(null);

  useEffect(() => {
    if (!activeConn) return;
    setReposLoading(true);
    apiGithubListRepos(activeConn)
      .then((r) => setRepos(r.repos))
      .catch((e) => onError(e.message ?? String(e)))
      .finally(() => setReposLoading(false));
  }, [activeConn, onError]);

  useEffect(() => {
    // Hydrate existing per-project links
    Promise.all(
      projects.map((p) =>
        apiGetRepoLink(p.id)
          .then((r) => [p.id, r.link] as const)
          .catch(() => [p.id, null] as const),
      ),
    ).then((pairs) => {
      const map: Record<string, ProjectRepoLink | null> = {};
      for (const [pid, link] of pairs) map[pid] = link;
      setLinks(map);
    });
  }, [projects]);

  const repoNames = useMemo(() => repos.map((r) => r.full_name), [repos]);

  async function connectRepo(projectId: string, repoFullName: string) {
    if (!activeConn) return;
    const repo = repos.find((r) => r.full_name === repoFullName);
    setPendingProject(projectId);
    try {
      await apiLinkRepo(projectId, {
        connection_id: activeConn,
        repo_full_name: repoFullName,
        branch: repo?.default_branch ?? "main",
      });
      const fresh = await apiGetRepoLink(projectId);
      setLinks((m) => ({ ...m, [projectId]: fresh.link }));
    } catch (e: any) {
      onError(e.message ?? String(e));
    } finally {
      setPendingProject(null);
    }
  }

  async function unlink(projectId: string) {
    setPendingProject(projectId);
    try {
      await apiUnlinkRepo(projectId);
      setLinks((m) => ({ ...m, [projectId]: null }));
    } catch (e: any) {
      onError(e.message ?? String(e));
    } finally {
      setPendingProject(null);
    }
  }

  return (
    <section className="rounded-2xl border border-border bg-card p-6 mb-6">
      <h2 className="text-[15px] font-semibold text-foreground mb-1">Linked repositories</h2>
      <p className="text-[12px] text-muted-foreground leading-relaxed mb-4 max-w-md">
        Pick a GitHub repo per project. Maya rebuilds the repo digest each time
        you link or re-link; she reads it as context on every turn.
      </p>

      {connections.length > 1 && (
        <div className="mb-3 flex items-center gap-2">
          <span className="text-[11px] text-muted-foreground">Account:</span>
          <select
            value={activeConn}
            onChange={(e) => setActiveConn(e.target.value)}
            className="text-[12px] bg-card border border-border rounded px-2 py-1"
          >
            {connections.map((c) => (
              <option key={c.id} value={c.id}>{c.github_user_login}</option>
            ))}
          </select>
        </div>
      )}

      {reposLoading ? (
        <p className="text-[12px] text-muted-foreground flex items-center gap-2">
          <Loader2 size={12} className="animate-spin" />
          Loading repos…
        </p>
      ) : projects.length === 0 ? (
        <p className="text-[12px] text-muted-foreground italic">
          You have no projects yet. Create one from the projects page first.
        </p>
      ) : (
        <div className="space-y-2">
          {projects.map((p) => {
            const link = links[p.id];
            const pending = pendingProject === p.id;
            return (
              <div
                key={p.id}
                className="flex items-center gap-3 rounded-lg border border-border bg-muted/30 px-3 py-2"
              >
                <span className="text-base shrink-0">{p.icon ?? "📁"}</span>
                <span className="text-[12.5px] font-medium text-foreground flex-shrink-0">{p.name}</span>
                <span className="text-muted-foreground">·</span>
                {pending ? (
                  <span className="text-[11.5px] text-muted-foreground flex items-center gap-1.5">
                    <Loader2 size={11} className="animate-spin" />
                    Working…
                  </span>
                ) : link ? (
                  <>
                    <a
                      href={`https://github.com/${link.repo_full_name}`}
                      target="_blank"
                      rel="noreferrer"
                      className="text-[12px] text-foreground/85 flex items-center gap-1 truncate hover:text-foreground"
                    >
                      <Github size={11} />
                      <span className="font-mono truncate">{link.repo_full_name}</span>
                      <ExternalLink size={9} />
                    </a>
                    <span className="text-[10px] text-muted-foreground ml-auto shrink-0">
                      branch: {link.branch}
                    </span>
                    <button
                      onClick={() => unlink(p.id)}
                      title="Unlink"
                      className="text-muted-foreground hover:text-rose-700 transition-colors ml-2"
                    >
                      <Trash2 size={12} />
                    </button>
                  </>
                ) : (
                  <select
                    defaultValue=""
                    onChange={(e) => {
                      if (e.target.value) connectRepo(p.id, e.target.value);
                    }}
                    className="flex-1 text-[11.5px] bg-card border border-border rounded px-2 py-1 max-w-[300px]"
                  >
                    <option value="">— pick a repo —</option>
                    {repoNames.map((rn) => (
                      <option key={rn} value={rn}>{rn}</option>
                    ))}
                  </select>
                )}
              </div>
            );
          })}
        </div>
      )}

      {connections.length > 0 && repos.length === 0 && !reposLoading && (
        <p className="mt-3 text-[11.5px] text-amber-700 flex items-center gap-1.5">
          <AlertTriangle size={11} />
          No repos returned — check the OAuth scope on the connection.
        </p>
      )}
    </section>
  );
};
