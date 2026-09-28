"""Human Handoff: stop automation, build a structured case summary, tell the customer."""

import hashlib

from app.graph.deps import Deps
from app.graph.nodes.common import with_actions

INTENT_DESCRIPTIONS = {
    "ORDER_STATUS": "Find out the status of their order",
    "SHIPMENT_TRACKING": "Track their shipment",
    "RETURN_REQUEST": "Return an item",
    "REFUND_STATUS": "Receive their refund",
    "POLICY_QUESTION": "Get an answer to a policy question",
    "WARRANTY": "Make a warranty claim",
    "COMPLAINT": "Have their complaint resolved",
    "GENERAL_FAQ": "Get an answer to a general question",
    "SMALL_TALK": "Get help with their request",
    "PRODUCT_RECALL": "Find out whether a product has been recalled",
    "UNKNOWN": "Unclear; the agent could not determine the request",
}

NEXT_STEPS = {
    "Explicit manager request": "Have a manager contact the customer",
    "Explicit request for human support": "Contact the customer directly",
    "Repeated complaint": "Review the customer's delivery history and consider goodwill options per policy",
    "Strong negative/angry sentiment": "Reach out promptly and de-escalate",
    "Potential fraud/security issue": "Route to the fraud/security team and verify account access",
    "Sensitive case (legal, safety or personal circumstances)":
        "Handle with care; involve the appropriate team (legal/product safety) as needed",
    "Compensation request requires human approval":
        "Review the request against policy; the agent did not promise any compensation",
    "Tool failure after retry": "Retry the order lookup once systems are available",
    "Warranty claim requires specialist review": "Assess the warranty claim with the customer's photos/video",
    "Damaged item report requires photo review": "Request photos and arrange replacement or refund per policy",
}


def _issue(state: dict, reasons: list[str]) -> str:
    order = state.get("order_data") or {}
    delayed = state.get("delay_detected") or order.get("status") == "delayed"
    if "Repeated complaint" in reasons and (delayed or state.get("complaint_history")):
        return "Repeated order delays"
    if any(r.startswith("Refund pending") for r in reasons):
        return "Refund not received within the policy processing window"
    if "Potential fraud/security issue" in reasons:
        return "Possible fraud or account security concern"
    if delayed:
        return "Delayed order"
    return {
        "RETURN_REQUEST": "Return request needs review",
        "REFUND_STATUS": "Refund enquiry",
        "WARRANTY": "Warranty claim",
        "COMPLAINT": "Customer complaint",
    }.get(state.get("intent") or "", "Customer requested assistance")


def _customer_intent(state: dict, reasons: list[str]) -> str:
    if "Explicit manager request" in reasons:
        return "Speak with a manager"
    if "Explicit request for human support" in reasons:
        return "Speak with a human agent"
    return INTENT_DESCRIPTIONS.get(state.get("intent") or "", "Get help with their request")


def render_summary(summary: dict) -> str:
    return "\n".join([
        "Case Summary", "",
        "Issue:", summary["issue"], "",
        "Customer Intent:", summary["customer_intent"], "",
        "Order:", summary["order"], "",
        "History:", summary["history"], "",
        "Actions Taken:", *([f"- {a}" for a in summary["actions_taken"]] or ["- None"]), "",
        "Current Status:", summary["current_status"], "",
        "Reason for Escalation:", *[f"- {r}" for r in summary["reason_for_escalation"]], "",
        "Recommended Next Step:", summary["recommended_next_step"],
    ])


def make_handoff_node(deps: Deps):
    tools = deps.tools

    async def handoff(state: dict) -> dict:
        customer = state["customer_id"]
        actions: list[str] = []
        reasons = state.get("escalation_reason") or ["Customer requested human support"]
        order_id = state.get("order_id")
        order = state.get("order_data")
        shipment = state.get("shipment_data")
        history = state.get("complaint_history")

        # Gather context the human agent will need (own-account data only).
        listing = await tools.call("list_customer_orders", customer_id=customer)
        if listing.get("ok"):
            actions.append("Order history reviewed")
            late = [o for o in listing["orders"] if o["late"]]
            if len(late) >= 2:
                history = (f"{len(late)} late or delayed orders on record "
                           f"({', '.join('#' + o['order_id'] for o in late)})")
            if not order_id:
                delayed_now = [o for o in listing["orders"] if o["shipment_status"] == "delayed"]
                if len(delayed_now) == 1:
                    order_id = delayed_now[0]["order_id"]

        if order_id and not order:
            result = await tools.call("get_order", order_id=order_id, customer_id=customer)
            if result.get("ok"):
                order = result
                actions += ["Order verified", "Retrieved order details"]
            else:
                order_id = None
        if order and order.get("shipment_id") and not shipment:
            result = await tools.call("track_shipment", order_id=order["order_id"], customer_id=customer)
            if result.get("ok"):
                shipment = result
                actions.append("Checked shipment status")

        if state.get("entities", {}).get("repeated") and not history:
            history = "Customer reports this is a repeated problem"
        if shipment and shipment["status"] != "delivered":
            status = (f"Shipment {shipment['status'].replace('_', ' ')} with {shipment['carrier']}, last location "
                      f"{shipment['location']}, estimated delivery {shipment['estimated_delivery']}")
        elif order:
            status = f"Order status: {order['status']}; refund status: {order['refund_status']}"
        else:
            status = "No order identified"

        all_actions = with_actions(state, *actions, "Escalated to human support")
        summary = {
            "issue": _issue({**state, "order_data": order}, reasons),
            "customer_intent": _customer_intent(state, reasons),
            "order_id": order["order_id"] if order else None,
            "order": f"#{order['order_id']} ({order['status']})" if order else "Not identified",
            "history": history or "No previous issues recorded in this conversation",
            "actions_taken": all_actions,
            "current_status": status,
            "reason_for_escalation": reasons,
            "recommended_next_step": "; ".join(dict.fromkeys(NEXT_STEPS.get(r, "Review the case") for r in reasons)),
            "policy_references": [c["citation"] for c in state.get("policy_context", [])],
        }
        case_id = "CASE-" + hashlib.sha1(f"{customer}:{reasons}:{order_id}".encode()).hexdigest()[:6].upper()
        summary["case_id"] = case_id

        who = "a manager" if "Explicit manager request" in reasons else "a human support specialist"
        response = (f"I'm sorry for the trouble. I've passed your case to {who}, who will follow up with you. "
                    "They'll have a full summary of what we've discussed and checked, so you won't need to repeat "
                    f"yourself.\n\nCase reference: {case_id}")
        return {
            "order_id": order_id,
            "order_data": order,
            "shipment_data": shipment,
            "escalation_required": True,
            "escalation_reason": reasons,
            "handoff_summary": summary,
            "handed_off": True,
            "case_id": case_id,
            "final_response": response,
            "actions_taken": all_actions,
        }

    return handoff
