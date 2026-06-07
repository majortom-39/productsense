from langchain.tools import ToolRuntime
from langchain_core.tools import tool


@tool
def probe(x: str, runtime: ToolRuntime) -> str:
    """probe tool"""
    cfg = runtime.config or {}
    return "conf=" + str((cfg.get("configurable") or {}))


print("LLM-facing args:", probe.args)
print(probe.invoke({"x": "hi"}, config={"configurable": {"project_id": "P123", "thread_id": "P123"}}))
