/**
 * AgentControl — the per-project "Connect your coding agent" panel.
 *
 * Sits in the project header next to RepoControl: the repo is WHERE the agent
 * builds, this is HOW it talks to ProductSense. Generates the project's
 * ps_live_ key and shows a one-paste snippet (Supabase-style) the founder
 * drops into Claude Code / Cursor — the agent configures itself from it.
 *
 * The dot is honest: it reflects `last_seen_at`, stamped server-side on every
 * authed MCP request. Green = seen in the last 10 minutes, amber = connected
 * before but quiet, grey = never connected / no key.
 */
import { useEffect, useRef, useState } from "react";
import {
  Bot, ChevronDown, Loader2, Copy, Check, RefreshCw, Unplug, ShieldAlert,
} from "lucide-react";
import {
  API_URL,
  apiGetMcpKeyStatus,
  apiGenerateMcpKey,
  apiRevokeMcpKey,
  type McpKeyStatus,
} from "@/lib/api";
import { timeAgo } from "@/lib/time";

const ACTIVE_WINDOW_MS = 10 * 60 * 1000;

function connectSnippet(key: string): string {
  const url = `${API_URL}/mcp`;
  return `Connect my ProductSense project as an MCP server so you can read the sprint board and report progress.

Transport: Streamable HTTP
URL: ${url}
Auth header: X-PS-Key: ${key}

If you are Claude Code, run:
  claude mcp add productsense --transport http ${url} --header "X-PS-Key: ${key}"

Otherwise add this to your MCP config (e.g. .cursor/mcp.json):
  {"mcpServers":{"productsense":{"url":"${url}","headers":{"X-PS-Key":"${key}"}}}}

Then call the get_session_context tool and tell me what the current task is.`;
}

export function AgentControl({ projectId }: { projectId: string }) {
  const [status, setStatus] = useState<McpKeyStatus | null>(null);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  /** Plaintext key — exists only right after generation; gone on close. */
  const [freshKey, setFreshKey] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  const refresh = () => {
    apiGetMcpKeyStatus(projectId)
      .then((r) => setStatus(r.status))
      .catch(() => {});
  };

  useEffect(() => {
    setStatus(null);
    setFreshKey(null);
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);

  // Refresh last_seen while the popover is open (the founder is watching
  // for the dot to go green after pasting the snippet).
  useEffect(() => {
    if (!open) return;
    refresh();
    const t = setInterval(refresh, 5000);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
        setFreshKey(null); // plaintext never lingers
      }
    };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, [open]);

  async function generate() {
    setBusy(true);
    try {
      const r = await apiGenerateMcpKey(projectId);
      setFreshKey(r.key.key);
      refresh();
    } catch {
      /* quiet */
    } finally {
      setBusy(false);
    }
  }

  async function disconnect() {
    setBusy(true);
    try {
      await apiRevokeMcpKey(projectId);
      setFreshKey(null);
      refresh();
    } catch {
      /* quiet */
    } finally {
      setBusy(false);
    }
  }

  async function copySnippet() {
    if (!freshKey) return;
    try {
      await navigator.clipboard.writeText(connectSnippet(freshKey));
      setCopied(true);
      setTimeout(() => setCopied(false), 1600);
    } catch {
      /* quiet */
    }
  }

  const lastSeen = status?.last_seen_at ? new Date(status.last_seen_at).getTime() : null;
  const isActive = lastSeen !== null && Date.now() - lastSeen < ACTIVE_WINDOW_MS;
  const dotClass = isActive
    ? "bg-emerald-500"
    : lastSeen !== null
    ? "bg-amber-400"
    : "bg-muted-foreground/40";

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen((o) => !o)}
        title={
          isActive
            ? `Coding agent active · last seen ${timeAgo(status!.last_seen_at!)}`
            : status?.active
            ? "Coding agent connected but quiet"
            : "Connect your coding agent"
        }
        className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border border-border text-[11.5px] font-medium text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
      >
        <span className={`w-2 h-2 rounded-full ${dotClass} ${isActive ? "animate-pulse" : ""}`} />
        <Bot size={12} className="shrink-0" />
        <span>Agent</span>
        <ChevronDown size={11} className="shrink-0 opacity-60" />
      </button>

      {open && (
        <div className="absolute right-0 top-full mt-1.5 w-[340px] rounded-xl border border-border bg-card shadow-lg z-50 overflow-hidden">
          <div className="px-3 py-2.5">
            <p className="text-[12px] font-medium text-foreground flex items-center gap-1.5">
              <Bot size={12} /> Your coding agent
            </p>
            <p className="mt-1 text-[10.5px] text-muted-foreground leading-relaxed">
              Claude Code, Cursor, or any MCP-capable agent connects here to pick
              up sprint tasks, report progress, and ask Maya questions.
            </p>
            <p className="mt-2 text-[11px]">
              {isActive ? (
                <span className="text-emerald-700 font-medium">
                  ● Active — last seen {timeAgo(status!.last_seen_at!)}
                </span>
              ) : status?.last_seen_at ? (
                <span className="text-amber-700">
                  ● Connected before — last seen {timeAgo(status.last_seen_at)}
                </span>
              ) : status?.active ? (
                <span className="text-muted-foreground">
                  ● Key created ({status.key_prefix}) — waiting for the agent's first call
                </span>
              ) : (
                <span className="text-muted-foreground">● Not connected yet</span>
              )}
            </p>
          </div>

          {freshKey ? (
            <div className="px-3 pb-3">
              <div className="rounded-lg border border-amber-200 bg-amber-50 px-2.5 py-2 mb-2">
                <p className="text-[10.5px] text-amber-900 leading-snug flex items-start gap-1.5">
                  <ShieldAlert size={11} className="mt-0.5 shrink-0" />
                  This key is shown once. Copy the snippet below and paste it into
                  your coding agent's chat — it sets itself up.
                </p>
              </div>
              <pre className="text-[9.5px] font-mono leading-relaxed bg-muted/60 border border-border rounded-lg p-2.5 max-h-[180px] overflow-auto whitespace-pre-wrap break-all">
                {connectSnippet(freshKey)}
              </pre>
              <button
                onClick={copySnippet}
                className="mt-2 w-full flex items-center justify-center gap-1.5 px-2 py-2 rounded-lg bg-foreground text-background text-[11.5px] font-medium hover:bg-foreground/85 transition-colors"
              >
                {copied ? <Check size={12} /> : <Copy size={12} />}
                {copied ? "Copied" : "Copy connect prompt"}
              </button>
            </div>
          ) : (
            <div className="flex border-t border-border">
              <button
                onClick={generate}
                disabled={busy}
                className="flex-1 flex items-center justify-center gap-1.5 px-2 py-2 text-[11px] font-medium text-foreground hover:bg-muted transition-colors disabled:opacity-50"
              >
                {busy ? <Loader2 size={11} className="animate-spin" /> : <RefreshCw size={11} />}
                {status?.active ? "Regenerate key" : "Generate connect key"}
              </button>
              {status?.active && (
                <button
                  onClick={disconnect}
                  disabled={busy}
                  className="flex-1 flex items-center justify-center gap-1.5 px-2 py-2 text-[11px] font-medium text-rose-700 hover:bg-rose-50 border-l border-border transition-colors disabled:opacity-50"
                >
                  <Unplug size={11} /> Disconnect
                </button>
              )}
            </div>
          )}
          {status?.active && !freshKey && (
            <p className="px-3 pb-2.5 text-[10px] text-muted-foreground leading-snug">
              Regenerating invalidates the old key — the agent must reconnect with
              the new snippet.
            </p>
          )}
        </div>
      )}
    </div>
  );
}
