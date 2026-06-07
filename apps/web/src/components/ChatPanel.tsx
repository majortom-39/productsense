import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  Send,
  Square,
  Sparkles,
  Quote,
  Loader2,
  ChevronDown,
  ChevronRight,
  ChevronLeft,
  AlertTriangle,
  Pin,
  Plus,
  Pencil,
  Trash2,
  ExternalLink,
  Paperclip,
  X,
  FileText,
  FileCheck2,
  FileWarning,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import { markdownComponentsWithMermaid } from "@/components/markdownComponents";
import remarkGfm from "remark-gfm";
import type { ChatMessage, AgentCallEntry, ChatItem, StateUpdateEntry, PendingAsk } from "@/hooks/useMayaSession";
import type { ProjectAsset } from "@/lib/api";
import { ArtifactRenderer } from "@/components/artifacts";
import type { RenderKind } from "@/components/artifacts";

interface Props {
  projectName: string;
  projectIcon?: string | null;
  sprintLabel?: string | null;
  items: ChatItem[];
  isStreaming: boolean;
  awaitingInput: boolean;
  activeAgent?: string | null;
  error: string | null;
  /** Maya's reasoning being streamed RIGHT NOW — shown live while the turn runs. */
  liveThinking?: string;
  /** Maya's answer tokens streaming RIGHT NOW (text_delta). Renders as an
   *  in-progress assistant bubble until the final `message` commits. */
  liveText?: string;
  /** Set when Maya raised an ask_founder interrupt. The question already
   *  shows as a normal assistant message; this carries the optional
   *  quick-reply options rendered as one-tap chips above the input. */
  pendingAsk?: PendingAsk | null;
  prefillText?: string | null;
  onPrefillConsumed?: () => void;
  onSend: (text: string, quoted?: string) => void;
  /** Cancel the in-flight Maya turn. Wired to the Stop button (replaces
   *  Send while Maya is processing). The backend cancels the LangGraph
   *  run; the UI settles when the `cancelled` SSE event arrives. */
  onCancelTurn?: () => void;
  /** Stash a draft the founder typed while Maya was still streaming.
   *  Auto-fires on the next turn boundary. */
  onQueueMessage?: (content: string) => void;
  /** Drop the currently queued draft without sending. */
  onClearQueuedMessage?: () => void;
  /** The currently queued draft, if any. Renders as a chip above the textarea. */
  queuedMessage?: string | null;
  /** Whether the right workspace panel is open. The chat panel hosts the toggle. */
  workspaceOpen?: boolean;
  /** Toggles WORKSPACE visibility. The button lives on the chat panel's
   *  right edge — it controls the OTHER panel, not itself. Direction of
   *  the chevron reflects which way the divider will move on click:
   *  workspaceOpen → chevron right (push divider right = workspace shrinks);
   *  !workspaceOpen → chevron left (push divider left = workspace returns). */
  onToggleWorkspace?: () => void;
  /** Asset manager surface — attached files Maya reads as context. The
   *  chat panel renders the paperclip + chips; upload/delete come from
   *  the parent (useProjectAssets hook). */
  assets?: ProjectAsset[];
  onUploadFile?: (file: File) => Promise<unknown> | void;
  onRemoveAsset?: (assetId: string) => void;
  assetError?: string | null;
  /** Dismiss the asset error banner. Founders need an explicit way to close
   *  the "File too large" warning — without it, the chip lingered until
   *  another upload succeeded. */
  onClearAssetError?: () => void;
}

/** Maya's reasoning — Claude-style. No card, no border. Just a small
 *  inline disclosure + italic muted text. While live, auto-expands and
 *  shows "thinking…" with a spinner; after completion collapses to a
 *  "show reasoning" link. */
const ThinkingBlock: React.FC<{ text: string; live?: boolean }> = ({ text, live }) => {
  const [open, setOpen] = useState(!!live);
  // Auto-open as live deltas arrive
  useEffect(() => {
    if (live) setOpen(true);
  }, [live, text]);
  if (!text.trim()) return null;

  return (
    <div className="text-[12px] text-muted-foreground">
      <button
        onClick={() => setOpen((o) => !o)}
        className="inline-flex items-center gap-1.5 hover:text-foreground transition-colors group"
      >
        {live ? (
          <Loader2 size={10} className="animate-spin text-blue-600 shrink-0" />
        ) : open ? (
          <ChevronDown size={10} className="shrink-0 opacity-70 group-hover:opacity-100" />
        ) : (
          <ChevronRight size={10} className="shrink-0 opacity-70 group-hover:opacity-100" />
        )}
        <span className="italic">
          {live ? "thinking…" : open ? "hide reasoning" : "show reasoning"}
        </span>
      </button>
      {open && (
        <div className="mt-1 ml-1 pl-3 border-l-2 border-muted-foreground/15 text-[12px] text-muted-foreground/85 italic leading-relaxed whitespace-pre-wrap">
          {text}
        </div>
      )}
    </div>
  );
};

const TOOL_PRETTY: Record<string, string> = {
  invoke_iris: "Iris · Problem Validator",
  invoke_aiden: "Aiden · Competitor Mapper",
  invoke_hugo: "Hugo · Risk Researcher",
  invoke_zara: "Zara · User Researcher",
  invoke_theo: "Theo · Tech Advisor",
  invoke_nora: "Nora · PRD Writer",
  invoke_kai: "Kai · Sprint Planner",
  invoke_wes: "Wes · Guardrail Proposer",
  log_decision: "Logging decision",
  commit_guardrails: "Locking in guardrails",
  // Direct-LLM tools (NOT a sub-agent — render as such)
  verify: "Fact-checking · grounded search",
  // Maya's dashboard curation (rendered as compact one-liners, not full cards)
  pin_artifact: "Pinning to Discovery",
  create_artifact: "Synthesizing card",
  update_artifact: "Updating Discovery card",
  delete_artifact: "Removing Discovery card",
};

/** Tool names that are housekeeping rather than substantive sub-agent work.
 *  They render as a compact single-line chip instead of a full expandable
 *  card — the founder doesn't need to inspect args/results, they just need
 *  to see that Maya did the bookkeeping. */
const COMPACT_TOOLS = new Set([
  "log_decision",
  "pin_artifact",
  "create_artifact",
  "update_artifact",
  "delete_artifact",
]);

/** Identify sub-agent tools whose result carries a render_kind we should
 *  show inline via ArtifactRenderer. */
const RICH_RESULT_TOOLS = new Set([
  "invoke_iris",
  "invoke_aiden",
  "invoke_hugo",
  "invoke_zara",
  "invoke_theo",
]);

function summariseArgs(args: Record<string, unknown>): string {
  if (!args || Object.keys(args).length === 0) return "";
  // Prefer SHORT string args (these read like topic labels) over long
  // ones (which are usually the substantive input dumped as a brief).
  // Without this rule, Wes's collapsed line shows the full failure-mode
  // text Maya passed in — useless as a title.
  const stringEntries = Object.entries(args).filter(
    ([, v]) => typeof v === "string" && (v as string).trim(),
  ) as [string, string][];
  if (stringEntries.length === 0) return "";
  // Sort by length, prefer ≤120 chars
  const sorted = stringEntries.sort((a, b) => a[1].length - b[1].length);
  const short = sorted.find(([, v]) => v.length <= 120);
  return short ? short[1] : sorted[0][1].slice(0, 120) + "…";
}

/** Per-tool override for the collapsed dispatch line title.
 *  Synthesis/housekeeping tools have long input args (e.g. Wes gets the
 *  full failure-mode summary) that aren't usable as a one-line label.
 *  Returning a fixed string here short-circuits summariseArgs. */
function dispatchTitleFor(tool: string, args: Record<string, unknown>): string {
  switch (tool) {
    case "invoke_wes":
      return "compiling guardrails";
    case "invoke_nora":
      return "drafting the PRD";
    case "update_prd_section": {
      const sec = (args as { section_id?: string }).section_id;
      return sec ? `updating PRD · ${sec}` : "updating PRD section";
    }
    case "invoke_kai":
      return "planning the sprint";
    case "update_sprint_with_diff":
      return "diffing the sprint against PRD changes";
    default:
      return summariseArgs(args);
  }
}

/** Render Maya's ask as the natural-language `question` field she emitted,
 *  with a tiny context tail (concept / target_user) only when it adds info.
 *
 *  The research sub-agents (iris/aiden/hugo/zara/theo) all carry a `question`
 *  arg now — that IS the chat-readable message. For synthesis agents that
 *  don't have a `question` field (nora/kai/wes/update_prd_section/...),
 *  we fall back to a short templated line. */
function mayaAskFor(tool: string, args: Record<string, unknown>): string {
  const a = args as Record<string, string | undefined>;
  const c = (k: string) => (typeof a[k] === "string" ? a[k]!.trim() : "");
  const question = c("question");

  // Research agents: question IS the prose. Context is a parenthetical tail.
  if (question) {
    const tail: string[] = [];
    if (c("concept")) tail.push(`re: ${c("concept")}`);
    else if (c("problem")) tail.push(`re: ${c("problem")}`);
    if (c("target_user")) tail.push(`target: ${c("target_user")}`);
    const tailStr = tail.length ? ` (${tail.join(" · ")})` : "";
    return `${question}${tailStr}`;
  }

  // Synthesis + housekeeping tools — keep the old short templates.
  switch (tool) {
    case "invoke_nora":
      return [
        `Drafting the PRD from what we've got.`,
        c("conversation_summary") && `Chat so far: ${c("conversation_summary").slice(0, 240)}…`,
        c("research_summary") && `Research findings: ${c("research_summary").slice(0, 200)}…`,
      ].filter(Boolean).join(" ");
    case "update_prd_section":
      return [
        `Quick PRD section update.`,
        c("section_id") && `Section: \`${c("section_id")}\`.`,
        c("change_summary") && `Change: ${c("change_summary")}`,
      ].filter(Boolean).join(" ");
    case "invoke_kai":
      return [
        `Breaking the PRD into a sprint.`,
        c("sprint_name") && `Sprint name: ${c("sprint_name")}.`,
      ].filter(Boolean).join(" ");
    case "update_sprint_with_diff":
      return [
        `PRD changed, diffing the sprint.`,
        c("prd_section_changed") && `Section: ${c("prd_section_changed")}.`,
        c("reason") && `Why: ${c("reason")}.`,
      ].filter(Boolean).join(" ");
    case "invoke_wes":
      return `Distilling failure patterns into guardrail drafts (founder approves before they lock in).`;
    case "commit_guardrails": {
      const n = Array.isArray(a.drafts) ? (a.drafts as unknown[]).length : 0;
      const note = c("approval_note");
      return n > 0
        ? `Locking in ${n} founder-approved guardrail${n === 1 ? "" : "s"}${note ? ` (${note})` : ""}.`
        : `Locking in approved guardrails.`;
    }
    case "verify":
      return c("claim") || "Fact-checking a claim.";
    default: {
      const firstVal = summariseArgs(args);
      return firstVal ? `Looking into: ${firstVal}` : "Looking into this.";
    }
  }
}

const TOOL_FIRST_NAME: Record<string, string> = {
  invoke_iris: "Iris",
  invoke_aiden: "Aiden",
  invoke_hugo: "Hugo",
  invoke_zara: "Zara",
  invoke_theo: "Theo",
  invoke_nora: "Nora",
  update_prd_section: "Nora",
  invoke_kai: "Kai",
  update_sprint_with_diff: "Kai",
  invoke_wes: "Wes",
  // verify is NOT a sub-agent — it's a direct grounded LLM call. We
  // surface it with a different label below ("Fact-check") so the chat
  // doesn't imply Maya is talking to a person.
  verify: "Fact-check",
};

/** Tools that render as "Maya → X: ...\nX replied: ..." vs tools that
 *  render in a single-actor voice (no second-party framing). Verify is
 *  the latter — it's a tool result, not a conversation. */
const NON_AGENT_TOOLS = new Set(["verify"]);

const QuotedSnippet: React.FC<{ text: string }> = ({ text }) => (
  <div className="mb-2 px-3 py-2 rounded-xl bg-muted/60 border-l-2 border-primary text-[12px] text-muted-foreground italic">
    <Quote size={10} className="inline mr-1.5 -mt-0.5 text-primary" />
    {text}
  </div>
);

/** Compact one-liner chip for housekeeping tools (pin/create/update/delete
 *  artifact, log_decision). No expansion, no args inspection. The founder
 *  just needs to see that Maya did the bookkeeping — and when something
 *  fails, the chip surfaces the actual error message instead of going
 *  silently red. */
const CompactToolChip: React.FC<{ entry: AgentCallEntry }> = ({ entry }) => {
  const pretty = TOOL_PRETTY[entry.tool] ?? entry.tool;
  const isError = entry.status === "error";
  const isRunning = entry.status === "running";
  const result = entry.result as Record<string, unknown> | null | undefined;
  const title =
    typeof result?.title === "string"
      ? (result.title as string)
      : typeof (entry.args as Record<string, unknown>)?.title === "string"
      ? ((entry.args as Record<string, unknown>).title as string)
      : "";

  // When the tool errored, show WHAT went wrong (server message) instead
  // of an empty red chip. Falls back to the legacy "tool · title" layout
  // for non-error states. The error message often carries actionable
  // detail (column-not-found, RLS denied, etc.) — surface it.
  const errorMessage =
    isError && typeof result?.message === "string"
      ? (result.message as string)
      : "";

  const icon = entry.tool === "pin_artifact" ? (
    <Pin size={11} className="shrink-0" />
  ) : entry.tool === "create_artifact" ? (
    <Plus size={11} className="shrink-0" />
  ) : entry.tool === "update_artifact" ? (
    <Pencil size={11} className="shrink-0" />
  ) : entry.tool === "delete_artifact" ? (
    <Trash2 size={11} className="shrink-0" />
  ) : (
    <Sparkles size={11} className="shrink-0" />
  );

  return (
    <div
      className={`inline-flex items-start gap-1.5 px-2.5 py-1 rounded-md text-[11px] border max-w-full ${
        isError
          ? "bg-rose-50 text-rose-700 border-rose-200"
          : isRunning
          ? "bg-blue-50 text-blue-700 border-blue-200"
          : "bg-muted/40 text-muted-foreground border-border"
      }`}
      title={errorMessage || undefined}
    >
      {isRunning ? (
        <Loader2 size={11} className="animate-spin shrink-0 mt-0.5" />
      ) : (
        <span className="mt-0.5">{icon}</span>
      )}
      <span className="font-medium shrink-0">{pretty}</span>
      {isError && errorMessage ? (
        <span className="text-rose-800 truncate max-w-[420px]">
          — failed: {errorMessage}
        </span>
      ) : (
        title && (
          <span className="text-foreground/70 truncate max-w-[260px]">
            · {title}
          </span>
        )
      )}
    </div>
  );
};

/** State-update chip — slim inline marker for non-dispatch tools
 *  (stage confirmations, decision logging, artifact CRUD, verify).
 *
 *  Replaces the prior behaviour of rendering these as "Asked Sub-agent"
 *  cards in chat. The 12-stage flow advances by these tools constantly;
 *  a card per tick would pollute the chat. A small chip with the label +
 *  optional one-line summary keeps the conversation readable while still
 *  showing the founder that state changed.
 *
 *  Verify is a special case: it carries a meaningful grounded-search
 *  payload (finding + sources) the founder may want to inspect. The chip
 *  becomes expandable when `tool === "verify"`. */
const StateUpdateChip: React.FC<{ entry: StateUpdateEntry }> = ({ entry }) => {
  const [open, setOpen] = useState(false);
  const isRefused = entry.status === "stage_refused";
  const isError = entry.status === "error";
  const isVerify = entry.tool === "verify";
  const result = (entry.result ?? null) as Record<string, unknown> | null;
  const verifyFinding = isVerify && typeof result?.finding === "string"
    ? (result.finding as string)
    : "";
  const verifyClaim = isVerify && typeof result?.claim === "string"
    ? (result.claim as string)
    : "";
  const verifySources = isVerify && Array.isArray(result?.sources)
    ? ((result.sources as unknown[]).filter(
        (s) => s && typeof s === "object" && typeof (s as { url?: unknown }).url === "string",
      ) as { label?: string; url: string }[])
    : [];
  // For verify, the "summary" we display on the chip is a short truncated
  // claim — never the full grounded result. Founders click to expand.
  const chipSummary = isVerify
    ? (verifyClaim || entry.summary)
    : entry.summary;

  // Label honesty: when the action FAILED, override the backend's
  // success-shaped label ("Positioning locked") with one that matches
  // reality ("Couldn't lock positioning"). The data stays as-is; only
  // the display reads truthfully. Keeps the chip from claiming success
  // it doesn't have.
  const displayLabel = (() => {
    if (!isError && !isRefused) return entry.label;
    const lower = entry.label.toLowerCase();
    if (lower.includes("locked")) {
      // "Positioning locked" → "Couldn't lock positioning"
      const subject = entry.label.replace(/\s*locked\s*$/i, "").trim();
      return `Couldn't lock ${subject.toLowerCase()}`;
    }
    if (lower.includes("recorded")) {
      // "Dev environment recorded" → "Couldn't record dev environment"
      const subject = entry.label.replace(/\s*recorded\s*$/i, "").trim();
      return `Couldn't record ${subject.toLowerCase()}`;
    }
    if (lower.includes("approved")) {
      return `Couldn't approve — ${entry.label.replace(/\s*approved\s*$/i, "").trim().toLowerCase()}`;
    }
    // Generic fallback for other failed actions.
    return `Failed: ${entry.label.toLowerCase()}`;
  })();

  const Wrapper: React.ElementType = isVerify ? "button" : "div";
  return (
    <div className="flex flex-col gap-1.5 max-w-full">
      <Wrapper
        {...(isVerify ? { onClick: () => setOpen((o) => !o), type: "button" } : {})}
        className={`inline-flex items-start gap-1.5 px-2.5 py-1 rounded-md text-[11px] border max-w-full text-left ${
          isError
            ? "bg-rose-50 text-rose-700 border-rose-200"
            : isRefused
            ? "bg-amber-50 text-amber-800 border-amber-200"
            : "bg-muted/40 text-muted-foreground border-border"
        } ${isVerify ? "hover:bg-muted/70 transition-colors cursor-pointer" : ""}`}
        title={chipSummary || undefined}
      >
        {isVerify ? (
          open ? <ChevronDown size={11} className="shrink-0 mt-0.5" />
               : <ChevronRight size={11} className="shrink-0 mt-0.5" />
        ) : (
          <Sparkles size={11} className="shrink-0 mt-0.5" />
        )}
        <span className="font-medium shrink-0">{displayLabel}</span>
        {chipSummary && (
          <span className="text-foreground/70 truncate max-w-[420px]">
            · {chipSummary}
          </span>
        )}
      </Wrapper>
      {isVerify && open && verifyFinding && (
        <div className="ml-3 pl-3 border-l-2 border-muted-foreground/15 text-[12px] text-foreground/85 space-y-2">
          <div className="prose prose-sm prose-warm max-w-none [&_p]:my-1 [&_strong]:font-semibold [&_em]:italic [&_code]:px-1 [&_code]:py-0.5 [&_code]:bg-muted/50 [&_code]:rounded">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{verifyFinding}</ReactMarkdown>
          </div>
          {verifySources.length > 0 && (
            <div className="flex items-center gap-2 flex-wrap pt-1">
              <span className="text-[10px] uppercase tracking-wider text-muted-foreground/70">
                Sources
              </span>
              {verifySources.map((s, i) => (
                <a
                  key={i}
                  href={s.url}
                  target="_blank"
                  rel="noreferrer"
                  className="text-[10.5px] text-muted-foreground hover:text-foreground underline-offset-2 hover:underline"
                >
                  {s.label || new URL(s.url).hostname.replace(/^www\./, "")}
                </a>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

/** Sub-agent dispatch — Claude-Code-style inline, NOT a card.
 *
 * Renders as a single indented line under Maya's avatar column, with a
 * left rule (like the thinking block). Click the chevron to expand the
 * actual Maya↔Sub-agent conversation. No border, no colored fill, no
 * rounded card — it's a side-thread of the same chat, not a separate
 * UI surface.
 *
 *   ↳ Asked Theo · Live debate analyzer…                   [▸]
 *
 * (When expanded, the conversation appears below the chevron, indented
 *  with a thin left rule.)
 */
const AgentCallCard: React.FC<{
  entry: AgentCallEntry;
  pinnedRunIds: Set<string>;
}> = ({ entry, pinnedRunIds }) => {
  const [open, setOpen] = useState(false);
  const isError = entry.status === "error";
  const isRunning = entry.status === "running";
  const isClarifying = entry.status === "clarification_needed";
  const pretty = TOOL_PRETTY[entry.tool] ?? entry.tool;
  const argSummary = dispatchTitleFor(entry.tool, entry.args);
  const turns = entry.turns ?? [{
    args: entry.args,
    status: entry.status,
    result: entry.result,
    startedAt: entry.startedAt,
    completedAt: entry.completedAt,
  }];

  // Check whether THIS sub-agent's run_id was subsequently pinned by Maya.
  const latestResult = (entry.result ?? null) as Record<string, unknown> | null;
  const runId = typeof latestResult?.run_id === "string" ? (latestResult.run_id as string) : null;
  const isPinned = !!runId && pinnedRunIds.has(runId);

  // Status verb in plain English: "Asking", "Asked", "Asked back",
  // "Hit a snag". Reads like a transcript line, not a state machine.
  const verb = isRunning
    ? "Asking"
    : isClarifying
    ? "Asked back"
    : isError
    ? "Hit a snag with"
    : "Asked";

  return (
    <div className="text-[12px] text-muted-foreground">
      <button
        onClick={() => setOpen((o) => !o)}
        className="inline-flex items-start gap-1.5 hover:text-foreground transition-colors group text-left max-w-full"
      >
        {isRunning ? (
          <Loader2 size={11} className="animate-spin text-blue-600 shrink-0 mt-0.5" />
        ) : isError ? (
          <AlertTriangle size={11} className="text-rose-600 shrink-0 mt-0.5" />
        ) : isClarifying ? (
          <AlertTriangle size={11} className="text-amber-600 shrink-0 mt-0.5" />
        ) : open ? (
          <ChevronDown size={11} className="shrink-0 mt-0.5 opacity-70 group-hover:opacity-100" />
        ) : (
          <ChevronRight size={11} className="shrink-0 mt-0.5 opacity-70 group-hover:opacity-100" />
        )}
        <span className="italic leading-relaxed">
          {verb}{" "}
          <span className="not-italic font-medium text-foreground/85">
            {pretty.split(" · ")[0]}
            {pretty.includes(" · ") && (
              <span className="font-normal text-muted-foreground">
                {" · "}
                {pretty.split(" · ").slice(1).join(" · ").replace(/[()]/g, "")}
              </span>
            )}
          </span>
          {argSummary && (
            <>
              {" "}
              <span className="text-muted-foreground/80">— {argSummary}</span>
            </>
          )}
          {turns.length > 1 && (
            <span className="ml-1.5 text-[10px] not-italic text-muted-foreground/60">
              ({turns.length} rounds)
            </span>
          )}
          {isPinned && (
            <span
              title="Maya pinned this finding to the Discovery tab"
              className="ml-1.5 inline-flex items-center gap-0.5 text-[10px] not-italic font-medium text-primary"
            >
              <Pin size={8} />
              pinned
            </span>
          )}
        </span>
      </button>

      {open && (
        <div className="mt-2 ml-1 pl-3 border-l-2 border-muted-foreground/15 space-y-3">
          {turns.map((turn, idx) => (
            <AgentTurnView
              key={idx}
              turn={turn}
              tool={entry.tool}
              roundNumber={idx + 1}
              totalRounds={turns.length}
            />
          ))}
        </div>
      )}
    </div>
  );
};

/** Render a single sub-agent round as a back-and-forth chat thread:
 *
 *    👩 Maya:  "Hey Theo — is this shippable? Live debate analyzer..."
 *    👨 Theo:  "Doing all of this perfectly live is a trap..."
 *              • Diarization on overlapping speech is shaky
 *              • LLM fact-check adds 2-5s latency
 *              [table / chart, if structured payload]
 *              Sources: ...
 *
 * Replaces the old form-style "BRIEF / FINDING" panel. The structured
 * args are still under the hood (Maya emits them via bind_tools and the
 * dispatcher uses them) — we just present them as natural prose. A
 * subtle "show raw" toggle is available for debugging.
 */
const AgentTurnView: React.FC<{
  turn: AgentCallEntry["turns"][number];
  tool: string;
  roundNumber: number;
  totalRounds: number;
}> = ({ turn, tool, roundNumber, totalRounds }) => {
  const isRunning = turn.status === "running";
  const isClarifying = turn.status === "clarification_needed";
  const isError = turn.status === "error";
  const isDone = turn.status === "complete";
  const resultObj =
    turn.result && typeof turn.result === "object" && !Array.isArray(turn.result)
      ? (turn.result as Record<string, unknown>)
      : null;

  const agentName = TOOL_FIRST_NAME[tool] ?? "Sub-agent";
  const mayaPrompt = mayaAskFor(tool, turn.args);
  const clarification = (turn.args as Record<string, unknown>)?.clarification as
    | string
    | undefined;

  // Result payloads carry a render_kind + structured payload for rich
  // visualization (table, chart, etc.). The same renderer the dashboard
  // uses gets called inline when applicable.
  const renderKind =
    resultObj && typeof resultObj.render_kind === "string"
      ? (resultObj.render_kind as RenderKind)
      : null;
  const payload =
    resultObj && resultObj.payload && typeof resultObj.payload === "object"
      ? (resultObj.payload as Record<string, unknown>)
      : {};
  // New SpecialistResult shape: { summary, detail, sources: string[] }.
  // Legacy sub-agent shape: { finding, bullets, sources: {url,label}[] }.
  // Support both so live results and any hydrated legacy rows render.
  const headline =
    (typeof resultObj?.summary === "string" && (resultObj.summary as string)) ||
    (typeof resultObj?.finding === "string" && (resultObj.finding as string)) ||
    "";
  const detail = typeof resultObj?.detail === "string" ? (resultObj.detail as string) : "";
  const bullets = Array.isArray(resultObj?.bullets)
    ? ((resultObj?.bullets as unknown[]).filter((x) => typeof x === "string") as string[])
    : [];
  // sources may be a list of plain URL strings (new) or {url,label} objects (legacy).
  const sources: { label?: string; url: string }[] = Array.isArray(resultObj?.sources)
    ? (resultObj?.sources as unknown[])
        .map((x) => {
          if (typeof x === "string" && x.trim()) return { url: x.trim() };
          if (x && typeof x === "object" && typeof (x as { url?: unknown }).url === "string") {
            return { url: (x as { url: string }).url, label: (x as { label?: string }).label };
          }
          return null;
        })
        .filter((x): x is { label?: string; url: string } => x !== null)
    : [];
  const isRichRender =
    RICH_RESULT_TOOLS.has(tool)
    && renderKind !== null
    && renderKind !== "text";

  // If the model returned an error-shaped object (downstream DB failure,
  // postgrest schema cache, etc.), present it as the agent saying "I hit
  // a snag" rather than a raw JSON dump.
  const looksLikeError =
    !isDone &&
    resultObj &&
    (typeof resultObj.code === "string" || resultObj.status === "error");
  // Prefer message (specific tech detail) → fall back to finding (the
  // sub-agent's human explanation) → generic last-resort. Wes especially
  // returns a useful `finding` on error even when `message` is absent.
  const errorMessage = looksLikeError
    ? (typeof resultObj?.message === "string"
        ? (resultObj.message as string)
        : typeof resultObj?.finding === "string"
        ? (resultObj.finding as string)
        : "ran into a system error")
    : "";

  // Flat, Claude-Code-style render: short speaker prefix in italic muted,
  // body inline below. No avatars, no cards, no colored fills. Just text.
  return (
    <div className="space-y-2.5 text-[12px] leading-relaxed">
      {totalRounds > 1 && (
        <p className="text-[10px] uppercase tracking-wider text-muted-foreground/70">
          Round {roundNumber}
        </p>
      )}

      {/* Maya's ask. For sub-agents this is "Maya → Theo: ...". For
       *  non-agent tools (verify) we use single-actor framing so the
       *  chat doesn't imply Maya is talking to a person — "Checking: <claim>"
       *  reads correctly for a direct grounded search. */}
      <div>
        {NON_AGENT_TOOLS.has(tool) ? (
          <>
            <span className="text-muted-foreground italic">Checking: </span>
            <span className="text-foreground/85">{mayaPrompt}</span>
          </>
        ) : (
          <>
            <span className="text-muted-foreground italic">Maya → {agentName}: </span>
            <span className="text-foreground/85">{mayaPrompt}</span>
          </>
        )}
        {clarification && (
          <div className="mt-1 text-foreground/75">
            <span className="text-muted-foreground italic">↳ Maya answered: </span>
            <span>{clarification}</span>
          </div>
        )}
      </div>

      {/* The reply — sub-agents say "X replied:", non-agent tools say
       *  "Result:" (a tool returning a value is not "replying"). */}
      {isRunning ? null : isClarifying ? (
        <div>
          <span className="text-amber-700 italic">{agentName} asks back: </span>
          <span className="text-foreground/85">
            {(turn.result as { clarifying_question?: string } | null)?.clarifying_question ||
              turn.clarifyingQuestion ||
              "(no question text)"}
          </span>
        </div>
      ) : looksLikeError || isError ? (
        <p className="text-rose-700">
          <span className="italic">{agentName} hit a snag: </span>
          {errorMessage || (typeof turn.result === "string" ? turn.result : "system error")}.
          Maya will work around it.
        </p>
      ) : isDone ? (
        <div>
          <span className="text-muted-foreground italic">
            {NON_AGENT_TOOLS.has(tool) ? "Result: " : `${agentName} replied: `}
          </span>
          {headline && (
            <span className="text-foreground/90">
              {/* Inline markdown so **bold**, *italic*, `code` render. The
                  headline (summary) is one sentence — span keeps it on the
                  same line as the "Theo replied:" prefix. */}
              <span className="prose prose-sm prose-warm max-w-none inline [&_p]:inline [&_p]:m-0 [&_strong]:font-semibold [&_em]:italic [&_code]:px-1 [&_code]:py-0.5 [&_code]:bg-muted/50 [&_code]:rounded">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{headline}</ReactMarkdown>
              </span>
            </span>
          )}
          {detail && (
            /* The specialist's full body of work (SpecialistResult.detail) —
               evidence bullets, the drafted artifact, the ranked list. */
            <div className="mt-1.5 prose prose-sm prose-warm max-w-none text-foreground/80 [&_p]:my-1 [&_ul]:my-1 [&_ol]:my-1 [&_li]:my-0.5 [&_strong]:font-semibold [&_em]:italic [&_h2]:text-[12.5px] [&_h3]:text-[12px] [&_code]:px-1 [&_code]:py-0.5 [&_code]:bg-muted/50 [&_code]:rounded">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{detail}</ReactMarkdown>
            </div>
          )}
          {bullets.length > 0 && (
            <ul className="mt-1.5 space-y-1 text-foreground/80">
              {bullets.map((b, i) => (
                <li key={i} className="pl-3 relative">
                  <span className="absolute left-0 top-1.5 w-1 h-1 rounded-full bg-foreground/40" />
                  <span className="prose prose-sm prose-warm max-w-none inline [&_p]:inline [&_p]:m-0 [&_strong]:font-semibold [&_em]:italic [&_code]:px-1 [&_code]:py-0.5 [&_code]:bg-muted/50 [&_code]:rounded">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>{b}</ReactMarkdown>
                  </span>
                </li>
              ))}
            </ul>
          )}
          {isRichRender && (
            <div className="mt-2.5">
              <ArtifactRenderer
                render_kind={renderKind as RenderKind}
                payload={payload}
                textBody={headline}
              />
            </div>
          )}
          {sources.length > 0 && (
            <div className="mt-2 flex items-center gap-2 flex-wrap">
              <span className="text-[10px] uppercase tracking-wider text-muted-foreground/70">
                Sources
              </span>
              {sources.map((s, i) => (
                <a
                  key={i}
                  href={s.url}
                  target="_blank"
                  rel="noreferrer"
                  className="text-[10.5px] text-muted-foreground hover:text-foreground flex items-center gap-1"
                >
                  <ExternalLink size={9} />
                  {s.label || s.url}
                </a>
              ))}
            </div>
          )}
        </div>
      ) : null}

    </div>
  );
};

/* Owner-column pattern: every assistant row is a flex with a 28px avatar
   slot on the left and a flex-1 content column on the right. Messages,
   agent-call cards, and live-thinking blocks all use the same shell so
   they share a single vertical alignment edge. */
const AVATAR_SIZE = 28;

const AssistantRow: React.FC<{
  /** Show the actual avatar in the slot — only true for the FIRST item in a turn. */
  showAvatar?: boolean;
  agentName?: string;
  children: React.ReactNode;
}> = ({ showAvatar, agentName = "Maya", children }) => (
  <div className="flex items-start gap-3 animate-in fade-in-0 slide-in-from-bottom-2 duration-300">
    <div className="shrink-0" style={{ width: AVATAR_SIZE, height: AVATAR_SIZE }}>
      {showAvatar && (
        <img
          src={`/Agents/${agentName}.png`}
          alt={agentName}
          className="w-7 h-7 rounded-full object-cover bg-muted ring-1 ring-border"
          onError={(e) => {
            (e.target as HTMLImageElement).style.visibility = "hidden";
          }}
        />
      )}
    </div>
    <div className="flex-1 min-w-0">{children}</div>
  </div>
);

/** Bubble — renders one message.
 *  `isTurnLeader` controls whether to show the avatar + "Maya · Product
 *  Manager" header. False when this message is a continuation of a Maya
 *  turn that already opened with another assistant item (an agent_call,
 *  another message). Mirrors Claude Code's "one header per assistant
 *  block, dispatches and prose nest under it" pattern. */
/* Memoized so this component doesn't re-render when the parent ChatPanel
 * re-renders (e.g. on every keystroke in the textarea). Without React.memo,
 * each Bubble re-runs ReactMarkdown — and with 80+ messages that's a real
 * cost per keystroke. The memo's default reference equality is enough here
 * because `message` objects in the items list are stable (only mutated on
 * server events, not on input).
 *
 * SHIP-10: paired with extracting the textarea into its own component so
 * draft state changes never trigger a parent re-render in the first place. */
const Bubble: React.FC<{ message: ChatMessage; isTurnLeader?: boolean }> = React.memo(({
  message,
  isTurnLeader = true,
}) => {
  const isUser = message.role === "user";
  const agent = message.agent ?? (isUser ? undefined : "Maya");
  const agentName = agent ? agent.charAt(0).toUpperCase() + agent.slice(1).toLowerCase() : undefined;

  if (isUser) {
    return (
      <div className="flex justify-end animate-in fade-in-0 slide-in-from-bottom-2 duration-300">
        <div className="max-w-[80%] px-4 py-2.5 rounded-2xl rounded-tr-md text-[14.5px] leading-[1.6] bg-primary text-primary-foreground shadow-sm">
          {message.quoted && <QuotedSnippet text={message.quoted} />}
          <div className="prose prose-sm max-w-none [&_p]:my-1 [&_p:first-child]:mt-0 [&_p:last-child]:mb-0 [&_ul]:my-1 [&_ol]:my-1 [&_strong]:font-semibold [&_em]:italic [&_*]:!text-primary-foreground [&_strong]:!text-primary-foreground">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content}</ReactMarkdown>
          </div>
        </div>
      </div>
    );
  }

  return (
    <AssistantRow showAvatar={isTurnLeader} agentName={agentName}>
      {isTurnLeader && (
        <div className="flex items-baseline gap-2 mb-1.5">
          <span className="text-[13px] font-semibold text-foreground">{agentName}</span>
          <span className="text-[11px] text-muted-foreground">· Product Manager</span>
        </div>
      )}
      {message.thinking && (
        <div className="mb-2">
          <ThinkingBlock text={message.thinking} />
        </div>
      )}
      {message.quoted && <QuotedSnippet text={message.quoted} />}
      <div className="prose prose-sm prose-warm max-w-none text-[14.5px] leading-[1.65] [&_p]:my-1.5 [&_p:first-child]:mt-0 [&_p:last-child]:mb-0 [&_ul]:my-1.5 [&_ol]:my-1.5 [&_strong]:font-semibold [&_em]:italic">
        <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponentsWithMermaid}>{message.content}</ReactMarkdown>
      </div>
    </AssistantRow>
  );
});
Bubble.displayName = "Bubble";

export function ChatPanel({
  projectName,
  projectIcon,
  sprintLabel,
  items,
  isStreaming,
  awaitingInput,
  activeAgent,
  error,
  liveThinking,
  liveText,
  pendingAsk,
  prefillText,
  onPrefillConsumed,
  onSend,
  onCancelTurn,
  onQueueMessage,
  onClearQueuedMessage,
  queuedMessage,
  workspaceOpen,
  onToggleWorkspace,
  assets,
  onUploadFile,
  onClearAssetError,
  onRemoveAsset,
  assetError,
}: Props) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const textRef = useRef<HTMLTextAreaElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const [draft, setDraft] = useState("");
  // Multiple quoted blocks — the founder can "Add to chat" several
  // dashboard cards before typing their question. Each is rendered as
  // a removable chip stacked above the textarea. On send, all blocks
  // get concatenated into the message prefix.
  const [quotedBlocks, setQuotedBlocks] = useState<string[]>([]);
  const [dragOver, setDragOver] = useState(false);

  // Derive which sub-agent run_ids Maya has pinned this session. Used to
  // surface a "Pinned ✓" badge on the corresponding AgentCallCard. We scan
  // pin_artifact entries whose result.status='ok' and harvest the run_id
  // arg they were called with.
  const pinnedRunIds = useMemo(() => {
    const set = new Set<string>();
    for (const it of items) {
      if (it.kind !== "agent_call" || it.tool !== "pin_artifact") continue;
      const result = (it.result ?? null) as Record<string, unknown> | null;
      if (!result || result.status !== "ok") continue;
      // The run_id was an INPUT to pin_artifact (in args, not result).
      const args = (it.args ?? {}) as Record<string, unknown>;
      const rid = typeof args.run_id === "string" ? (args.run_id as string) : null;
      if (rid) set.add(rid);
    }
    return set;
  }, [items]);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [items, isStreaming, activeAgent]);

  // Auto-grow the textarea up to 6 lines, then enable internal scrolling.
  //
  // Was useLayoutEffect — fired SYNCHRONOUSLY on every keystroke and
  // forced layout recalc + a re-render of the entire ChatPanel (which
  // renders the whole chat history). That was the source of "typing
  // lag a couple milliseconds per character" in long sessions.
  //
  // Now: useEffect + requestAnimationFrame. Same visual outcome — the
  // textarea grows as you type — but the recalc happens after the
  // browser has committed the paint, so the user never sees a stall.
  useEffect(() => {
    const el = textRef.current;
    if (!el) return;
    const raf = requestAnimationFrame(() => {
      el.style.height = "auto";
      const cs = getComputedStyle(el);
      const lineHeight = parseFloat(cs.lineHeight) || 20;
      const pad = parseFloat(cs.paddingTop) + parseFloat(cs.paddingBottom);
      const maxH = lineHeight * 6 + pad;
      const h = Math.min(el.scrollHeight, maxH);
      el.style.height = `${h}px`;
      el.style.overflowY = el.scrollHeight > maxH ? "auto" : "hidden";
    });
    return () => cancelAnimationFrame(raf);
  }, [draft]);

  useEffect(() => {
    if (!prefillText) return;
    // Each "Add to chat" click appends a new block instead of replacing
    // — founders often want to reference multiple cards in one question.
    // Dedupe so double-clicks don't create duplicates.
    setQuotedBlocks((prev) =>
      prev.includes(prefillText) ? prev : [...prev, prefillText],
    );
    textRef.current?.focus();
    onPrefillConsumed?.();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [prefillText]);

  function send() {
    const text = draft.trim();
    if (!text) return;
    // Concatenate all quoted blocks with separators so Maya sees them as
    // a list of referenced material — same way she'd see a paper with
    // multiple footnotes. The last argument to onSend is the combined
    // quote string (or undefined if nothing was attached).
    const combinedQuote =
      quotedBlocks.length > 0 ? quotedBlocks.join("\n\n---\n\n") : undefined;
    onSend(text, combinedQuote);
    setDraft("");
    setQuotedBlocks([]);
  }

  async function handleFiles(files: FileList | File[] | null) {
    if (!files || !onUploadFile) return;
    const arr = Array.from(files);
    // Upload serially so the UI shows each chip materialize as it lands.
    // Parallel would be marginally faster but creates a flash of N chips
    // appearing at once, which reads as "did something break?"
    for (const f of arr) {
      await onUploadFile(f);
    }
  }

  // Visible asset list — newest first, hides deleted (server already filters).
  const visibleAssets = (assets ?? []).filter((a) => !a.deleted_at);

  return (
    <div className="flex-1 flex flex-col h-full min-w-0 rounded-3xl bg-card border border-border overflow-hidden">
      <div className="px-5 py-4 border-b border-border flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 min-w-0">
          {projectIcon && <span className="text-base shrink-0">{projectIcon}</span>}
          <h2 className="text-sm font-semibold text-foreground truncate">{projectName}</h2>
          {sprintLabel && (
            <span className="ml-2 px-2 py-0.5 rounded-md bg-emerald-50 text-emerald-700 text-[10px] font-medium border border-emerald-100 shrink-0">
              {sprintLabel}
            </span>
          )}
        </div>
        {/* Single divider toggle on the chat's right edge. Always controls
            the workspace (the other panel). Chevron direction shows where
            the divider moves on click. */}
        {onToggleWorkspace && (
          <button
            onClick={onToggleWorkspace}
            title={workspaceOpen ? "Hide workspace" : "Show workspace"}
            aria-label={workspaceOpen ? "Hide workspace panel" : "Show workspace panel"}
            className="shrink-0 w-8 h-8 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted transition-colors flex items-center justify-center"
          >
            {workspaceOpen ? <ChevronRight size={17} /> : <ChevronLeft size={17} />}
          </button>
        )}
      </div>

      <div
        ref={scrollRef}
        className="flex-1 overflow-y-auto px-5 py-6"
        // scrollbar-gutter reserves space for the scrollbar at all times, so
        // content doesn't jiggle when it appears/disappears.
        style={{ scrollbarGutter: "stable" }}
      >
        {/* Reading column adapts to workspace state:
              - workspace OPEN  → 720px (focused column; details panel takes the rest)
              - workspace CLOSED → 920px (wider for solo-reading mode)
            The breakpoint is driven by `workspaceOpen` which is already in
            scope. No reflow on toggle — only the column max-width changes. */}
        <div
          className={`mx-auto w-full space-y-6 transition-[max-width] duration-300 ${
            workspaceOpen ? "max-w-[720px]" : "max-w-[920px]"
          }`}
        >
          {items.length === 0 && !isStreaming && (
            <p className="text-sm text-muted-foreground text-center mt-8">
              Maya will start the conversation in a moment…
            </p>
          )}
          {/* Reorder items so state_update chips land at the END of each
              Maya-turn rather than interleaved with her prose. The data in
              `items` is in temporal arrival order (correct for replay /
              audit), but the chat surface enforces a contract:
              within one Maya turn, prose + agent_call cards render in
              temporal order, then all state_update chips render together at
              the end of the turn. This kills the "chip lands between two
              sentences of the same paragraph" bug. */}
          {(() => {
            const groups: ChatItem[][] = [];
            let current: ChatItem[] = [];
            for (const it of items) {
              if (it.kind === "message" && it.role === "user") {
                if (current.length > 0) {
                  groups.push(current);
                  current = [];
                }
                groups.push([it]);
              } else {
                current.push(it);
              }
            }
            if (current.length > 0) groups.push(current);
            const ordered: ChatItem[] = [];
            for (const g of groups) {
              if (g.length === 1 && g[0].kind === "message" && (g[0] as ChatMessage).role === "user") {
                ordered.push(g[0]);
                continue;
              }
              const nonState = g.filter((x) => x.kind !== "state_update");
              const states = g.filter((x) => x.kind === "state_update");
              ordered.push(...nonState, ...states);
            }
            return ordered;
          })().map((it, i, arr) => {
            // An item is a "turn leader" when it's the first assistant
            // item after a user message (or it's the very first item).
            // Turn leaders show Maya's avatar + name header. Continuations
            // hide both — so a single Maya block visually owns the
            // dispatches + her final prose, like Claude Code.
            const prev = arr[i - 1];
            const isTurnLeader =
              !prev || (prev.kind === "message" && prev.role === "user");

            if (it.kind === "message") {
              return <Bubble key={it.id} message={it} isTurnLeader={isTurnLeader} />;
            }
            if (it.kind === "state_update") {
              const chip = <StateUpdateChip entry={it} />;
              if (isTurnLeader) {
                return (
                  <AssistantRow key={it.id} showAvatar agentName="Maya">
                    <div className="flex items-baseline gap-2 mb-1.5">
                      <span className="text-[13px] font-semibold text-foreground">Maya</span>
                      <span className="text-[11px] text-muted-foreground">· Product Manager</span>
                    </div>
                    {chip}
                  </AssistantRow>
                );
              }
              return (
                <AssistantRow key={it.id} showAvatar={false}>
                  {chip}
                </AssistantRow>
              );
            }
            const inner = COMPACT_TOOLS.has(it.tool) ? (
              <CompactToolChip entry={it} />
            ) : (
              <AgentCallCard entry={it} pinnedRunIds={pinnedRunIds} />
            );
            if (isTurnLeader) {
              // First assistant item after a user message — open the Maya
              // header here so the dispatch / chip is visually owned by Maya.
              return (
                <AssistantRow key={it.id} showAvatar agentName="Maya">
                  <div className="flex items-baseline gap-2 mb-1.5">
                    <span className="text-[13px] font-semibold text-foreground">Maya</span>
                    <span className="text-[11px] text-muted-foreground">· Product Manager</span>
                  </div>
                  {inner}
                </AssistantRow>
              );
            }
            return (
              <AssistantRow key={it.id} showAvatar={false}>
                {inner}
              </AssistantRow>
            );
          })}
          {/* Live: thinking / spinner. Continuation of the current turn
              if the last item in `items` is already an assistant entry
              (agent_call OR an assistant message). Only shows Maya's
              avatar header when nothing of hers has appeared yet.

              Phase 10: when there's already a `running` agent_call card
              for the active agent in the item stream, suppress the
              "Theo · Tech Advisor…" indicator here — the card itself
              already shows the spinner, and rendering both made the
              founder see the same dispatch twice. We still render the
              live block when EITHER (a) Maya is thinking with no
              corresponding agent_call yet, or (b) the activeAgent is a
              synthesis/pure tool that doesn't get its own card. */}
          {isStreaming && (() => {
            const last = items[items.length - 1];
            const lastIsUser = !last || (last.kind === "message" && last.role === "user");
            const showHeader = lastIsUser;
            const hasLiveCardForActive = !!activeAgent && items.some(
              (it) => it.kind === "agent_call" && it.tool === activeAgent && it.status === "running",
            );
            const hasThinking = (liveThinking ?? "").trim().length > 0;
            const hasLiveText = (liveText ?? "").trim().length > 0;
            // Nothing useful to show: card is already rendering the spinner
            // for this agent and there's no fresh thinking/answer text to surface.
            if (hasLiveCardForActive && !hasThinking && !hasLiveText) return null;
            return (
              <AssistantRow showAvatar={showHeader} agentName="Maya">
                {showHeader && (
                  <div className="flex items-baseline gap-2 mb-1.5">
                    <span className="text-[13px] font-semibold text-foreground">Maya</span>
                    <span className="text-[11px] text-muted-foreground">· Product Manager</span>
                  </div>
                )}
                {hasThinking && (
                  <div className={hasLiveText ? "mb-2" : ""}>
                    <ThinkingBlock text={liveThinking || ""} live />
                  </div>
                )}
                {hasLiveText ? (
                  // Maya's answer streaming token-by-token. Same prose styling
                  // as a committed Bubble so there's no visual jump when the
                  // final `message` lands and clears liveText.
                  <div className="prose prose-sm prose-warm max-w-none text-[14.5px] leading-[1.65] [&_p]:my-1.5 [&_p:first-child]:mt-0 [&_p:last-child]:mb-0 [&_ul]:my-1.5 [&_ol]:my-1.5 [&_strong]:font-semibold [&_em]:italic">
                    <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponentsWithMermaid}>
                      {liveText || ""}
                    </ReactMarkdown>
                  </div>
                ) : (
                  !hasThinking && (
                    <div className="flex items-center gap-2 text-xs text-muted-foreground">
                      <Loader2 size={11} className="animate-spin shrink-0" />
                      <span className="italic">
                        {activeAgent ? `${TOOL_PRETTY[activeAgent] ?? activeAgent}…` : "thinking…"}
                      </span>
                    </div>
                  )
                )}
              </AssistantRow>
            );
          })()}
          {error && (
            <div className="text-xs text-rose-700 bg-rose-50 rounded-xl px-4 py-3 border border-rose-100">
              {error}
            </div>
          )}
        </div>
      </div>

      <div
        className={`px-4 pb-4 pt-3 border-t border-border bg-card transition-colors ${
          dragOver ? "bg-primary/5" : ""
        }`}
        onDragOver={(e) => {
          if (!onUploadFile) return;
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => {
          if (!onUploadFile) return;
          e.preventDefault();
          setDragOver(false);
          handleFiles(e.dataTransfer.files);
        }}
      >
       <div className={`mx-auto w-full transition-[max-width] duration-300 ${workspaceOpen ? "max-w-[720px]" : "max-w-[920px]"}`}>
        {/* Attached assets — chips with status; click × to remove */}
        {visibleAssets.length > 0 && (
          <div className="mb-2 flex flex-wrap gap-1.5">
            {visibleAssets.map((a) => (
              <AssetChip key={a.id} asset={a} onRemove={onRemoveAsset} />
            ))}
          </div>
        )}
        {assetError && (
          <div className="mb-2 flex items-start gap-2 text-[11px] text-rose-700 bg-rose-50 border border-rose-100 rounded-md px-2 py-1.5">
            <span className="flex-1">{assetError}</span>
            {onClearAssetError && (
              <button
                type="button"
                onClick={onClearAssetError}
                aria-label="Dismiss error"
                className="shrink-0 px-1.5 -mr-1 rounded text-rose-600/80 hover:text-rose-900 hover:bg-rose-100 transition-colors"
              >
                ×
              </button>
            )}
          </div>
        )}
        {quotedBlocks.length > 0 && (
          <div className="mb-2 space-y-1.5">
            {quotedBlocks.map((q, i) => (
              <div
                key={i}
                className="px-3 py-2 rounded-xl bg-muted/40 border-l-2 border-primary flex items-start gap-2"
              >
                <Quote size={10} className="text-primary mt-1 shrink-0" />
                <p className="flex-1 text-[12px] text-muted-foreground italic line-clamp-2">{q}</p>
                <button
                  onClick={() =>
                    setQuotedBlocks((prev) => prev.filter((_, idx) => idx !== i))
                  }
                  title="Remove this quote"
                  className="text-[10px] text-muted-foreground hover:text-foreground"
                >
                  ×
                </button>
              </div>
            ))}
            {quotedBlocks.length > 1 && (
              <button
                onClick={() => setQuotedBlocks([])}
                className="text-[10px] text-muted-foreground/70 hover:text-foreground italic"
              >
                clear all
              </button>
            )}
          </div>
        )}
        {queuedMessage && (
          <div className="mb-2 flex items-center gap-2 rounded-xl border border-amber-200 bg-amber-50 px-3 py-1.5">
            <Loader2 size={11} className="text-amber-700 animate-spin shrink-0" />
            <span className="text-[11px] text-amber-800 shrink-0">Queued ·</span>
            <p className="flex-1 text-[12px] text-amber-900/90 italic line-clamp-1">{queuedMessage}</p>
            <button
              onClick={() => onClearQueuedMessage?.()}
              title="Cancel queued message"
              className="text-[12px] text-amber-700 hover:text-amber-900"
            >
              ×
            </button>
          </div>
        )}
        {/* ask_founder quick-replies. Maya paused for the founder's judgment;
            the question is already in the chat as a normal message. These
            chips are one-tap shortcuts — tapping one sends it as the answer,
            which the backend detects and resumes the suspended run with.
            The founder can always type a freeform answer instead. */}
        {pendingAsk && pendingAsk.options.length > 0 && (
          <div className="mb-2 flex flex-wrap gap-1.5">
            {pendingAsk.options.map((opt, i) => (
              <button
                key={i}
                onClick={() => onSend(opt)}
                className="px-3 py-1.5 rounded-full border border-primary/30 bg-primary/5 text-[12px] font-medium text-primary hover:bg-primary/10 transition-colors"
              >
                {opt}
              </button>
            ))}
          </div>
        )}
        <div className="flex items-end gap-2 bg-muted/40 rounded-2xl border border-border px-2 py-2">
          {onUploadFile && (
            <>
              <input
                ref={fileRef}
                type="file"
                multiple
                hidden
                onChange={(e) => {
                  handleFiles(e.target.files);
                  // Reset value so the same file can be re-selected later
                  if (e.target) (e.target as HTMLInputElement).value = "";
                }}
              />
              <button
                onClick={() => fileRef.current?.click()}
                title="Attach files (Maya will read these as context)"
                className="w-8 h-8 rounded-xl text-muted-foreground hover:text-foreground hover:bg-muted transition-colors flex items-center justify-center flex-shrink-0"
              >
                <Paperclip size={14} />
              </button>
            </>
          )}
          <textarea
            ref={textRef}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                // While Maya is streaming, Enter QUEUES the draft for the
                // next turn — it doesn't try to send (the backend would
                // reject anyway, and the founder loses their typing).
                // Once streaming ends, the queued message auto-fires.
                if (isStreaming) {
                  const text = draft.trim();
                  if (!text) return;
                  onQueueMessage?.(text);
                  setDraft("");
                } else {
                  send();
                }
              }
            }}
            placeholder={
              isStreaming
                ? "Maya is working — type to queue your next message…"
                : awaitingInput
                ? "Reply to Maya, paste a PRD snippet, or drop a file…"
                : "Message Maya…"
            }
            rows={1}
            className="flex-1 bg-transparent resize-none outline-none text-[14.5px] text-foreground placeholder:text-muted-foreground py-1.5 leading-[1.6]"
          />
          {isStreaming ? (
            // STOP button — replaces Send while Maya is processing.
            // Always clickable (the founder needs an override path even
            // when no draft is in the textarea).
            <button
              onClick={() => onCancelTurn?.()}
              title="Stop Maya"
              className="w-8 h-8 rounded-xl bg-rose-600 text-white flex items-center justify-center flex-shrink-0 hover:bg-rose-700 transition-colors"
            >
              <Square size={11} fill="currentColor" />
            </button>
          ) : (
            <button
              onClick={send}
              disabled={!draft.trim()}
              className="w-8 h-8 rounded-xl bg-primary text-primary-foreground flex items-center justify-center flex-shrink-0 disabled:opacity-40 disabled:cursor-not-allowed hover:bg-primary/90 transition-colors"
            >
              <Send size={13} />
            </button>
          )}
        </div>
       </div>
      </div>
    </div>
  );
}


/** Compact asset chip. Shows status (pending/processing/ready/error)
 *  with a contextual icon. × removes the asset. */
const AssetChip: React.FC<{
  asset: ProjectAsset;
  onRemove?: (id: string) => void;
}> = ({ asset, onRemove }) => {
  const isReady = asset.status === "ready";
  const isError = asset.status === "error";
  const isRunning = asset.status === "pending" || asset.status === "processing";

  const Icon = isError ? FileWarning : isReady ? FileCheck2 : FileText;
  const tone = isError
    ? "bg-rose-50 border-rose-200 text-rose-700"
    : isReady
    ? "bg-emerald-50 border-emerald-200 text-emerald-800"
    : "bg-muted/60 border-border text-muted-foreground";

  return (
    <span
      title={
        asset.error_text
          ? `${asset.display_name} — ${asset.error_text}`
          : isReady
          ? `${asset.display_name} · ${asset.digest_tokens ?? 0} tokens read`
          : `${asset.display_name} · ${asset.status}`
      }
      className={`inline-flex items-center gap-1.5 max-w-[240px] px-2 py-1 rounded-md border text-[10.5px] font-medium ${tone}`}
    >
      {isRunning ? (
        <Loader2 size={10} className="animate-spin shrink-0" />
      ) : (
        <Icon size={10} className="shrink-0" />
      )}
      <span className="truncate">{asset.display_name}</span>
      {onRemove && (
        <button
          onClick={() => onRemove(asset.id)}
          className="opacity-60 hover:opacity-100 transition-opacity"
          title="Remove"
        >
          <X size={10} />
        </button>
      )}
    </span>
  );
};
