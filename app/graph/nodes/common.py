"""Helpers shared by the specialist nodes."""

from datetime import date

from app.mcp.tools.common import NOT_VERIFIED

TOOL_FAILURE_REASON = "Tool failure after retry"


def fmt_date(value: str | None) -> str:
    if not value:
        return "not available"
    d = date.fromisoformat(value[:10])
    return f"{d:%B} {d.day}"


def with_actions(state: dict, *actions: str) -> list[str]:
    return [*state.get("actions_taken", []), *actions]


def tool_error_update(state: dict, result: dict, *actions: str) -> dict:
    """State update for a failed tool call: privacy block, or escalation on tool failure."""
    if result.get("error") == "tool_failure":
        return {
            "escalation_required": True,
            "escalation_reason": [*state.get("escalation_reason", []), TOOL_FAILURE_REASON],
            "actions_taken": with_actions(state, *actions, "Order lookup failed (service unavailable)"),
        }
    if result.get("error") == "order_not_verified":
        return {
            "order_id": None,
            "order_data": None,
            "final_response": NOT_VERIFIED,
            "actions_taken": with_actions(state, *actions, "Order ownership could not be verified"),
        }
    return {"final_response": result.get("message", "I couldn't complete that request."),
            "actions_taken": with_actions(state, *actions)}


def top_citation(results: list[dict], title: str) -> dict | None:
    return next((r for r in results if r["citation"].endswith(f"> {title}")), None)
