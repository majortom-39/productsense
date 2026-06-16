"""Firecrawl wrappers used by research sub-agents.

Three callable tools:
    web_search(query) → bullet-formatted top results
    crawl_website(url) → page markdown (capped)
    reddit_research(query) → reddit-focused query

Lazy client. Returns a clear error string on failure rather than raising —
sub-agents need to keep going.
"""
from __future__ import annotations

import asyncio
import os
from typing import Optional

try:
    from firecrawl import AsyncFirecrawl
    from firecrawl.v2.types import ScrapeOptions
except Exception:  # firecrawl optional during install/dev
    AsyncFirecrawl = None  # type: ignore[assignment]
    ScrapeOptions = None  # type: ignore[assignment]


_CRAWL_TIMEOUT_S = 45.0
_SEARCH_TIMEOUT_S = 25.0  # snippet search is fast; cap a stuck call so one slow
                         # search can't stall a whole specialist
_MAX_CONTENT_CHARS = 2000

_client: Optional["AsyncFirecrawl"] = None


def _get_client() -> "AsyncFirecrawl":
    global _client
    if _client is None:
        if AsyncFirecrawl is None:
            raise RuntimeError("firecrawl package not installed")
        api_key = os.getenv("FIRECRAWL_API_KEY")
        if not api_key:
            raise RuntimeError("FIRECRAWL_API_KEY not set")
        _client = AsyncFirecrawl(api_key=api_key)
    return _client


async def web_search(query: str, limit: int = 6) -> str:
    # NOTE: deliberately NO scrape_options. Passing ScrapeOptions(formats=["markdown"])
    # makes firecrawl fully scrape the page body of every result, which turned a
    # single search into a 30-60s call — multiplied across several searches per
    # specialist, that was the bulk of a multi-minute turn. The result SNIPPETS
    # (title + url + description) are enough for synthesis; a specialist that needs
    # the full text of one page calls crawl_website(url) on just that page.
    try:
        client = _get_client()
        result = await asyncio.wait_for(
            client.search(query=query, limit=limit),
            timeout=_SEARCH_TIMEOUT_S,
        )
    except asyncio.TimeoutError:
        return f"[web_search timeout] {query}"
    except Exception as e:
        return f"[web_search error] {str(e)[:200]}"

    parts = [f"**Web Search:** {query}\n"]
    items = getattr(result, "web", None) or []
    if not items:
        return parts[0] + "\nNo results."
    for i, item in enumerate(items, 1):
        title = getattr(item, "title", "") or "(no title)"
        url = getattr(item, "url", "") or ""
        snippet = getattr(item, "description", "") or getattr(item, "markdown", "") or ""
        parts.append(f"\n**[{i}] {title}**\n{url}\n{snippet[:_MAX_CONTENT_CHARS].strip()}")
    return "\n---\n".join(parts)


async def crawl_website(url: str) -> str:
    try:
        client = _get_client()
        result = await asyncio.wait_for(
            client.scrape(url=url, formats=["markdown"]),
            timeout=_CRAWL_TIMEOUT_S,
        )
    except asyncio.TimeoutError:
        return f"[crawl_website timeout] {url}"
    except Exception as e:
        return f"[crawl_website error] {url}: {str(e)[:200]}"
    md = getattr(result, "markdown", "") or ""
    return f"**Crawled {url}**\n\n{md[:4000]}"


async def reddit_research(query: str) -> str:
    """Reddit-focused web search. Wraps web_search with a site: clause."""
    return await web_search(f"site:reddit.com {query}")
