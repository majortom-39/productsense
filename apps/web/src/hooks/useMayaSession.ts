/**
 * useMayaSession — drives the chat with Maya.
 *
 * Calls /maya/start, opens the SSE stream, and exposes message history,
 * streaming flags, and a sendMessage() helper.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { supabase } from "@/lib/supabase";

const API_URL = (import.meta.env.VITE_API_URL as string) ?? "http://localhost:8000";

export interface AgentTurn {
  /** A single round in a Maya<->sub-agent exchange. */
  args: Record<string, unknown>;
  status: "running" | "complete" | "clarification_needed" | "error";
  result?: Record<string, unknown> | string;
  startedAt: string;
  completedAt?: string;
  /** If the sub-agent asked Maya a clarifying question on this turn. */
  clarifyingQuestion?: string;
}

export interface AgentCallEntry {
  /** kind discriminator */
  kind: "agent_call";
  id: string;
  /** Canonical key = the BARE specialist name ("zara"), live and hydrated. */
  tool: string;
  /** The chronological sequence of rounds. First turn = initial brief. */
  turns: AgentTurn[];
  // Convenience surface for the latest turn — keeps the existing card code happy.
  args: Record<string, unknown>;
  status: "running" | "complete" | "clarification_needed" | "error";
  result?: Record<string, unknown> | string;
  startedAt: string;
  completedAt?: string;
  /** Live ticker while running — what the specialist is doing right now
   *  ("Searching the web: …"). Transient; not persisted. */
  activity?: string;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  agent?: string;
  createdAt: string;
  quoted?: string;
  toolCall?: { name: string; summary?: string };
  /** Maya's live-streamed reasoning, captured during this turn. Empty for users. */
  thinking?: string;
}

/** A state-update chip — slim inline marker for non-dispatch tools
 *  (stage confirmations, decision logging, artifact creation, etc.).
 *  Replaces the old behaviour of rendering these as fake sub-agent cards.
 *
 *  Verify is also classified as state_update — the grounded-search result
 *  is valuable but doesn't deserve a full sub-agent card. For verify,
 *  `result` carries the full grounded payload so the chip can expand to
 *  show finding + sources inline. */
export interface StateUpdateEntry {
  kind: "state_update";
  id: string;
  tool: string;            // e.g. "confirm_problem_statement"
  label: string;           // user-facing label
  summary?: string;        // optional 1-line outcome
  result?: Record<string, unknown> | null;  // full payload (used by expandable chips like verify)
  createdAt: string;
  status: "ok" | "stage_refused" | "error" | "running";
}

/** Union surfaced to the chat panel — interleaves messages with agent calls
 *  and slim state-update chips. */
export type ChatItem =
  | (ChatMessage & { kind: "message" })
  | AgentCallEntry
  | StateUpdateEntry;

export type ArtifactHint =
  | "prd"
  | "sprint"
  | "decisions"
  | "discovery"
  | "solutions"
  | "features"
  | "reviews";

/** A single live-plan item mirrored from Maya's write_todos (clean_arch §12a). */
export interface Todo {
  content: string;
  status: "pending" | "in_progress" | "completed";
}

/** A pending ask_founder interrupt — Maya paused for the founder's judgment.
 *  The question text also arrives as a normal assistant `message`; this just
 *  carries the optional quick-reply `options`. Answering = sendMessage(answer);
 *  the backend detects the answer and resumes the suspended run. */
export interface PendingAsk {
  question: string;
  options: string[];
}

/** Inline delta carried on an artifact_hint event when the backend can
 *  short-circuit a refetch. The frontend merges this directly into its
 *  local state — no HTTP round-trip, which kills the PostgREST race
 *  that made pin + decision-log feel unreliable.
 *
 *  Covers two artifact kinds today:
 *    - research  (Maya's pin/create/update/delete tools)
 *    - decisions (Maya's log_decision + commit_guardrails tools)
 *  PRD + sprint still go via the refetch path (no race in practice).
 *
 *  Three ops:
 *    upsert       — single row added or modified (set or replace by id)
 *    upsert_batch — N rows added (commit_guardrails fanout); merge each
 *    delete       — single row removed by id
 */
export type ArtifactDeltaKind = "discovery" | "decisions";
export type ArtifactDelta =
  | { kind: ArtifactDeltaKind; op: "upsert"; id: string; item: Record<string, unknown>; nonce: number }
  | { kind: ArtifactDeltaKind; op: "upsert_batch"; items: Record<string, unknown>[]; nonce: number }
  | { kind: ArtifactDeltaKind; op: "delete"; id: string; nonce: number };

interface MayaState {
  messages: ChatMessage[];
  /** Single chronological stream of messages + agent calls, ready to render. */
  items: ChatItem[];
  sessionStarted: boolean;
  isStreaming: boolean;
  awaitingInput: boolean;
  error: string | null;
  activeAgent: string | null;
  artifactHint: { kind: ArtifactHint; nonce: number } | null;
  /** Append-only queue of inline deltas. Bursty events (e.g. Maya pins
   *  two artifacts in the same response) APPEND here rather than
   *  overwriting — the previous single-field design lost intermediate
   *  events when nonces fired in the same React render. Index drains. */
  artifactDeltas: ArtifactDelta[];
  /** Maya's reasoning being streamed RIGHT NOW (cleared when the message lands). */
  liveThinking: string;
  /** Maya's ANSWER tokens being streamed right now (text_delta), cleared when
   *  the final `message` for the turn lands. Renders as the in-progress bubble. */
  liveText: string;
  /** Maya's live plan, mirrored from write_todos. Drives the Plan tab. */
  todos: Todo[];
  /** Set when Maya raised an ask_founder interrupt and is waiting on the
   *  founder. Cleared when they answer (sendMessage) or the turn settles. */
  pendingAsk: PendingAsk | null;
  /** Founder typed a message while Maya was still streaming a previous turn.
   *  Stays here until isStreaming flips back to false, at which point the
   *  auto-flush effect fires it as a normal sendMessage. Mirrors the Claude
   *  pattern. */
  queuedMessage: string | null;
}

const INITIAL: MayaState = {
  messages: [],
  items: [],
  sessionStarted: false,
  isStreaming: false,
  awaitingInput: false,
  error: null,
  activeAgent: null,
  artifactHint: null,
  artifactDeltas: [],
  liveThinking: "",
  liveText: "",
  todos: [],
  pendingAsk: null,
  queuedMessage: null,
};

let _msgCounter = 0;
const uid = () => `m-${++_msgCounter}-${Date.now()}`;

/** Rebuild the live `items` stream from hydrated messages + agent_runs.
 *
 *  We interleave them by ISO timestamp (messages.created_at,
 *  agent_runs.started_at) so the chat reads in the same chronological
 *  order it did live. Each `agent_runs` row becomes an `AgentCallEntry`
 *  with one synthetic "completed" turn carrying the stored output_payload,
 *  so the existing rendering pipeline doesn't need to know it came from
 *  hydration vs. live SSE.
 *
 *  Failure cases:
 *   - run with no agent_name → skip (corrupt row)
 *   - run with status='running' on hydrate → treat as 'complete' anyway
 *     since the live SSE for that run is gone forever; better to show
 *     something than a stuck spinner. */
// Friendly labels for the persistent chips. Mirror of _TOOL_LABELS on the
// backend so the chat-stream wording matches live + reload.
const STATE_TOOL_LABELS: Record<string, string> = {
  log_decision: "Logging decision",
  pin_artifact: "Pinning to Discovery",
  create_artifact: "Synthesizing card",
  update_artifact: "Updating card",
  commit_guardrails: "Locking in guardrails",
};

function mergeHistoryItems(
  messages: ChatMessage[],
  runs: Array<Record<string, any>>,
  decisions: Array<Record<string, any>> = [],
  artifactEvents: Array<Record<string, any>> = [],
): ChatItem[] {
  type Stamped = { at: number; item: ChatItem };
  const out: Stamped[] = [];

  for (const m of messages) {
    out.push({
      at: new Date(m.createdAt || 0).getTime(),
      item: { ...m, kind: "message" as const },
    });
  }

  for (const r of runs) {
    if (!r || typeof r !== "object") continue;
    const agentName = r.agent_name;
    if (typeof agentName !== "string" || !agentName) continue;
    const startedAt = r.started_at || r.created_at || new Date().toISOString();
    const completedAt = r.ended_at || startedAt;

    // Reconstruct a single turn from the persisted output_payload. We
    // map the DB status to the runtime status union the renderer knows.
    const dbStatus: string = r.status ?? "complete";
    const subStatus: AgentCallEntry["status"] =
      dbStatus === "clarification_needed"
        ? "clarification_needed"
        : dbStatus === "error"
        ? "error"
        : "complete";

    const result = r.output_payload ?? null;
    // Maya's brief to the specialist IS persisted (agent_runs.query) — carry
    // it through as args.description, the same field live agent_start events
    // use, so a reloaded card shows the exchange identically to a live one.
    const args: Record<string, unknown> =
      typeof r.query === "string" && r.query ? { description: r.query } : {};

    const turn: AgentTurn = {
      args,
      status: subStatus,
      result: result as AgentTurn["result"],
      startedAt,
      completedAt,
    };

    // One canonical key for both live and hydrated cards: the BARE specialist
    // name ("zara"). Legacy rows from the old architecture wrote
    // "invoke_zara" — strip the prefix so they land on the same vocabulary.
    const tool = agentName.replace(/^invoke_/, "");

    const entry: AgentCallEntry = {
      kind: "agent_call",
      id: r.id || uid(),
      tool,
      args,
      status: subStatus,
      result: result as AgentCallEntry["result"],
      startedAt,
      completedAt,
      turns: [turn],
    };
    out.push({
      at: new Date(startedAt).getTime(),
      item: entry,
    });
  }

  // ── Synthesize StateUpdateEntry items for persistent chips ──
  // Decisions: one chip per row at created_at, label = "Logging decision".
  for (const d of decisions) {
    const at = new Date(d.created_at || d.createdAt || 0).getTime();
    if (!at) continue;
    out.push({
      at,
      item: {
        kind: "state_update" as const,
        id: `dec-${d.id ?? uid()}`,
        tool: "log_decision",
        label: STATE_TOOL_LABELS.log_decision,
        summary: (d.title || "").toString().slice(0, 140),
        result: { status: "ok", display_id: d.display_id, title: d.title },
        createdAt: d.created_at ?? new Date(at).toISOString(),
        status: "ok",
      },
    });
  }

  // Artifact events: one chip per pin/create/update event at created_at.
  // We use created_at (the row's birth) since "first seen on the dashboard"
  // is what the chip semantically marks. Updates don't get their own chip
  // on reload — only the live SSE shows them.
  for (const a of artifactEvents) {
    const at = new Date(a.created_at || 0).getTime();
    if (!at) continue;
    const createdBy = a.created_by;
    const tool = createdBy === "maya_pinned" ? "pin_artifact" : "create_artifact";
    out.push({
      at,
      item: {
        kind: "state_update" as const,
        id: `art-${a.id ?? uid()}`,
        tool,
        label: STATE_TOOL_LABELS[tool] || "Artifact",
        summary: (a.title || a.summary || "").toString().slice(0, 140),
        result: {
          status: "ok",
          artifact_id: a.id,
          title: a.title,
          render_kind: a.render_kind,
        },
        createdAt: a.created_at,
        status: "ok",
      },
    });
  }

  // Stable chronological sort
  out.sort((a, b) => a.at - b.at);
  return out.map((s) => s.item);
}

async function authedFetch(path: string, init?: RequestInit): Promise<Response> {
  const { data } = await supabase.auth.getSession();
  const token = data.session?.access_token ?? "";
  return fetch(`${API_URL}${path}`, {
    ...init,
    headers: {
      ...(init?.headers ?? {}),
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
  });
}

export function useMayaSession(projectId: string | null) {
  const [state, setState] = useState<MayaState>(INITIAL);
  const streamRef = useRef<EventSource | null>(null);
  const startedFor = useRef<string | null>(null);
  // Reconnect state. The browser's EventSource has built-in auto-reconnect
  // for transient TCP issues, BUT it won't help us across a backend restart
  // (the in-memory session is wiped + the auth token may have expired).
  // We track our own attempt counter + reconnect timer so we can:
  //   - Refresh the JWT before reconnecting (old token may be stale)
  //   - Re-call /maya/start so the backend re-creates the session
  //   - Bounded backoff so a real outage doesn't hammer
  const reconnectAttempts = useRef<number>(0);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const MAX_RECONNECT_ATTEMPTS = 5;
  // Delta queue lives in a ref so that bursty SSE events (e.g. Maya pins
  // 2 artifacts in the same response) can all be retained without
  // depending on React batching for ordering. The state `artifactDeltas`
  // mirrors it for renders that want to observe queue depth; consumer
  // drains via consumeArtifactDeltas() which reads + clears the ref.
  const deltaQueueRef = useRef<ArtifactDelta[]>([]);

  const reset = useCallback(() => {
    streamRef.current?.close();
    streamRef.current = null;
    startedFor.current = null;
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
    reconnectAttempts.current = 0;
    deltaQueueRef.current = [];
    setState(INITIAL);
  }, []);

  // openStream — extracted so we can call it both from start() and the
  // reconnect path. Pure: opens an EventSource, wires onmessage/onerror.
  // The onerror handler triggers reconnectStream() which handles backoff.
  const openStream = useCallback(async (id: string): Promise<void> => {
    // Close any existing stream first (defensive — prevents leaks).
    if (streamRef.current) {
      streamRef.current.close();
      streamRef.current = null;
    }
    const { data } = await supabase.auth.getSession();
    const token = data.session?.access_token ?? "";
    if (!token) {
      console.warn("[useMayaSession] no token for SSE stream");
      return;
    }
    const url = `${API_URL}/maya/stream?project_id=${encodeURIComponent(id)}&token=${encodeURIComponent(token)}`;
    const source = new EventSource(url);
    source.onmessage = (ev) => {
      try {
        const evt = JSON.parse(ev.data);
        handleEvent(evt);
        // Successful event => reset reconnect counter
        if (reconnectAttempts.current > 0) {
          reconnectAttempts.current = 0;
        }
      } catch {
        // ignore parse errors
      }
    };
    source.onerror = () => {
      // EventSource closes itself on error in most browsers. Schedule a
      // reconnect via reconnectStream — it'll backoff + bounded-retry.
      // Don't flip isStreaming to false here; we want the UI to keep
      // showing "thinking…" until reconnect either succeeds or gives up.
      reconnectStream(id);
    };
    streamRef.current = source;
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // reconnectStream — backoff + bounded-retry reconnect logic. Triggered
  // by EventSource.onerror. Calls /maya/start (backend auto-creates the
  // session if missing — see _get_or_create_session in routes/maya.py),
  // then re-opens the stream. After MAX_RECONNECT_ATTEMPTS the UI gets
  // an error event so the founder knows.
  const reconnectStream = useCallback((id: string) => {
    // Don't pile up timers if we're already reconnecting
    if (reconnectTimerRef.current) return;
    reconnectAttempts.current += 1;
    if (reconnectAttempts.current > MAX_RECONNECT_ATTEMPTS) {
      console.warn(`[useMayaSession] giving up after ${MAX_RECONNECT_ATTEMPTS} reconnect attempts`);
      setState((p) => ({
        ...p,
        isStreaming: false,
        awaitingInput: true,
        error: "Lost connection to the server. Please refresh the page.",
      }));
      return;
    }
    // Backoff: 1s, 2s, 4s, 8s, 10s (max)
    const delay = Math.min(1000 * Math.pow(2, reconnectAttempts.current - 1), 10_000);
    console.log(`[useMayaSession] reconnect attempt ${reconnectAttempts.current}/${MAX_RECONNECT_ATTEMPTS} in ${delay}ms`);
    reconnectTimerRef.current = setTimeout(async () => {
      reconnectTimerRef.current = null;
      try {
        // Re-call /maya/start. Backend's _get_or_create_session restores
        // the session from checkpoint if it was lost (e.g. backend restart).
        // Idempotent — if session exists, returns "already_running".
        await authedFetch("/maya/start", {
          method: "POST",
          body: JSON.stringify({ project_id: id }),
        });
        // Re-open the EventSource. If THIS one fails too, openStream's
        // onerror handler will call reconnectStream again with the
        // incremented counter — natural backoff continuation.
        await openStream(id);
      } catch (err) {
        console.error("[useMayaSession] reconnect failed:", err);
        // Try again on next tick — reconnectStream will increment the
        // counter and apply the next backoff.
        reconnectStream(id);
      }
    }, delay);
  }, [openStream]);

  const start = useCallback(async (id: string) => {
    if (startedFor.current === id) return;
    startedFor.current = id;
    setState({ ...INITIAL, isStreaming: true });

    // Boot session
    const res = await authedFetch("/maya/start", {
      method: "POST",
      body: JSON.stringify({ project_id: id }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      setState((p) => ({ ...p, error: err.detail, isStreaming: false }));
      return;
    }
    // Backend is the source of truth for "is there an in-flight turn".
    // Previously we inferred it from chat history (lastWasUser), but that
    // lies after an orphaned crash + backend restart — the last user
    // message stays in the DB even though no Maya turn is actually
    // running. The backend's is_processing flag is authoritative.
    const startData = await res.json().catch(() => ({} as Record<string, unknown>));
    const backendProcessing = !!(startData as { is_processing?: boolean }).is_processing;

    // Hydrate prior messages + sub-agent dispatches. The endpoint returns
    // BOTH lists; we interleave them by timestamp to rebuild the
    // chronological item stream the chat surface renders. Without this
    // step, every Iris/Aiden/Hugo/Zara/Theo card disappears on reload —
    // only Maya's prose used to come back.
    const histRes = await authedFetch(`/maya/messages?project_id=${id}`);
    if (histRes.ok) {
      const {
        messages,
        agent_runs,
        decisions,
        artifact_events,
      } = await histRes.json();
      const hydrated: ChatMessage[] = (messages ?? []).map((m: any) => ({
        id: m.id,
        role: m.role === "user" ? "user" : "assistant",
        content: m.content,
        agent: m.agent,
        createdAt: m.created_at,
      }));
      const items = mergeHistoryItems(
        hydrated,
        agent_runs ?? [],
        decisions ?? [],
        artifact_events ?? [],
      );
      setState((p) => ({
        ...p,
        messages: hydrated,
        items,
        sessionStarted: true,
        isStreaming: backendProcessing,
        awaitingInput: !backendProcessing,
      }));
    } else {
      setState((p) => ({
        ...p,
        sessionStarted: true,
        isStreaming: backendProcessing,
        awaitingInput: !backendProcessing,
      }));
    }

    // Open SSE via the shared helper (also reused on reconnect).
    reconnectAttempts.current = 0;
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
    await openStream(id);
  }, [openStream]);

  const handleEvent = useCallback((evt: any) => {
    setState((prev) => {
      switch (evt.type) {
        case "message": {
          // PREAMBLE handling: when the server sends `awaiting_input: false`
          // it means this is Maya's "let me check Theo" text BEFORE a
          // dispatch — the turn isn't done. Keep isStreaming/disabled-input
          // true so the founder can't fire another message mid-dispatch.
          const isFinal = (evt.awaiting_input ?? true) === true;
          // Dedup: if the server included a DB id and we've already hydrated
          // that same id from /maya/messages, skip the append. Belt-and-braces
          // for the greeting race where both paths deliver the same row.
          const incomingId = typeof evt.id === "string" ? (evt.id as string) : null;
          if (incomingId && prev.messages.some((m) => m.id === incomingId)) {
            // Already in state. Still flip the streaming flags so the UI exits
            // the "thinking…" state cleanly (only on final).
            return {
              ...prev,
              isStreaming: isFinal ? false : prev.isStreaming,
              awaitingInput: isFinal,
              activeAgent: isFinal ? null : prev.activeAgent,
              liveThinking: isFinal ? "" : prev.liveThinking,
              liveText: "",
              pendingAsk: isFinal ? null : prev.pendingAsk,
            };
          }
          const msg: ChatMessage = {
            id: incomingId ?? uid(),
            role: "assistant",
            content: evt.content ?? "",
            agent: evt.agent ?? "maya",
            createdAt: new Date().toISOString(),
            // Attach the accumulated reasoning from this turn (may be empty).
            // For preambles, thinking text isn't really meaningful yet; we
            // only attach on final messages.
            thinking: isFinal && prev.liveThinking ? prev.liveThinking : undefined,
          };
          return {
            ...prev,
            messages: [...prev.messages, msg],
            items: [...prev.items, { ...msg, kind: "message" as const }],
            isStreaming: isFinal ? false : true,
            awaitingInput: isFinal,
            activeAgent: isFinal ? null : prev.activeAgent,
            liveThinking: isFinal ? "" : prev.liveThinking,
            // The streamed answer is now committed as a real message; drop the
            // in-progress buffer so the bubble doesn't render twice.
            liveText: "",
          };
        }
        case "thinking": {
          const delta = (evt.delta ?? "") as string;
          if (!delta) return prev;
          return { ...prev, liveThinking: prev.liveThinking + delta };
        }
        case "text_delta": {
          // Maya's answer streaming token-by-token. Accumulate into liveText so
          // the chat can render an in-progress assistant bubble; the final
          // `message` event then commits the full text and clears this buffer.
          const delta = (evt.delta ?? "") as string;
          if (!delta) return prev;
          return { ...prev, liveText: prev.liveText + delta };
        }
        case "todos": {
          // Maya's live plan (write_todos). Mirror it for the Plan tab.
          const items = Array.isArray(evt.items) ? (evt.items as Todo[]) : [];
          return { ...prev, todos: items };
        }
        case "ask": {
          // ask_founder interrupt. The question text already arrived as a
          // persisted `message`; here we capture the optional quick-reply
          // options and surface that Maya is waiting on the founder.
          const question = typeof evt.question === "string" ? evt.question : "";
          const options = Array.isArray(evt.options) ? (evt.options as string[]) : [];
          return {
            ...prev,
            pendingAsk: { question, options },
            isStreaming: false,
            awaitingInput: true,
            activeAgent: null,
            liveText: "",
          };
        }
        case "agent_start": {
          // New coordinator dispatches all specialists via the `task` tool, so
          // we key the card by the specialist (`subagent`) rather than the tool
          // name (which is always "task"). Legacy events without `subagent`
          // fall back to `tool`.
          const toolKey = (evt.subagent as string) || (evt.tool as string) || "unknown";
          // If the most recent agent_call for this specialist is still in a
          // needs_input state (i.e. Maya is re-invoking), append a new turn to
          // that same entry instead of creating a new card.
          const items = [...prev.items];
          for (let i = items.length - 1; i >= 0; i--) {
            const it = items[i];
            if (it.kind === "agent_call" && it.tool === toolKey && it.status === "clarification_needed") {
              const newTurn: AgentTurn = {
                args: evt.args ?? {},
                status: "running",
                startedAt: new Date().toISOString(),
              };
              items[i] = {
                ...it,
                args: evt.args ?? it.args,
                status: "running",
                turns: [...it.turns, newTurn],
              };
              return { ...prev, activeAgent: toolKey, items };
            }
            // Stop the scan when we hit a message — only consider very recent calls
            if (it.kind === "message") break;
          }
          // New invocation, new card
          const firstTurn: AgentTurn = {
            args: evt.args ?? {},
            status: "running",
            startedAt: new Date().toISOString(),
          };
          const entry: AgentCallEntry = {
            kind: "agent_call",
            id: uid(),
            tool: toolKey,
            args: evt.args ?? {},
            status: "running",
            startedAt: firstTurn.startedAt,
            turns: [firstTurn],
          };
          return {
            ...prev,
            activeAgent: toolKey,
            items: [...prev.items, entry],
          };
        }
        case "agent_activity": {
          // Live ticker line for the specialist that's currently working —
          // attach to the most recent RUNNING agent card.
          const action = typeof evt.action === "string" ? (evt.action as string) : "";
          if (!action) return prev;
          const items = [...prev.items];
          for (let i = items.length - 1; i >= 0; i--) {
            const it = items[i];
            if (it.kind === "agent_call" && it.status === "running") {
              items[i] = { ...it, activity: action };
              return { ...prev, items };
            }
          }
          return prev;
        }
        case "state_update": {
          // Slim chip for non-dispatch tools — stage confirmations, decision
          // logging, artifact CRUD, etc. We only commit a visible chip on
          // phase=end so the chip text reflects the actual outcome; phase=
          // start events are dropped (sub-second writes; nothing useful to
          // show in flight).
          if (evt.phase === "start") return prev;
          const result = (evt.result ?? null) as any;
          let status: StateUpdateEntry["status"] = "ok";
          if (result && typeof result === "object") {
            if (result.status === "stage_refused") status = "stage_refused";
            else if (result.status === "error") status = "error";
          }
          const entry: StateUpdateEntry = {
            kind: "state_update",
            id: uid(),
            tool: (evt.tool ?? "unknown") as string,
            label: (evt.label ?? evt.tool ?? "Update") as string,
            summary: typeof evt.summary === "string" ? (evt.summary as string) : undefined,
            result: result && typeof result === "object" ? result : null,
            createdAt: new Date().toISOString(),
            status,
          };
          return { ...prev, items: [...prev.items, entry] };
        }
        case "agent_result": {
          const toolKey = (evt.subagent as string) || (evt.tool as string) || "unknown";
          const items = [...prev.items];
          for (let i = items.length - 1; i >= 0; i--) {
            const it = items[i];
            if (it.kind === "agent_call" && it.tool === toolKey && it.status === "running") {
              const resultObj = (evt.result ?? null) as any;
              // New SpecialistResult contract uses status complete|needs_input;
              // legacy used clarification_needed. Treat both as "needs input".
              const needsInput =
                resultObj && typeof resultObj === "object" &&
                (resultObj.status === "needs_input" || resultObj.status === "clarification_needed");
              const subStatus: AgentCallEntry["status"] =
                needsInput
                  ? "clarification_needed"
                  : resultObj && typeof resultObj === "object" && resultObj.status === "error"
                  ? "error"
                  : "complete";
              const clarifyingQuestion =
                needsInput && Array.isArray(resultObj?.questions) && resultObj.questions.length
                  ? (resultObj.questions as string[]).join(" ")
                  : needsInput && typeof resultObj?.clarifying_question === "string"
                  ? (resultObj.clarifying_question as string)
                  : undefined;
              // Update the latest turn
              const turns = [...it.turns];
              const lastIdx = turns.length - 1;
              if (lastIdx >= 0) {
                turns[lastIdx] = {
                  ...turns[lastIdx],
                  status: subStatus,
                  result: evt.result ?? null,
                  completedAt: new Date().toISOString(),
                  clarifyingQuestion,
                };
              }
              items[i] = {
                ...it,
                status: subStatus,
                result: evt.result ?? null,
                completedAt: new Date().toISOString(),
                activity: undefined,
                turns,
              };
              break;
            }
          }
          return { ...prev, activeAgent: null, items };
        }
        case "artifact_hint": {
          // Backend emits {type: "artifact_hint", kind, ...op-specific fields}
          // after any artifact-mutating tool. For research + decisions the
          // event may carry inline delta data (op + id|items + item?) so
          // the consuming hook merges state directly without a refetch —
          // bypasses the PostgREST read-after-write race that made pins
          // and decisions feel laggy.
          //
          // PRD + sprint fall through to refetch (no inline delta path
          // yet — lower volume, no race observed in practice).
          //
          // Deltas APPEND to the queue. Previous design overwrote a
          // single field, which lost intermediate events when Maya fired
          // two pins in the same response (both nonces in the same React
          // render → only the last survived). Queue keeps every event;
          // Index drains.
          const kind = (evt.kind as ArtifactHint) ?? null;
          if (!kind) return prev;
          const nonce = Date.now() + Math.random();  // strict-ordering id
          const next: Partial<MayaState> = { artifactHint: { kind, nonce } };

          const op = evt.op as ArtifactDelta["op"] | undefined;
          if ((kind === "discovery" || kind === "decisions") && op) {
            let delta: ArtifactDelta | null = null;
            if (op === "upsert" && typeof evt.id === "string" && evt.item) {
              delta = {
                kind,
                op: "upsert",
                id: evt.id as string,
                item: evt.item as Record<string, unknown>,
                nonce,
              };
            } else if (op === "upsert_batch" && Array.isArray(evt.items)) {
              delta = {
                kind,
                op: "upsert_batch",
                items: evt.items as Record<string, unknown>[],
                nonce,
              };
            } else if (op === "delete" && typeof evt.id === "string") {
              delta = { kind, op: "delete", id: evt.id as string, nonce };
            }
            if (delta) {
              // Ref is the source of truth; state mirrors it for re-render.
              // This pattern survives React 18 batching — every reducer
              // call pushes synchronously regardless of when commits run.
              deltaQueueRef.current.push(delta);
              next.artifactDeltas = [...deltaQueueRef.current];
            }
          }
          return { ...prev, ...next };
        }
        // Legacy event names (kept as aliases for any older client code
        // that might still emit them — current backend uses artifact_hint).
        case "research_added":
          return { ...prev, artifactHint: { kind: "discovery", nonce: Date.now() } };
        case "prd_updated":
          return { ...prev, artifactHint: { kind: "prd", nonce: Date.now() } };
        case "sprint_updated":
          return { ...prev, artifactHint: { kind: "sprint", nonce: Date.now() } };
        case "decision_logged":
        case "guardrail_added":
          return { ...prev, artifactHint: { kind: "decisions", nonce: Date.now() } };
        case "cancelled":
          // Founder hit Stop. Settle the UI back to idle so the next
          // message can fire. We DO NOT clear queuedMessage here — if
          // they had a draft queued, the auto-flush effect picks it up
          // as the next turn.
          return {
            ...prev,
            isStreaming: false,
            awaitingInput: true,
            activeAgent: null,
            liveThinking: "",
            liveText: "",
          };
        case "turn_done":
          // Backend signals the turn is complete — fires in every exit
          // path (success, timeout, exception). Needed because Maya
          // sometimes ends a turn with a tool call (e.g. confirm_friction)
          // and no follow-up text, so no `message` event with
          // awaiting_input=true ever arrives to unlock the input.
          // Idempotent — already-settled state stays settled.
          if (!prev.isStreaming && prev.awaitingInput) return prev;
          return {
            ...prev,
            isStreaming: false,
            awaitingInput: true,
            activeAgent: null,
            liveThinking: "",
            liveText: "",
          };
        case "error":
          return { ...prev, error: evt.message ?? "Unknown error", isStreaming: false };
        default:
          return prev;
      }
    });
  }, []);

  const sendMessage = useCallback(
    async (content: string, quoted?: string) => {
      if (!projectId) return;
      // The user can quote a PRD snippet — prepend it as context Maya can see.
      const fullContent = quoted ? `> "${quoted}"\n\n${content}` : content;
      const localMsg: ChatMessage = {
        id: uid(),
        role: "user",
        content,
        createdAt: new Date().toISOString(),
        ...(quoted ? { quoted } : {}),
      } as ChatMessage;
      setState((p) => ({
        ...p,
        messages: [...p.messages, localMsg],
        items: [...p.items, { ...localMsg, kind: "message" as const }],
        isStreaming: true,
        awaitingInput: false,
        // Sending is also how the founder answers an ask_founder interrupt —
        // clear the pending prompt and any half-streamed text.
        pendingAsk: null,
        liveText: "",
      }));
      const res = await authedFetch("/maya/message", {
        method: "POST",
        body: JSON.stringify({ project_id: projectId, content: fullContent }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        setState((p) => ({ ...p, error: err.detail, isStreaming: false }));
      }
    },
    [projectId],
  );

  /** Cancel the in-flight Maya turn. The backend cancels the asyncio.Task
   *  wrapping the current turn; LangGraph + Gemini receive CancelledError
   *  and unwind. Backend then emits a `cancelled` SSE event which settles
   *  the UI back to idle. */
  const cancelTurn = useCallback(async () => {
    if (!projectId) return;
    try {
      await authedFetch("/maya/abort", {
        method: "POST",
        body: JSON.stringify({ project_id: projectId }),
      });
    } catch {
      // Best-effort — even if the request fails the backend will eventually
      // emit the cancelled event when the task winds down, or the user can
      // retry. We don't want to surface this as a chat error.
    }
  }, [projectId]);

  /** Stash a draft the founder typed while Maya was still streaming.
   *  Auto-flushes via the effect below as soon as isStreaming flips false. */
  const queueMessage = useCallback((content: string) => {
    setState((p) => ({ ...p, queuedMessage: content }));
  }, []);

  /** Drop the queued draft without sending. Founder editing-out of the
   *  queue via the chip's × button. */
  const clearQueuedMessage = useCallback(() => {
    setState((p) => ({ ...p, queuedMessage: null }));
  }, []);

  // Auto-flush the queued message when streaming ends. The dependency on
  // queuedMessage avoids running this loop spuriously — it only fires when
  // a queue actually exists AND streaming has just settled.
  useEffect(() => {
    if (state.isStreaming || !state.queuedMessage) return;
    const draft = state.queuedMessage;
    setState((p) => ({ ...p, queuedMessage: null }));
    void sendMessage(draft);
  }, [state.isStreaming, state.queuedMessage, sendMessage]);

  // Auto-start whenever projectId changes
  useEffect(() => {
    if (!projectId) {
      reset();
      return;
    }
    reset();
    start(projectId);
    return () => {
      streamRef.current?.close();
      streamRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);

  /** Take + clear all queued artifact deltas. Index calls this on every
   *  artifactHint nonce change and applies the batch atomically. Backed
   *  by the queue ref so the result is deterministic regardless of
   *  React's batching behaviour. */
  const consumeArtifactDeltas = useCallback((): ArtifactDelta[] => {
    const drained = deltaQueueRef.current;
    if (drained.length === 0) return [];
    deltaQueueRef.current = [];
    // Mirror state so observers see the empty queue.
    setState((prev) =>
      prev.artifactDeltas.length === 0 ? prev : { ...prev, artifactDeltas: [] },
    );
    return drained;
  }, []);

  return {
    ...state,
    sendMessage,
    reset,
    consumeArtifactDeltas,
    cancelTurn,
    queueMessage,
    clearQueuedMessage,
  };
}
