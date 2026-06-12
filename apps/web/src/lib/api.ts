/**
 * Typed wrappers for the ProductSense FastAPI backend.
 *
 * Every call attaches the current Supabase JWT as a bearer token.
 * The backend validates it and scopes queries by user_id.
 */
import { supabase } from "@/lib/supabase";

export const API_URL = (import.meta.env.VITE_API_URL as string) ?? "http://localhost:8000";

async function authHeaders(): Promise<Record<string, string>> {
  const { data } = await supabase.auth.getSession();
  const token = data.session?.access_token;
  return token
    ? { Authorization: `Bearer ${token}`, "Content-Type": "application/json" }
    : { "Content-Type": "application/json" };
}

async function http<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    method,
    headers: await authHeaders(),
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? `${method} ${path} failed (${res.status})`);
  }
  return res.json();
}

// ─── Health ─────────────────────────────────────────────────────────────────

export async function ping(): Promise<{ status: string }> {
  const res = await fetch(`${API_URL}/health`);
  if (!res.ok) throw new Error(`API health check failed: ${res.status}`);
  return res.json();
}

// ─── Projects ───────────────────────────────────────────────────────────────

export interface Project {
  id: string;
  user_id: string;
  name: string;
  icon: string | null;
  entry_type: string;
  created_at: string;
  updated_at?: string | null;
  // Macro context — the elevator pitch + the rule. Coding agent reads these first.
  project_brief?: string | null;
  north_star?: string | null;
}

export const apiListProjects = () => http<Project[]>("GET", "/projects");

export const apiCreateProject = (input: {
  name: string;
  icon?: string | null;
  entry_type?: string;
}) => http<Project>("POST", "/projects", input);

export const apiGetProject = (id: string) =>
  http<{ project: Project }>("GET", `/projects/${id}`).then((r) => r.project);

export const apiDeleteProject = (id: string) =>
  http<{ status: string }>("DELETE", `/projects/${id}`);

// ─── Artifacts (PRD / Sprint / Decisions / Discovery) ──────────────────────

export interface Prd {
  id: string;
  project_id: string;
  version: number;
  status: string;
  body_md: string;
  created_at: string;
}

export interface Sprint {
  id: string;
  project_id: string;
  number: number;
  name: string;
  subtitle: string | null;
  status: string;
  // Sprint-level context — the agent reads these once, treats them as canon.
  tech_stack?: Record<string, unknown> | null;
  data_models?: Array<{ name: string; shape?: Record<string, unknown>; notes?: string }> | null;
  repo_layout?: string | null;
  conventions?: Record<string, unknown> | null;
  existing_files?: string[] | null;
}

export type TaskStatus = "todo" | "in_progress" | "done";

export interface Task {
  id: string;
  project_id: string;
  sprint_id: string;
  display_id: string;
  status: TaskStatus;
  title: string;
  goal: string | null;
  description: string | null;
  acceptance: string[] | null;
  prd_context: string | null;
  do_not: string[] | null;
  blocked_by: string[] | null;
  open_decision_id: string | null;
  agent_note: string | null;
  files_touched: string[] | null;
  completion_summary: string | null;
  // Enriched coding-agent fields
  tech_decisions?: Record<string, unknown> | null;
  data_contracts?: Array<{ name: string; lifecycle?: string; shape?: Record<string, unknown> }> | null;
  verification?: string[] | null;
  pitfalls?: string[] | null;
  complexity?: "low" | "medium" | "high" | null;
  secrets_required?: string[] | null;
  refs?: Array<{ label: string; url: string }> | null;
  prompt_brief?: string | null;
}

export type DecisionStatus = "open" | "decided";

export interface Decision {
  id: string;
  project_id: string;
  display_id: string;
  decided_by: string;
  status: DecisionStatus;
  open_type: string | null;
  title: string;
  detail: string;
  why: string;
  related_task_id: string | null;
  tag: string | null;
  pinned: boolean;
  affects: string[] | null;
  created_at: string;
  resolved_at: string | null;
  /** Supersession (Phase 2). When Maya logs a decision that replaces an
   * earlier one (e.g. switching from Tavily → Firecrawl), the new row
   * carries `supersedes` (uuid of the prior row) and the prior row gets
   * `superseded_at` + `superseded_by` stamped. The dashboard hides
   * superseded rows by default; the MCP `get_session_context` returns
   * active-only — coding agent never sees contradictions. */
  supersedes: string | null;
  superseded_at: string | null;
  superseded_by: string | null;
}

// ─── Dynamic artifacts: render shapes Maya can pick from ───────────────────

export type RenderKind =
  | "text"
  | "table"
  | "matrix"
  | "bar_chart"
  | "line_chart"
  | "graph"
  | "persona_cards"
  | "stack_diagram"
  | "mermaid"
  | "wireframe_flow";

/** Discriminated union of payload shapes per render_kind.
 * Components are defensive about malformed input — anything that doesn't
 * match falls back to a text card with a "couldn't render" notice. */
export type ArtifactPayload =
  | { /* text */ body_md?: string }
  | { /* table */ columns: string[]; rows: (string | number | null)[][] }
  | { /* matrix */ row_labels: string[]; col_labels: string[]; cells: (string | number | null)[][] }
  | { /* bar_chart */ x_label?: string; y_label?: string; categories: string[]; series: { name: string; values: number[] }[] }
  | { /* line_chart */ x_label?: string; y_label?: string; series: { name: string; points: { x: number | string; y: number }[] }[] }
  | { /* graph */ nodes: { id: string; label: string; group?: string }[]; edges: { from: string; to: string; label?: string }[] }
  | { /* persona_cards */ personas: { name: string; role?: string; traits?: string[]; quote?: string; pains?: string[] }[] }
  | { /* stack_diagram */ layers: { name: string; items: string[] }[] }
  | { /* mermaid */ source: string; caption?: string }
  | { /* wireframe_flow */ flow_name?: string; device: "phone"|"browser"|"extension"|"desktop"; flow_type?: "onboarding"|"core"|"settings"|"error"|"empty"|"auth"|"other"; screens: { name: string; html: string; notes?: string; derived_from?: string }[]; transitions?: { from: string; to: string; trigger?: string }[]; informed_by?: string[] };

export type ArtifactCreatedBy = "maya_pinned" | "maya_synthesized";

export interface DiscoveryArtifact {
  id: string;
  project_id: string;
  title: string;
  summary: string | null;
  render_kind: RenderKind;
  payload: Record<string, unknown>;        // shape depends on render_kind (see ArtifactPayload)
  source_run_ids: string[];
  created_by: ArtifactCreatedBy;
  /** Provenance + ingestor-specific extras. Notable shape:
   *    { source_agents?: string[] }   — populated at pin/create time */
  metadata: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
  deleted_at: string | null;
}

// Back-compat alias for code that hasn't migrated yet.
export type ResearchArtifact = DiscoveryArtifact;

export const apiGetPrd = (projectId: string) =>
  http<{ prd: Prd | null }>("GET", `/projects/${projectId}/prd`);

export const apiListSprints = (projectId: string) =>
  http<{ sprints: Sprint[] }>("GET", `/projects/${projectId}/sprints`);

export const apiListTasks = (projectId: string, status?: TaskStatus) =>
  http<{ tasks: Task[] }>(
    "GET",
    `/projects/${projectId}/tasks${status ? `?status=${status}` : ""}`,
  );

export const apiUpdateTask = (
  projectId: string,
  taskId: string,
  payload: { status: TaskStatus; agent_note?: string },
) => http<{ task: Task }>("PATCH", `/projects/${projectId}/tasks/${taskId}`, payload);

export const apiListDecisions = (
  projectId: string,
  options?: { status?: DecisionStatus; includeSuperseded?: boolean },
) => {
  const params = new URLSearchParams();
  if (options?.status) params.set("status", options.status);
  if (options?.includeSuperseded) params.set("include_superseded", "true");
  const qs = params.toString();
  return http<{ decisions: Decision[] }>(
    "GET",
    `/projects/${projectId}/decisions${qs ? `?${qs}` : ""}`,
  );
};

export const apiListDiscovery = (projectId: string) =>
  http<{ discovery: DiscoveryArtifact[] }>("GET", `/projects/${projectId}/discovery`);

// Back-compat alias — call sites are migrating to apiListDiscovery.
export const apiListResearch = apiListDiscovery;

// ─── Solutions & features (deepagent §6 product-arc loop) ──────────────────

export interface Solution {
  id: string;
  project_id: string;
  display_id: string;            // 'sol-1'
  title: string;
  summary: string | null;
  /** { pros: string[]; cons: string[] } */
  tradeoffs: { pros?: string[]; cons?: string[] } | Record<string, unknown>;
  recommended: boolean;
  needs_review: boolean;
  needs_review_why: string | null;
  version: number;
  created_at: string;
  updated_at: string;
}

export interface Feature {
  id: string;
  project_id: string;
  display_id: string;            // 'f-1'
  title: string;
  description: string | null;
  in_mvp: boolean;
  priority: number | null;
  needs_review: boolean;
  needs_review_why: string | null;
  version: number;
  created_at: string;
  updated_at: string;
}

/** A node the coherence engine flagged for another look (deepagent §8). */
export interface ReviewItem {
  type: string;                  // 'artifact' | 'decision' | 'feature' | ...
  id: string;
  why: string | null;
  title: string;
  display_id: string | null;
}

export const apiListSolutions = (projectId: string) =>
  http<{ solutions: Solution[] }>("GET", `/projects/${projectId}/solutions`);

export const apiListFeatures = (projectId: string) =>
  http<{ features: Feature[] }>("GET", `/projects/${projectId}/features`);

export const apiListReviews = (projectId: string) =>
  http<{ reviews: ReviewItem[] }>("GET", `/projects/${projectId}/reviews`);

// apiRefreshResearch removed — under the dynamic-artifacts model Maya owns
// artifact freshness. The founder asks Maya in chat to refresh, she re-runs
// the affected sub-agents and updates her pinned cards via update_artifact.

// ─── Assets (asset manager) ────────────────────────────────────────────────

export type AssetStatus = "pending" | "processing" | "ready" | "error";
export type AssetType = "file" | "repo" | "url";

export interface ProjectAsset {
  id: string;
  project_id: string;
  asset_type: AssetType;
  source_kind: string;
  source_ref: string | null;
  display_name: string;
  mime_type: string | null;
  size_bytes: number | null;
  status: AssetStatus;
  digest_md: string | null;
  digest_tokens: number | null;
  metadata: Record<string, unknown>;
  error_text: string | null;
  created_at: string;
  updated_at: string;
  deleted_at: string | null;
}

export const apiListAssets = (projectId: string) =>
  http<{ assets: ProjectAsset[] }>("GET", `/projects/${projectId}/assets`);

export const apiGetAsset = (projectId: string, assetId: string) =>
  http<{ asset: ProjectAsset }>("GET", `/projects/${projectId}/assets/${assetId}`);

export async function apiUploadAsset(
  projectId: string,
  file: File,
): Promise<ProjectAsset> {
  // Multipart upload — can't use the generic http() helper because we don't
  // want to set Content-Type (browser must set the multipart boundary).
  const { data } = await supabase.auth.getSession();
  const token = data.session?.access_token;
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${API_URL}/projects/${projectId}/assets`, {
    method: "POST",
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
    body: form,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? `Upload failed (${res.status})`);
  }
  const body = (await res.json()) as { asset: ProjectAsset };
  return body.asset;
}

export const apiDeleteAsset = (projectId: string, assetId: string) =>
  http<{ asset: ProjectAsset }>("DELETE", `/projects/${projectId}/assets/${assetId}`);


// ─── GitHub integration ──────────────────────────────────────────────────

export interface GithubConnection {
  id: string;
  github_user_login: string;
  scope: string | null;
  created_at: string;
  updated_at: string;
}

export interface GithubRepo {
  full_name: string;
  description: string | null;
  default_branch: string;
  private: boolean;
  language: string | null;
  pushed_at: string | null;
}

export interface ProjectRepoLink {
  id: string;
  project_id: string;
  github_connection_id: string;
  repo_full_name: string;
  branch: string;
  asset_id: string | null;
  last_synced_at: string | null;
}

export const apiGithubStart = () =>
  http<{ authorize_url: string; state: string }>("GET", "/integrations/github/start");

export const apiGithubExchange = (code: string) =>
  http<{ connection: GithubConnection }>("POST", "/integrations/github/exchange", { code });

export const apiGithubListConnections = () =>
  http<{ connections: GithubConnection[] }>("GET", "/integrations/github/connections");

export const apiGithubDeleteConnection = (id: string) =>
  http<{ status: string }>("DELETE", `/integrations/github/connections/${id}`);

export const apiGithubListRepos = (connectionId: string) =>
  http<{ repos: GithubRepo[] }>("GET", `/integrations/github/repos?conn_id=${encodeURIComponent(connectionId)}`);

export const apiLinkRepo = (
  projectId: string,
  payload: { connection_id: string; repo_full_name: string; branch?: string },
) => http<{ status: string; repo_full_name: string }>("POST", `/projects/${projectId}/repo`, payload);

export const apiGetRepoLink = (projectId: string) =>
  http<{ link: ProjectRepoLink | null }>("GET", `/projects/${projectId}/repo`);

export const apiUnlinkRepo = (projectId: string) =>
  http<{ status: string }>("DELETE", `/projects/${projectId}/repo`);

// ─── MCP connection (the founder's coding agent) ─────────────────────────

export interface McpKeyStatus {
  active: boolean;
  key_prefix: string | null;
  created_at: string | null;
  /** Stamped on every authed MCP request — powers the "agent connected" dot. */
  last_seen_at: string | null;
}

export const apiGetMcpKeyStatus = (projectId: string) =>
  http<{ status: McpKeyStatus }>("GET", `/projects/${projectId}/mcp-key`);

/** Mints a fresh ps_live_ key (rotating any old one). The plaintext `key` is
 *  returned ONCE — show it in the connect snippet immediately; it can never
 *  be fetched again. */
export const apiGenerateMcpKey = (projectId: string) =>
  http<{ key: { key: string; key_prefix: string; created_at: string } }>(
    "POST",
    `/projects/${projectId}/mcp-key`,
  );

export const apiRevokeMcpKey = (projectId: string) =>
  http<{ status: string }>("DELETE", `/projects/${projectId}/mcp-key`);
