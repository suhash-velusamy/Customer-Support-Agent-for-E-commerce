"""Controlled Tavily web search for the two approved external lookups.

Only two query types are allowed: courier disruptions and product recalls. Results are
filtered for relevance, trimmed, and always labelled as external web information so they
are never presented as company policy. Without a TAVILY_API_KEY the search is skipped.
"""

from typing import Any

from app.config.settings import get_settings

MAX_RESULTS = 3
SNIPPET_CHARS = 300
MIN_SCORE = 0.3
WEB_LABEL = "External information (web search, not company policy)"


class WebSearch:
    def __init__(self, client: Any | None = None, api_key: str | None = None):
        # An injected client (tests) is reused; otherwise a fresh AsyncTavilyClient is created per
        # search, because its HTTP session is bound to the event loop it was first used on.
        self.client = client
        self.api_key = api_key if api_key is not None else get_settings().tavily_api_key

    @property
    def available(self) -> bool:
        return self.client is not None or bool(self.api_key)

    def _client(self):
        if self.client is not None:
            return self.client
        from tavily import AsyncTavilyClient

        return AsyncTavilyClient(api_key=self.api_key)

    async def _search(self, query: str, must_mention: str, **kwargs) -> dict:
        if not self.available:
            return {"ok": False, "error": "unavailable", "query": query, "results": []}
        try:
            raw = await self._client().search(query, max_results=6, search_depth="basic", **kwargs)
        except Exception:  # noqa: BLE001 - web search is optional; never break the conversation
            return {"ok": False, "error": "search_failed", "query": query, "results": []}

        needle = must_mention.lower()
        results = [
            {
                "title": r.get("title", "").strip(),
                "url": r.get("url", ""),
                "snippet": " ".join(r.get("content", "").split())[:SNIPPET_CHARS],
                "published_date": r.get("published_date"),
                "source": "web",
            }
            for r in raw.get("results", [])
            if r.get("score", 1.0) >= MIN_SCORE
            and needle in f"{r.get('title', '')} {r.get('content', '')}".lower()
        ]
        return {"ok": True, "query": query, "results": results[:MAX_RESULTS]}

    async def carrier_disruptions(self, carrier: str, location: str | None = None) -> dict:
        where = f" {location}" if location else ""
        query = f"{carrier} delivery delays service disruption{where}"
        return await self._search(query, must_mention=carrier, topic="news", time_range="week")

    async def product_recalls(self, product_name: str) -> dict:
        query = f"{product_name} product recall notice"
        return await self._search(query, must_mention="recall", topic="news", time_range="year")


def format_web_results(results: list[dict], heading: str) -> str:
    lines = [f"{WEB_LABEL}: {heading}"]
    for r in results:
        date = f" ({r['published_date'][:10]})" if r.get("published_date") else ""
        lines.append(f"- {r['title']}{date}: {r['snippet']} Source: {r['url']}")
    return "\n".join(lines)
