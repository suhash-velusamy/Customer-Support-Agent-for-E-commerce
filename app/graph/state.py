"""Typed LangGraph state shared across all nodes."""

from typing import Annotated, TypedDict

from langgraph.graph.message import add_messages


class SupportState(TypedDict, total=False):
    messages: Annotated[list, add_messages]
    customer_id: str

    # Set by triage each turn
    intent: str | None
    sentiment: str | None
    route: str | None
    entities: dict  # item_hint, recent, reason, damaged, repeated, injection, ...

    # Carried across turns
    order_id: str | None
    pending_return: dict | None  # eligible return awaiting customer confirmation
    complaint_count: int
    unknown_count: int
    handed_off: bool
    complaint_history: str | None
    case_id: str | None

    # Per-turn results
    escalation_required: bool
    escalation_reason: list[str]
    order_data: dict | None
    shipment_data: dict | None
    policy_context: list[dict]
    web_context: list[dict]
    delay_detected: bool
    return_eligible: bool | None
    return_result: dict | None
    final_response: str | None
    handoff_summary: dict | None
    guardrail_violations: list[str]

    # Cumulative, human-readable activity log (safe to show in UI)
    actions_taken: list[str]
