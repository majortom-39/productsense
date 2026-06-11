/**
 * Settings page — workspace-level integrations.
 *
 * Today this means the GitHub *account* connection (OAuth). Connecting an
 * account is workspace-level and lives here; choosing *which repo* powers a
 * given project is per-project and lives in that project's top bar
 * (see components/RepoControl.tsx), not on this page.
 *
 * Future: notification preferences, project deletion, MCP setup help, etc.
 */
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  ArrowLeft,
  Github,
  Loader2,
  Trash2,
  Check,
} from "lucide-react";
import {
  apiGithubListConnections,
  apiGithubStart,
  apiGithubDeleteConnection,
  type GithubConnection,
} from "@/lib/api";


export default function Settings() {
  const navigate = useNavigate();
  const [connections, setConnections] = useState<GithubConnection[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = async () => {
    setLoading(true);
    setError(null);
    try {
      const c = await apiGithubListConnections();
      setConnections(c.connections);
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
                Connect a GitHub account here, then pick a repo for each project
                from the repo button in that project's top bar. Maya reads the
                linked repo's stack, data model, and structure — so she can scope
                new features against what's already built.
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
              No GitHub connections yet. Connect an account, then link a repo from
              inside a project.
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
