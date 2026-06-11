/**
 * RepoControl — the per-project GitHub repo picker.
 *
 * Lives in the project header (top-right), NOT in global Settings: the GitHub
 * *account* connection is workspace-level (Settings), but *which repo* powers a
 * project is a property of that project, so it belongs here. Self-contained —
 * fetches its own connection + link state and talks to the repo API directly.
 *
 * States: no account → nudge to Settings · account but no repo → "Link repo"
 * picker · linked → shows the repo + change / re-sync / unlink in a popover.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Github, ChevronDown, Loader2, RefreshCw, Link2Off, ExternalLink, Plus,
} from "lucide-react";
import {
  apiGithubListConnections,
  apiGithubListRepos,
  apiGetRepoLink,
  apiLinkRepo,
  apiUnlinkRepo,
  type GithubConnection,
  type GithubRepo,
  type ProjectRepoLink,
} from "@/lib/api";

export function RepoControl({ projectId }: { projectId: string }) {
  const navigate = useNavigate();
  const [connections, setConnections] = useState<GithubConnection[]>([]);
  const [link, setLink] = useState<ProjectRepoLink | null>(null);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState<string | null>(null); // status text while working
  const [repos, setRepos] = useState<GithubRepo[]>([]);
  const [reposLoading, setReposLoading] = useState(false);
  const [activeConn, setActiveConn] = useState<string>("");
  const ref = useRef<HTMLDivElement>(null);

  // Initial load: connections + this project's current link.
  useEffect(() => {
    let alive = true;
    setLoading(true);
    Promise.all([apiGithubListConnections(), apiGetRepoLink(projectId)])
      .then(([c, l]) => {
        if (!alive) return;
        setConnections(c.connections);
        setActiveConn(c.connections[0]?.id ?? "");
        setLink(l.link);
      })
      .catch(() => {})
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, [projectId]);

  // Load repos for the active connection only when the popover is open.
  useEffect(() => {
    if (!open || !activeConn) return;
    setReposLoading(true);
    apiGithubListRepos(activeConn)
      .then((r) => setRepos(r.repos))
      .catch(() => setRepos([]))
      .finally(() => setReposLoading(false));
  }, [open, activeConn]);

  // Close on outside click.
  useEffect(() => {
    if (!open) return;
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, [open]);

  const repoNames = useMemo(() => repos.map((r) => r.full_name), [repos]);

  async function pickRepo(fullName: string) {
    if (!activeConn) return;
    const repo = repos.find((r) => r.full_name === fullName);
    setBusy(link ? "Switching repo…" : "Linking & reading repo…");
    try {
      await apiLinkRepo(projectId, {
        connection_id: activeConn,
        repo_full_name: fullName,
        branch: repo?.default_branch ?? "main",
      });
      const fresh = await apiGetRepoLink(projectId);
      setLink(fresh.link);
      setOpen(false);
    } catch {
      /* surfaced via the chip staying unchanged; keep it quiet */
    } finally {
      setBusy(null);
    }
  }

  async function resync() {
    if (!link) return;
    setBusy("Re-reading repo…");
    try {
      await apiLinkRepo(projectId, {
        connection_id: link.github_connection_id,
        repo_full_name: link.repo_full_name,
        branch: link.branch,
      });
      const fresh = await apiGetRepoLink(projectId);
      setLink(fresh.link);
    } catch {
      /* quiet */
    } finally {
      setBusy(null);
    }
  }

  async function unlink() {
    setBusy("Unlinking…");
    try {
      await apiUnlinkRepo(projectId);
      setLink(null);
      setOpen(false);
    } catch {
      /* quiet */
    } finally {
      setBusy(null);
    }
  }

  if (loading) {
    return (
      <span className="inline-flex items-center gap-1.5 text-[11px] text-muted-foreground px-2 py-1">
        <Loader2 size={11} className="animate-spin" />
      </span>
    );
  }

  // No GitHub account connected → send them to Settings (account-level).
  if (connections.length === 0) {
    return (
      <button
        onClick={() => navigate("/settings")}
        title="Connect a GitHub account in Settings, then pick a repo here"
        className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border border-border text-[11.5px] font-medium text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
      >
        <Github size={12} />
        Connect GitHub
      </button>
    );
  }

  const repoPicker = (
    <div className="px-3 py-2.5 border-t border-border">
      {connections.length > 1 && (
        <select
          value={activeConn}
          onChange={(e) => setActiveConn(e.target.value)}
          className="w-full mb-2 text-[11.5px] bg-card border border-border rounded-md px-2 py-1.5"
        >
          {connections.map((c) => (
            <option key={c.id} value={c.id}>{c.github_user_login}</option>
          ))}
        </select>
      )}
      {reposLoading ? (
        <p className="text-[11px] text-muted-foreground flex items-center gap-1.5 py-1">
          <Loader2 size={11} className="animate-spin" /> Loading repos…
        </p>
      ) : (
        <select
          defaultValue=""
          onChange={(e) => e.target.value && pickRepo(e.target.value)}
          className="w-full text-[11.5px] bg-card border border-border rounded-md px-2 py-1.5"
        >
          <option value="">{link ? "— switch to… —" : "— pick a repo —"}</option>
          {repoNames
            .filter((rn) => rn !== link?.repo_full_name)
            .map((rn) => (
              <option key={rn} value={rn}>{rn}</option>
            ))}
        </select>
      )}
    </div>
  );

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen((o) => !o)}
        title={link ? `Linked to ${link.repo_full_name}` : "Link a repo to this project"}
        className={`inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border text-[11.5px] font-medium transition-colors max-w-[220px] ${
          link
            ? "border-border text-foreground hover:bg-muted"
            : "border-dashed border-border text-muted-foreground hover:text-foreground hover:bg-muted"
        }`}
      >
        {busy ? (
          <Loader2 size={12} className="animate-spin shrink-0" />
        ) : (
          <Github size={12} className="shrink-0" />
        )}
        <span className="truncate font-mono">
          {busy ?? (link ? link.repo_full_name.split("/").pop() : "Link repo")}
        </span>
        {!busy && <ChevronDown size={11} className="shrink-0 opacity-60" />}
      </button>

      {open && (
        <div className="absolute right-0 top-full mt-1.5 w-[280px] rounded-xl border border-border bg-card shadow-lg z-50 overflow-hidden">
          {link ? (
            <>
              <div className="px-3 py-2.5">
                <a
                  href={`https://github.com/${link.repo_full_name}`}
                  target="_blank"
                  rel="noreferrer"
                  className="flex items-center gap-1.5 text-[12px] font-medium text-foreground hover:underline"
                >
                  <Github size={12} className="shrink-0" />
                  <span className="font-mono truncate">{link.repo_full_name}</span>
                  <ExternalLink size={10} className="shrink-0 opacity-60" />
                </a>
                <p className="mt-1 text-[10.5px] text-muted-foreground">
                  branch <span className="font-mono">{link.branch}</span>
                  {link.last_synced_at && " · Maya has read this repo"}
                </p>
              </div>
              <div className="flex border-t border-border">
                <button
                  onClick={resync}
                  disabled={!!busy}
                  className="flex-1 flex items-center justify-center gap-1.5 px-2 py-2 text-[11px] font-medium text-foreground hover:bg-muted transition-colors disabled:opacity-50"
                >
                  <RefreshCw size={11} /> Re-sync
                </button>
                <button
                  onClick={unlink}
                  disabled={!!busy}
                  className="flex-1 flex items-center justify-center gap-1.5 px-2 py-2 text-[11px] font-medium text-rose-700 hover:bg-rose-50 border-l border-border transition-colors disabled:opacity-50"
                >
                  <Link2Off size={11} /> Unlink
                </button>
              </div>
              <div className="px-3 py-1.5 border-t border-border">
                <p className="text-[10px] uppercase tracking-wide text-muted-foreground font-medium flex items-center gap-1">
                  <Plus size={9} /> Change repo
                </p>
              </div>
              {repoPicker}
            </>
          ) : (
            <>
              <div className="px-3 py-2.5">
                <p className="text-[12px] font-medium text-foreground flex items-center gap-1.5">
                  <Github size={12} /> Link a repo
                </p>
                <p className="mt-1 text-[10.5px] text-muted-foreground leading-relaxed">
                  Maya reads its structure, stack, and data model — so she scopes
                  new features against what's already built.
                </p>
              </div>
              {repoPicker}
            </>
          )}
        </div>
      )}
    </div>
  );
}
