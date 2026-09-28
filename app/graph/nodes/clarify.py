"""Clarification for unclear requests; hands off after repeated failures to understand."""

from app.graph.deps import Deps

CLARIFY = ("I'm not sure I understood. I can help with order status and tracking, returns, refunds, exchanges, "
           "warranty and our store policies. Could you tell me a bit more, and include your order number if "
           "you have one?")
REFUSE_INTERNALS = ("I can't share internal instructions or system details, but I'm happy to help with your "
                    "orders, returns, refunds or our policies.")
MAX_UNKNOWN = 2


def make_clarify_node(deps: Deps):
    async def clarify(state: dict) -> dict:
        if state.get("entities", {}).get("injection"):
            return {"final_response": REFUSE_INTERNALS}
        if state.get("unknown_count", 0) >= MAX_UNKNOWN:
            return {"escalation_required": True,
                    "escalation_reason": ["Agent unable to understand the request after clarification"]}
        return {"final_response": CLARIFY}

    return clarify
