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

# domain tool -> founder-facing chip label.
_TOOL_LABELS = {
    "create_artifact": "Saved a finding",
    "update_artifact": "Updated a finding",
    "log_decision": "Logged a decision",
    "open_question": "Opened a question",
    "create_solution": "Added a solution",
    "create_feature": "Shaped a feature",
    "link": "Linked dependencies",
    "flag_change": "Flagged a change",
    "list_open_reviews": "Checked open reviews",
    "resolve_review": "Resolved a review flag",
}

# Domain tools that surface a chip in chat. The rest run silently (they still
# fire artifact_hint refreshes — the chip is purely the chat marker).
_CHIP_VISIBLE = {
    "create_artifact", "update_artifact", "log_decision", "open_question",
    "create_solution", "create_feature", "flag_change",
}


def _hints_for(tool_name: str) -> set[str]:
    """Which right-panel surfaces a finished domain tool should refresh."""
    if tool_name in ("create_artifact", "update_artifact"):
        hints = {"discovery"}
    elif tool_name == "create_solution":
        hints = {"solutions"}
    elif tool_name == "create_feature":
        hints = {"features"}
    elif tool_name in ("log_decision", "open_question"):
        hints = {"decisions"}
    elif tool_name == "link":
        hints = set()
    elif tool_name in ("flag_change", "resolve_review", "list_open_reviews"):
        hints = {"reviews"}
    else:
        hints = set()
    # Any update that can flip in_mvp / version also nudges the review badges.
    if tool_name in ("update_artifact", "flag_change", "log_decision"):
        hints.add("reviews")
    return hints


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

    async def _handle(self, user_msg: str) -> None:
        """Run one founder turn (or resume an interrupt) through the coordinator."""
        # Bind the project on THIS context so the domain tools resolve it.
        set_active_project(self.project_id)
        agent = self._ensure_agent()

        config = {
            "configurable": {"thread_id": self.project_id},
            "recursion_limit": _RECURSION_LIMIT,
        }

        if self._awaiting_answer:
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
            async for mode, chunk in agent.astream(
                graph_input, config=config, stream_mode=["messages", "updates"]
            ):
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
            self._emit("error", {
                "message": (
                    "Maya took too long and was stopped. Try a more specific ask."
                ),
            })
        except asyncio.CancelledError:
            raise
        except Exception as e:
            self._emit("error", {"message": str(e)[:300]})
            print(f"[DeepMayaSession] turn error: {e}\n{traceback.format_exc()}")
        finally:
            # If we suspended on an interrupt the input stays locked until the
            # founder answers; otherwise the turn is over and input unlocks.
            self._emit("turn_done", {"awaiting_answer": interrupted})

    # ─── stream handlers ────────────────────────────────────────────────
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
