"""Tier 1 / Tier 3 clarification routing.

When the coding agent asks a clarification question via MCP, we:
  1. Load PRD + decisions + guardrails + task spec
  2. Ask Maya (one-shot, non-streaming) to either answer (Tier 1) or
     escalate (Tier 3) — instructed to output strict JSON
  3. Tier 1 → log a maya_autonomous decision, return answer
  4. Tier 3 → log an open decision tagged escalated + open clarification, return queued
"""
from __future__ import annotations

import json
import re

from app.config import settings
from app.db import require_admin
from app.services import artifacts, gemini, prompts


_TIER_INSTR = (
    "\n\n## Clarification mode\n"
    "You're being asked a clarification question by the coding agent over MCP. "
    "Output ONE JSON object — no prose outside it.\n\n"
    "If you can answer with high confidence from PRD + decisions + guardrails:\n"
    '{\"tier\": 1, \"answer\": str, \"reasoning\": str, \"title\": str, \"why\": str}\n'
    "title is a short label for the auto-logged decision; why is the rationale.\n\n"
    "If the question is ambiguous, would change a PRD-level rule, or you have low confidence:\n"
    '{\"tier\": 3, \"recommendation\": str, \"reasoning\": str, \"title\": str}\n'
    "Don't guess on Tier 3 — escalate."
)


async def clarify(
    *, project_id: str, task_id: str, question: str
) -> dict:
    prd = artifacts.get_active_prd(project_id)
    decisions = artifacts.list_decisions(project_id)
    guardrails = [d for d in decisions if d.get("tag") == "guardrail"]
    decided = [d for d in decisions if d.get("tag") != "guardrail" and d["status"] == "decided"]
    task = artifacts.get_task(task_id)

    context = (
        f"## Task\n{task.get('display_id', '')} — {task.get('title', '')}\n"
        f"Description: {task.get('description', '')}\n"
        f"Acceptance: {task.get('acceptance', [])}\n\n"
        f"## Question from coding agent\n{question}\n\n"
        f"## PRD\n{(prd or {}).get('body_md', '(no PRD yet)')}\n\n"
        f"## Decisions log (last 10)\n"
        + "\n".join(f"- {d['display_id']}: {d['title']} — {d['detail']}" for d in decided[:10])
        + "\n\n## Guardrails\n"
        + "\n".join(f"- {g['title']}: {g['detail']}" for g in guardrails)
    )

    response = await gemini.call(
        model=settings.maya_model,
        system=prompts.MAYA + _TIER_INSTR,
        contents=[gemini.text_turn("user", context)],
        thinking_level=settings.maya_thinking_level,
    )
    raw = gemini.extract_text(response).strip()
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.MULTILINE).strip()

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # Default to escalation when parse fails
        data = {"tier": 3, "recommendation": raw[:500], "reasoning": "(parse fail)", "title": "Unparsed clarification"}

    tier = int(data.get("tier", 3))

    if tier == 1:
        decision = artifacts.log_decision(
            project_id=project_id,
            decided_by="maya_autonomous",
            title=data.get("title", "Clarification"),
            detail=data.get("answer", ""),
            why=data.get("why") or data.get("reasoning", ""),
            related_task_id=task_id,
        )
        return {
            "tier": 1,
            "decision_id": decision.get("display_id"),
            "answer": data.get("answer"),
            "reasoning": data.get("reasoning"),
        }

    # Tier 3
    open_decision = artifacts.log_decision(
        project_id=project_id,
        decided_by="agent_flagged",
        title=data.get("title", "Needs your judgment"),
        detail=question,
        why=data.get("reasoning", ""),
        related_task_id=task_id,
        status="open",
        open_type="escalated",
    )
    # Open clarification row
    require_admin().table("clarifications").insert({
        "project_id": project_id,
        "related_task_id": task_id,
        "decision_id": open_decision.get("id"),
        "question": question,
        "status": "open",
    }).execute()
    # Mark task as having an open decision
    require_admin().table("tasks").update(
        {"open_decision_id": open_decision.get("id")}
    ).eq("id", task_id).execute()

    next_unblocked = [
        t["id"] for t in artifacts.list_tasks(project_id, status="todo")
        if not t.get("blocked_by") and t["id"] != task_id
    ][:5]

    return {
        "tier": 3,
        "decision_id": open_decision.get("display_id"),
        "status": "queued",
        "maya_recommendation": data.get("recommendation"),
        "next_unblocked_task_ids": next_unblocked,
    }
