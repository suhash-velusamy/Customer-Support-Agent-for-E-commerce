"""LangGraph assembly and a small conversational wrapper."""

import asyncio
from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from app.config.settings import get_settings
from app.guardrails import check_output
from app.graph.deps import Deps
from app.graph.nodes.clarify import make_clarify_node
from app.graph.nodes.complaint_agent import make_complaint_agent
from app.graph.nodes.handoff import make_handoff_node
from app.graph.nodes.order_agent import make_order_agent
from app.graph.nodes.policy_agent import make_policy_agent
from app.graph.nodes.triage import make_triage_node
from app.graph.routing import after_specialist, after_triage
from app.graph.state import SupportState
from app.mcp.client import SupportTools

SPECIALISTS = ("order_agent", "policy_agent", "complaint_agent", "clarify")


async def respond(state: dict) -> dict:
    """Send the reply, after the output guardrail."""
    guard = check_output(state.get("final_response") or "", state.get("customer_id"))
    update: dict = {"messages": [AIMessage(guard.text)]}
    if guard.blocked:
        update.update(
            final_response=guard.text,
            guardrail_violations=guard.violations,
            actions_taken=[*state.get("actions_taken", []), "Reply blocked by safety check"],
        )
    return update


def build_graph(deps: Deps, checkpointer=None):
    graph = StateGraph(SupportState)
    graph.add_node("triage", make_triage_node(deps))
    graph.add_node("order_agent", make_order_agent(deps))
    graph.add_node("policy_agent", make_policy_agent(deps))
    graph.add_node("complaint_agent", make_complaint_agent(deps))
    graph.add_node("clarify", make_clarify_node(deps))
    graph.add_node("handoff", make_handoff_node(deps))
    graph.add_node("respond", respond)

    graph.add_edge(START, "triage")
    graph.add_conditional_edges("triage", after_triage, [*SPECIALISTS, "handoff", "respond"])
    for node in SPECIALISTS:
        graph.add_conditional_edges(node, after_specialist, ["handoff", "respond"])
    graph.add_edge("handoff", "respond")
    graph.add_edge("respond", END)
    return graph.compile(checkpointer=checkpointer)


def _default_llm():
    settings = get_settings()
    if not (settings.use_llm_triage and settings.openrouter_api_key):
        return None
    from app.config.llm import get_llm

    return get_llm()


class SupportAgent:
    """Multi-turn support agent. Each thread_id is one conversation."""

    def __init__(self, db_path: Path | str | None = None, customer_id: str | None = None,
                 use_llm: bool | None = None, **deps_overrides):
        llm = _default_llm() if use_llm in (None, True) else None
        self.customer_id = customer_id or get_settings().demo_customer_id
        self.deps = Deps(tools=SupportTools(db_path), llm=llm, **deps_overrides)
        self.graph = build_graph(self.deps, checkpointer=MemorySaver())

    async def achat(self, message: str, thread_id: str = "default") -> dict:
        return await self.graph.ainvoke(
            {"messages": [HumanMessage(message)], "customer_id": self.customer_id},
            {"configurable": {"thread_id": thread_id}},
        )

    def chat(self, message: str, thread_id: str = "default") -> dict:
        return asyncio.run(self.achat(message, thread_id))
