"""One-off diagnostic to print every message in the checkpointed state for
a given project, so we can find what's producing the 400 empty-parts error.
Usage: python inspect_state.py <project_id>
"""
import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from app.services import checkpointer as cp_svc


async def inspect(thread_id: str) -> None:
    await cp_svc.init_checkpointer()
    saver = cp_svc.get_checkpointer()
    config = {"configurable": {"thread_id": thread_id}}
    state = await saver.aget(config)
    if state is None:
        print("No state for thread", thread_id)
        await cp_svc.close_checkpointer()
        return
    msgs = state.get("channel_values", {}).get("messages", []) or []
    print(f"\nTotal messages in checkpoint: {len(msgs)}\n")
    print(f"{'idx':>3}  {'type':18s} {'content_len':>11s} {'tc':>3s} {'preview'}")
    print("-" * 100)
    empty_findings = []
    for i, m in enumerate(msgs):
        kind = type(m).__name__
        content = getattr(m, "content", "")
        if isinstance(content, list):
            # Multi-part content (e.g. images + text). Show shape.
            parts_desc = ",".join(
                f"{type(p).__name__}({len(getattr(p, 'text', '')) if hasattr(p, 'text') else '?'})"
                for p in content
            )
            cl = sum(
                len(getattr(p, "text", "")) if hasattr(p, "text") else 0
                for p in content
            )
            preview = f"[parts: {parts_desc}]"
        elif isinstance(content, str):
            cl = len(content)
            preview = content[:80].replace("\n", " ")
        else:
            cl = 0
            preview = f"<{type(content).__name__}>"
        tc = len(getattr(m, "tool_calls", []) or [])
        tcid = getattr(m, "tool_call_id", None)
        name = getattr(m, "name", None)
        tag = ""
        if tcid:
            tag = f" tcid={tcid[:8]}"
        if name:
            tag += f" name={name}"
        print(f"{i:3d}  {kind:18s} {cl:11d} {tc:>3d}  {preview}{tag}")
        # FLAG empty-content messages that don't have tool_calls (these are
        # the prime suspects for Vertex 400 "no parts" errors).
        if cl == 0 and tc == 0 and kind != "SystemMessage":
            empty_findings.append((i, kind, repr(m)[:300]))
    print()
    if empty_findings:
        print(f"!! Found {len(empty_findings)} suspect empty messages:")
        for i, kind, repr_str in empty_findings:
            print(f"  [{i}] {kind}: {repr_str}")
    else:
        print("No fully-empty non-system messages found at this level.")
        print("(The 400 may come from a message with content but empty parts list,")
        print(" or from how LangChain serializes a specific message type to Vertex.)")
    await cp_svc.close_checkpointer()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python inspect_state.py <thread_id>")
        sys.exit(1)
    asyncio.run(inspect(sys.argv[1]))
