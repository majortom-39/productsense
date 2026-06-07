"""Web-research tools for the research specialists.

Thin LangChain `@tool` wrappers around `app.services.firecrawl`. Only the
web-bound specialists (Iris, Aiden, Zara, Hugo, Theo) get these; the
synthesis-only specialists (Nora, Kai, Wes) work from the context Maya passes
them and take no tools.

The underlying firecrawl functions are async and return a clear error string
rather than raising — a specialist that loses its web tool mid-run should
degrade to an honest caveat, not crash the whole delegation.
"""
from __future__ import annotations

from langchain_core.tools import tool

from app.services import firecrawl


@tool
async def web_search(query: str) -> str:
    """Search the web and return the top results as formatted markdown.

    Use for live evidence: market signals, competitor pages, user complaints,
    technical references. `query` is a normal search string.
    """
    return await firecrawl.web_search(query)


@tool
async def crawl_website(url: str) -> str:
    """Fetch a single web page and return its main content as markdown.

    Use to read a specific page you already have the URL for (a competitor's
    pricing page, a docs page, a forum thread).
    """
    return await firecrawl.crawl_website(url)


@tool
async def reddit_research(query: str) -> str:
    """Search Reddit for first-person user discussion on a topic.

    Use to hear how real people describe a problem in their own words —
    complaints, workarounds, what they wish existed.
    """
    return await firecrawl.reddit_research(query)


# Tools handed to web-bound specialists. Synthesis specialists get [].
RESEARCH_TOOLS = [web_search, crawl_website, reddit_research]
