"""Dependencies injected into graph nodes (tools, retriever, clock, optional LLM)."""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from app.clock import today
from app.mcp.client import SupportTools
from app.rag.retriever import search_policy
from app.tools.tavily_search import WebSearch


@dataclass
class Deps:
    tools: SupportTools
    search_policy: Callable[..., list[dict]] = search_policy
    today: Callable[[], date] = today
    llm: Any | None = None
    web: WebSearch = field(default_factory=WebSearch)
    extra: dict = field(default_factory=dict)
