"""Routing decisions between graph nodes."""

ORDER_INTENTS = {"ORDER_STATUS", "SHIPMENT_TRACKING", "REFUND_STATUS", "CONFIRM_RETURN"}
POLICY_INTENTS = {"RETURN_REQUEST", "POLICY_QUESTION", "WARRANTY", "GENERAL_FAQ", "PRODUCT_RECALL"}


def choose_route(state: dict) -> str:
    """Specialist node for the current turn, decided after triage."""
    if state.get("escalation_required"):
        return "handoff"
    intent = state.get("intent")
    if intent in ORDER_INTENTS:
        return "order_agent"
    if intent in POLICY_INTENTS:
        return "policy_agent"
    if intent == "COMPLAINT":
        return "complaint_agent"
    if intent == "HUMAN_HANDOFF":
        return "handoff"
    return "clarify"


def after_triage(state: dict) -> str:
    return state.get("route") or "clarify"


def after_specialist(state: dict) -> str:
    """Specialists either resolved the turn or raised an escalation."""
    return "handoff" if state.get("escalation_required") else "respond"
