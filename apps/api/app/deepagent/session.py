"""DeepMayaSession — the SSE bridge to the new Deep Agents coordinator.

This is the Phase-5 keystone: it makes `build_maya` (the deepagents harness)
reachable over HTTP/SSE with the SAME external surface the frontend already
speaks to:

    DeepMayaSession(project_id).start(send_greeting)
    await .send(content)            # new founder message OR an ask_founder answer
    event = await .next_event()     # SSE events for the API route
    .abort()                        # founder hit Stop

How it differs from the legacy `app/services/maya.py`:

- It drives the deepagents graph (`create_deep_agent`) instead of the old
  12-stage machine. Maya plans with `write_todos`, delegates with `task`, and
  records product work through the domain tools.
- It streams with `stream_mode=["messages", "updates"]` and **no** `subgraphs`,
  so only Maya's own tokens reach the chat — specialist (subagent) tokens never
  leak in. Maya stays the single voice for free.
- `ask_founder` is a real LangGraph `interrupt`. When the graph suspends we emit
  an `ask` event; the founder's next `send()` is detected as the answer and
  resumes the run with `Command(resume=...)` rather than starting a new turn.
- New events feed the new surfaces: `todos` (the live Plan), `artifact_hint`
  with the new kinds (solutions/features/reviews), and `state_update` chips for
  the domain tools.

The active project is bound on the contextvar (`set_active_project`) inside the
turn coroutine so every domain-tool call resolves it implicitly.
"""
from __future__ import annotations

import asyncio
import json
import time
import traceback
from typing import Any, Optional

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.types import Command

from app.deepagent.coordinator import build_maya
from app.deepagent.domain_tools import set_active_project
from app.services import agent_runs_store
from app.services import assets as assets_svc
from app.services import checkpointer as checkpointer_svc
from app.services import messages as msg_store

SENTINEL: Any = object()
_TURN_TIMEOUT_SECONDS = 600  # research + several subagents can run long
_RECURSION_LIMIT = 60

_GREETING = "Hey, I'm Maya. Tell me a bit about the product you're looking to build."

# subagent_type -> founder-facing label (Activity feed / agent cards).
_SUBAGENT_LABELS = {
    "iris": "Iris (Problem Validator)",
    "aiden": "Aiden (Competitor Mapper)",
    "zara": "Zara (User Researcher)",
    "hugo": "Hugo (Risk Researcher)",
    "theo": "Theo (Tech Advisor)",
    "nora": "Nora (PRD Writer)",
    "kai": "Kai (Sprint Planner)",
}

# domain tool -> founder-facing chip label. Every persistence tool Maya owns
# must appear here — a missing entry means the founder watches a black box
# while the dashboard silently changes (or worse, doesn't refresh at all).
_TOOL_LABELS = {
    "create_artifact": "Saved a finding",
    "update_artifact": "Updated a finding",
    "log_decision": "Logged a decision",
    "open_question": "Opened a question for you",
    "resolve_question": "Closed an open question",
    "update_decision": "Updated a decision",
    "create_solution": "Added a solution",
    "update_solution": "Updated a solution",
    "create_feature": "Shaped a feature",
    "update_feature": "Updated a feature",
    "write_prd": "Wrote the PRD",
    "create_sprint": "Published the sprint board",
    "add_task": "Added a task to the sprint",
    "update_task": "Updated a task",
    "remove_task": "Removed a task",
    "update_sprint": "Updated the sprint",
    "archive_node": "Archived an item",
    "supersede_node": "Replaced an item",
    "link": "Linked dependencies",
    "flag_change": "Flagged a change",
    "list_open_reviews": "Checked open reviews",
    "resolve_review": "Resolved a review flag",
}

# Domain tools that surface a chip in chat. Read-back/plumbing tools
# (list_nodes, get_node, gather_context, link, list_open_reviews) run silently —
# they still fire artifact_hint refreshes where relevant.
_CHIP_VISIBLE = {
    "create_artifact", "update_artifact", "log_decision", "open_question",
    "resolve_question", "update_decision", "create_solution", "update_solution",
    "create_feature", "update_feature", "write_prd", "create_sprint",
    "add_task", "update_task", "remove_task", "update_sprint",
    "archive_node", "supersede_node", "flag_change",
}

# tool -> the right-panel surfaces it should refresh when it finishes. This is
# what makes the dashboard fill in LIVE as Maya works — a missing entry means
# the founder must reload to see the result.
_TOOL_HINTS: dict[str, set[str]] = {
    "create_artifact": {"discovery"},
    "update_artifact": {"discovery", "reviews"},
    "create_solution": {"solutions"},
    "update_solution": {"solutions", "reviews"},
    "create_feature": {"features", "prd"},
    "update_feature": {"features", "prd", "reviews"},
    # Guardrail decisions render inside the PRD, so decisions also nudge prd.
    "log_decision": {"decisions", "prd", "reviews"},
    "open_question": {"decisions"},
    "resolve_question": {"decisions"},
    "update_decision": {"decisions", "prd", "reviews"},
    "write_prd": {"prd"},
    "create_sprint": {"sprint"},
    "add_task": {"sprint"},
    "update_task": {"sprint"},
    "remove_task": {"sprint"},
    "update_sprint": {"sprint"},
    # Archive/supersede can retire any node type — refresh broadly.
    "archive_node": {"discovery", "decisions", "solutions", "features", "sprint"},
    "supersede_node": {"discovery", "decisions", "solutions", "features"},
    "flag_change": {"reviews"},
    "resolve_review": {"reviews"},
}


def _hints_for(tool_name: str) -> set[str]:
    """Which right-panel surfaces a finished domain tool should refresh."""
    return _TOOL_HINTS.get(tool_name, set())


# Research-tool activity inside a specialist subgraph -> a founder-readable
# line for the live ticker ("what is Zara actually doing right now?").
def _activity_label(tool_name: str, args: dict) -> Optional[str]:
    q = str(args.get("query") or "")[:90]
    if tool_name == "web_search":
        return f"Searching the web: “{q}”" if q else "Searching the web"
    if tool_name == "reddit_research":
        return f"Reading Reddit threads: “{q}”" if q else "Reading Reddit threads"
    if tool_name == "crawl_website":
        url = str(args.get("url") or "")[:90]
        return f"Reading {url}" if url else "Reading a page"
    return None


def _flatten(content: Any) -> str:
    """Flatten message content to text (Gemini may return a list of parts)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for p in content:
            if isinstance(p, str):
                parts.append(p)
            elif isinstance(p, dict) and isinstance(p.get("text"), str):
                parts.append(p["text"])
        return "".join(parts)
    return ""


class DeepMayaSession:
    def __init__(self, project_id: str):
        self.project_id = project_id
        self._user_inputs: asyncio.Queue[str] = asyncio.Queue()
        self._events: asyncio.Queue = asyncio.Queue()
        self._task: Optional[asyncio.Task] = None
        self._turn_task: Optional[asyncio.Task] = None
        self._started = False
        self._done = False
        self._agent = None
        # True while the graph is suspended on an ask_founder interrupt — the
        # next founder message is the ANSWER, not a new turn.
        self._awaiting_answer = False
        # Signature of the attachment digest set last injected into a turn —
        # files ride along exactly once per change, not on every message.
        self._assets_sig: Optional[str] = None

    def _with_attachments(self, user_msg: str) -> str:
        """Prepend the founder's attached-file digests to a turn, when changed.

        Best-effort: a DB hiccup must never block the founder's message. The
        block is framed as background data (see assets.load_digests_for_maya);
        the checkpointer keeps it in history, so once injected Maya can refer
        back to it for the rest of the session without re-sending.
        """
        try:
            block, sig = assets_svc.attachments_for_turn(self.project_id, self._assets_sig)
        except Exception:
            return user_msg
        if sig is not None:
            self._assets_sig = sig
        if not block:
            return user_msg
        return (
            "<attached_files>\n"
            f"{block}\n"
            "</attached_files>\n\n"
            f"{user_msg}"
        )

    # ─── lifecycle ──────────────────────────────────────────────────────
    def start(self, send_greeting: bool) -> None:
        if self._started:
            return
        self._started = True
        self._task = asyncio.create_task(self._run(send_greeting))

    @property
    def is_done(self) -> bool:
        return self._done

    @property
    def is_processing(self) -> bool:
        return self._turn_task is not None and not self._turn_task.done()

    @property
    def awaiting_answer(self) -> bool:
        return self._awaiting_answer

    # ─── public IO ──────────────────────────────────────────────────────
    async def send(self, content: str) -> None:
        msg_store.save(self.project_id, role="user", content=content)
        await self._user_inputs.put(content)

    async def next_event(self) -> Optional[dict]:
        item = await self._events.get()
        if item is SENTINEL:
            return None
        return item

    def abort(self) -> bool:
        if self._turn_task and not self._turn_task.done():
            self._turn_task.cancel()
            return True
        return False

    # ─── internals ──────────────────────────────────────────────────────
    def _ensure_agent(self):
        if self._agent is None:
            self._agent = build_maya(checkpointer=checkpointer_svc.get_checkpointer())
        return self._agent

    async def _run(self, send_greeting: bool) -> None:
        try:
            if send_greeting and not msg_store.list_recent(self.project_id, limit=1):
                self._save_and_emit_assistant(_GREETING)

            while True:
                try:
                    user_msg = await asyncio.wait_for(
                        self._user_inputs.get(), timeout=1800
                    )
                except asyncio.TimeoutError:
                    break
                self._turn_task = asyncio.create_task(self._handle(user_msg))
                try:
                    await self._turn_task
                except asyncio.CancelledError:
                    self._emit("cancelled", {"reason": "founder_aborted"})
                finally:
                    self._turn_task = None
        except Exception as e:
            self._emit("error", {"message": str(e)[:300]})
            print(f"[DeepMayaSession] error: {e}\n{traceback.format_exc()}")
        finally:
            self._done = True
            self._events.put_nowait(SENTINEL)

    async def _has_pending_interrupt(self, agent, config) -> bool:
        """The DURABLE truth about whether the graph is suspended on ask_founder.

        The in-memory `_awaiting_answer` flag dies with the session (backend
        restart, idle timeout, scale-out) while the graph stays suspended in the
        checkpointer. Without this check, the founder's answer would be fed in
        as a brand-new message against a suspended graph — the "Maya is
        confused / doesn't follow" failure. Best-effort: on any error, fall
        back to treating the message as new input.
        """
        try:
            state = await agent.aget_state(config)
        except Exception:
            return False
        if getattr(state, "interrupts", None):
            return True
        for t in getattr(state, "tasks", ()) or ():
            if getattr(t, "interrupts", None):
                return True
        return False

    async def _handle(self, user_msg: str) -> None:
        """Run one founder turn (or resume an interrupt) through the coordinator."""
        # Bind the project on THIS context so the domain tools resolve it.
        set_active_project(self.project_id)
        agent = self._ensure_agent()

        config = {
            "configurable": {"thread_id": self.project_id},
            "recursion_limit": _RECURSION_LIMIT,
        }

        # Resume-vs-new is decided by the CHECKPOINTER, not session memory:
        # the fast-path flag is just a hint that avoids the state read.
        resume = self._awaiting_answer or await self._has_pending_interrupt(agent, config)
        if resume:
            # The founder is answering a pending ask_founder interrupt.
            graph_input: Any = Command(resume={"answer": user_msg})
            self._awaiting_answer = False
        else:
            graph_input = {"messages": [HumanMessage(content=self._with_attachments(user_msg))]}

        # tool_call_id -> tool name, captured from AIMessages so we can attribute
        # ToolMessage results back to the tool that produced them.
        call_names: dict[str, str] = {}
        call_subagent: dict[str, str] = {}
        # tool_call_id -> persisted agent_runs row id, so we can move the row
        # to its terminal state when the specialist returns.
        call_run_ids: dict[str, str] = {}
        emitted_texts: set[str] = set()
        interrupted = False

        def _emit_text(text: str, *, awaiting_input: bool) -> None:
            clean = (text or "").strip()
            if not clean or clean in emitted_texts:
                return
            emitted_texts.add(clean)
            self._save_and_emit_assistant(clean, awaiting_input=awaiting_input)

        async def _drive():
            nonlocal interrupted
            # subgraphs=True so specialist activity is visible: chunks become
            # (namespace, mode, payload), namespace () = Maya's own graph.
            # Specialist TOKENS are never surfaced (Maya stays the single
            # voice) — only their tool calls, as a live activity ticker.
            async for ns, mode, chunk in agent.astream(
                graph_input, config=config,
                stream_mode=["messages", "updates"], subgraphs=True,
            ):
                if ns:  # inside a specialist subgraph
                    if mode == "updates" and isinstance(chunk, dict):
                        self._on_subgraph_update(chunk)
                    continue
                if mode == "messages":
                    self._on_message_token(chunk)
                    continue
                # mode == "updates": {node_name: state_update} or interrupt
                if not isinstance(chunk, dict):
                    continue
                for node_name, update in chunk.items():
                    if node_name == "__interrupt__":
                        self._on_interrupt(update)
                        interrupted = True
                        continue
                    if not isinstance(update, dict):
                        continue
                    # Live plan (write_todos wrote new state).
                    if "todos" in update and isinstance(update["todos"], list):
                        self._emit("todos", {"items": update["todos"]})
                    msgs = update.get("messages")
                    if not isinstance(msgs, list):
                        continue
                    for m in msgs:
                        self._on_state_message(m, call_names, call_subagent, call_run_ids, _emit_text)

        try:
            await asyncio.wait_for(_drive(), timeout=_TURN_TIMEOUT_SECONDS)
        except asyncio.TimeoutError:
            # The founder must HEAR this, not just see a transient banner — and
            # it must survive a reload, so it's a persisted assistant message.
            self._save_and_emit_assistant(
                "That took longer than I allow myself, so I stopped midway. "
                "Nothing is lost — say \"continue\" and I'll pick it back up, "
                "or give me a narrower ask.",
            )
        except asyncio.CancelledError:
            raise
        except Exception as e:
            print(f"[DeepMayaSession] turn error: {e}\n{traceback.format_exc()}")
            self._emit("error", {"message": str(e)[:300]})
            # Same rule: a failed turn ends with Maya SAYING so, durably. The
            # checkpointer kept everything up to the failure, so "continue"
            # genuinely resumes from where she left off.
            self._save_and_emit_assistant(
                "I hit a snag partway through that — one of my steps failed. "
                "Nothing is lost: say \"continue\" and I'll pick up where I "
                "left off.",
            )
        finally:
            # If we suspended on an interrupt the input stays locked until the
            # founder answers; otherwise the turn is over and input unlocks.
            self._emit("turn_done", {"awaiting_answer": interrupted})

    # ─── stream handlers ────────────────────────────────────────────────
    def _on_subgraph_update(self, chunk: dict) -> None:
        """Surface a specialist's tool calls as live activity lines.

        This is what turns the 1-3 minute research silence into a visible
        ticker ("Searching the web: …", "Reading Reddit threads: …"). Only
        tool CALLS are surfaced — specialist text never reaches the chat.
        """
        for update in chunk.values():
            if not isinstance(update, dict):
                continue
            msgs = update.get("messages")
            if not isinstance(msgs, list):
                continue
            for m in msgs:
                if not isinstance(m, AIMessage):
                    continue
                for tc in getattr(m, "tool_calls", None) or []:
                    label = _activity_label(tc.get("name") or "", tc.get("args") or {})
                    if label:
                        self._emit("agent_activity", {"action": label})

    def _on_message_token(self, chunk: Any) -> None:
        """messages-mode chunk = (message, metadata). Stream Maya's tokens."""
        msg = chunk[0] if isinstance(chunk, tuple) else chunk
        if not isinstance(msg, AIMessage) and msg.__class__.__name__ != "AIMessageChunk":
            return
        text = _flatten(getattr(msg, "content", ""))
        if text:
            self._emit("text_delta", {"delta": text})

    def _on_interrupt(self, update: Any) -> None:
        """Surface an ask_founder interrupt as an `ask` event + lock for answer."""
        payload: dict = {}
        items = update if isinstance(update, (list, tuple)) else [update]
        for it in items:
            value = getattr(it, "value", None)
            if isinstance(value, dict):
                payload = value
                break
            if isinstance(it, dict) and "question" in it:
                payload = it
                break
        self._awaiting_answer = True
        question = payload.get("question") or "Maya needs your input to continue."
        options = payload.get("options") or []
        # Persist the question as an assistant message so it survives reload.
        self._save_and_emit_assistant(question, awaiting_input=True)
        self._emit("ask", {"question": question, "options": options})

    def _on_state_message(
        self,
        m: Any,
        call_names: dict[str, str],
        call_subagent: dict[str, str],
        call_run_ids: dict[str, str],
        emit_text,
    ) -> None:
        if isinstance(m, AIMessage):
            tool_calls = getattr(m, "tool_calls", None) or []
            text = _flatten(m.content)
            for tc in tool_calls:
                name = tc.get("name") or ""
                tcid = tc.get("id") or ""
                args = tc.get("args") or {}
                call_names[tcid] = name
                if name == "task":
                    sub = args.get("subagent_type") or ""
                    call_subagent[tcid] = sub
                    self._emit("agent_start", {
                        "tool": "task",
                        "subagent": sub,
                        "label": _SUBAGENT_LABELS.get(sub, sub or "Specialist"),
                        "args": args,
                        "kind": "research",
                    })
                    # Persist the dispatch so the card survives a reload.
                    run_id = agent_runs_store.start_run(
                        self.project_id, sub, args.get("description") or ""
                    )
                    if run_id:
                        call_run_ids[tcid] = run_id
                elif name == "write_todos":
                    pass  # handled via the `todos` state update
                elif name in _TOOL_LABELS:
                    if name in _CHIP_VISIBLE:
                        self._emit("state_update", {
                            "tool": name,
                            "label": _TOOL_LABELS.get(name, name),
                            "phase": "start",
                        })
            if text:
                # Text alongside tool calls is a preamble (input stays locked);
                # text with no tool calls is Maya's final answer for the turn.
                emit_text(text, awaiting_input=not tool_calls)
            return

        if isinstance(m, ToolMessage):
            tcid = getattr(m, "tool_call_id", "") or ""
            name = call_names.get(tcid, getattr(m, "name", "") or "")
            result_text = _flatten(getattr(m, "content", ""))
            parsed: Any = None
            if result_text:
                try:
                    parsed = json.loads(result_text)
                except Exception:
                    parsed = None
            if name == "task":
                sub = call_subagent.get(tcid, "")
                self._emit("agent_result", {
                    "tool": "task",
                    "subagent": sub,
                    "label": _SUBAGENT_LABELS.get(sub, sub or "Specialist"),
                    "kind": "research",
                    "result": parsed if parsed is not None else result_text,
                })
                # Move the persisted run to its terminal state. Map the
                # SpecialistResult.status onto the agent_runs enum.
                run_status = "complete"
                if isinstance(parsed, dict):
                    s = parsed.get("status")
                    if s == "needs_input":
                        run_status = "clarification_needed"
                    elif s == "error":
                        run_status = "error"
                payload = parsed if isinstance(parsed, dict) else {"text": result_text}
                agent_runs_store.finish_run(call_run_ids.get(tcid), run_status, payload)
            elif name in _TOOL_LABELS:
                if name in _CHIP_VISIBLE:
                    summary = None
                    if isinstance(result_text, str):
                        summary = result_text[:200]
                    self._emit("state_update", {
                        "tool": name,
                        "label": _TOOL_LABELS.get(name, name),
                        "phase": "end",
                        "summary": summary,
                    })
                for hint in _hints_for(name):
                    self._emit("artifact_hint", {"kind": hint})
            return

    def _save_and_emit_assistant(self, content: str, *, awaiting_input: bool = True) -> None:
        row = msg_store.save(
            self.project_id, role="assistant", content=content, agent="maya",
        )
        self._emit("message", {
            "id": row.get("id"),
            "agent": "maya",
            "content": content,
            "awaiting_input": awaiting_input,
        })

    def _emit(self, event_type: str, data: dict) -> None:
        self._events.put_nowait({"type": event_type, **data})
