"""Order Agent: order status, shipment tracking, refund status, and executing confirmed returns."""

import re
from datetime import date, timedelta

from app.graph.deps import Deps
from app.tools.tavily_search import format_web_results
from app.graph.nodes.common import fmt_date, tool_error_update, top_citation, with_actions

ASK_ORDER_ID = "Could you share your order number (for example #10245) so I can look that up for you?"
STATUS_TEXT = {
    "processing": "is being processed and hasn't shipped yet",
    "shipped": "has shipped and is on its way",
    "delayed": "is delayed",
    "delivered": "has been delivered",
    "cancelled": "was cancelled",
}


def _is_delayed(shipment: dict | None, today: date) -> bool:
    if not shipment or shipment["status"] == "delivered":
        return False
    eta = shipment.get("estimated_delivery")
    return shipment["status"] == "delayed" or (eta is not None and date.fromisoformat(eta) < today)


def _sentence(text: str, containing: str) -> str:
    """The policy sentence that mentions `containing` (falls back to the whole rule)."""
    return next((s.strip() for s in re.split(r"(?<=\.)\s+", text) if containing in s), text)


def make_order_agent(deps: Deps):
    tools = deps.tools

    async def order_agent(state: dict) -> dict:
        if state.get("intent") == "CONFIRM_RETURN":
            return await _create_return(state)

        customer = state["customer_id"]
        order_id = state.get("order_id")
        actions: list[str] = []

        if not order_id and state.get("intent") == "REFUND_STATUS":
            listing = await tools.call("list_customer_orders", customer_id=customer)
            if not listing.get("ok"):
                return tool_error_update(state, listing)
            actions.append("Order history reviewed")
            open_refunds = [o for o in listing["orders"] if o["refund_status"] in ("pending", "processing")]
            if len(open_refunds) == 1:
                order_id = open_refunds[0]["order_id"]
            elif len(open_refunds) > 1:
                ids = ", ".join(f"#{o['order_id']}" for o in open_refunds)
                return {"final_response": f"You have refunds in progress on orders {ids}. Which one is this about?",
                        "actions_taken": with_actions(state, *actions)}
            else:
                return {"final_response": "I couldn't find a refund in progress on your account. "
                                          + ASK_ORDER_ID, "actions_taken": with_actions(state, *actions)}
        if not order_id:
            return {"final_response": ASK_ORDER_ID}

        order = await tools.call("get_order", order_id=order_id, customer_id=customer)
        if not order.get("ok"):
            return tool_error_update(state, order, *actions)
        actions += ["Order verified", "Order details retrieved"]

        if state.get("intent") == "REFUND_STATUS":
            return _refund_status(state, order, actions)
        return await _order_status(state, order, actions)

    async def _order_status(state: dict, order: dict, actions: list[str]) -> dict:
        shipment = None
        if order["shipment_id"]:
            shipment = await tools.call("track_shipment", order_id=order["order_id"], customer_id=state["customer_id"])
            if not shipment.get("ok"):
                return {**tool_error_update(state, shipment, *actions), "order_data": order}
            actions.append("Shipment status retrieved")

        items = ", ".join(f"{i['product_name']} x{i['quantity']}" for i in order["items"])
        lines = [f"Your order #{order['order_id']} ({items}) {STATUS_TEXT[order['status']]}."]
        delayed = _is_delayed(shipment, deps.today())
        policy_context: list[dict] = []
        web_context: list[dict] = []

        if shipment:
            lines.append("")
            lines.append(f"Carrier: {shipment['carrier']}")
            if state.get("intent") == "SHIPMENT_TRACKING" or order["status"] != "delivered":
                lines.append(f"Tracking number: {shipment['tracking_number']}")
            if shipment["status"] == "delivered":
                lines.append(f"Delivered: {fmt_date(shipment['delivered_at'])}")
            else:
                lines.append(f"Current location: {shipment['location']}")
                lines.append(f"Estimated delivery: {fmt_date(shipment['estimated_delivery'])}")
            lines.append(f"Last update: {fmt_date(shipment['last_update'])}")
        elif order["status"] == "processing":
            lines.append("Tracking details will be available once it ships.")
        elif order["status"] == "cancelled":
            lines.append(f"Refund status: {order['refund_status']}.")

        if delayed:
            policy_context = deps.search_policy("delayed shipments carrier delays estimated delivery", k=2)
            actions.append("Shipping policy checked")
            rule = top_citation(policy_context, "Delayed shipments")
            # Only delayed shipments justify an external lookup.
            web = await deps.web.carrier_disruptions(shipment["carrier"], shipment["location"])
            if web["ok"]:
                actions.append("Carrier disruption search performed")
                web_context = web["results"]
            lines.append("")
            if web_context:
                lines.append("I'm sorry this is running behind. Recent reports mention delivery disruptions for "
                             f"{shipment['carrier']}, which may explain the delay (see below).")
            else:
                lines.append("I'm sorry this is running behind. The carrier has marked the shipment as delayed, and "
                             "I don't have a confirmed reason for the delay yet.")
            if rule:
                lines.append(f"{_sentence(rule['text'], 'support review')}\n{rule['citation']}")

        if web_context:
            lines.append("")
            lines.append(format_web_results(web_context, f"{shipment['carrier']} service updates"))

        return {
            "order_data": order,
            "shipment_data": shipment,
            "web_context": web_context,
            "delay_detected": delayed,
            "policy_context": policy_context,
            "final_response": "\n".join(lines),
            "actions_taken": with_actions(state, *actions),
        }

    def _refund_status(state: dict, order: dict, actions: list[str]) -> dict:
        policy = deps.search_policy("refund processing time delayed refunds not arrived", k=3)
        actions.append("Refund policy checked")
        processing = top_citation(policy, "Refund processing time")
        delayed_rule = top_citation(policy, "Delayed refunds")
        base = {"order_data": order, "policy_context": policy}
        status = order["refund_status"]

        if status == "none":
            text = (f"There's no refund recorded on order #{order['order_id']}. If you've sent an item back, "
                    "it may not have been received at our warehouse yet.")
            return {**base, "final_response": text, "actions_taken": with_actions(state, *actions)}
        if status == "completed":
            text = (f"The refund for order #{order['order_id']} has been completed and sent to your original "
                    "payment method.")
            if processing:
                text += f" Banks can take a few extra business days to show the credit.\n{processing['citation']}"
            return {**base, "final_response": text, "actions_taken": with_actions(state, *actions)}

        # pending / processing
        if not (processing and delayed_rule and order.get("refund_requested_at")):
            return {**base, "escalation_required": True,
                    "escalation_reason": [*state.get("escalation_reason", []),
                                          "Policy ambiguity: refund timing rule not found"],
                    "actions_taken": with_actions(state, *actions)}

        limit = int(re.search(r"(\d+) calendar days", delayed_rule["text"]).group(1))
        started = date.fromisoformat(order["refund_requested_at"])
        waited = (deps.today() - started).days
        if waited > limit:
            return {**base, "escalation_required": True,
                    "escalation_reason": [*state.get("escalation_reason", []),
                                          f"Refund pending {waited} days, beyond the {limit}-day policy window"],
                    "actions_taken": with_actions(state, *actions)}

        review_date = fmt_date((started + timedelta(days=limit)).isoformat())
        text = (
            f"The refund for order #{order['order_id']} was started on {fmt_date(order['refund_requested_at'])} "
            f"and is currently {status} ({waited} days so far).\n\n"
            f"{processing['text']}\n{processing['citation']}\n\n"
            f"That's still within our {limit}-day processing window. If it hasn't arrived by {review_date}, let us "
            f"know and a specialist will review it.\n{delayed_rule['citation']}"
        )
        return {**base, "final_response": text, "actions_taken": with_actions(state, *actions)}

    async def _create_return(state: dict) -> dict:
        pending = state.get("pending_return")
        # Guardrail: only create a return that the Policy Agent confirmed, with its citation.
        if not pending or not state.get("return_eligible") or not pending.get("policy_reference"):
            return {"final_response": "I can't create a return until its eligibility has been confirmed against "
                                      "our return policy.", "pending_return": None}
        result = await tools.call(
            "initiate_return",
            customer_id=state["customer_id"],
            order_id=pending["order_id"],
            item_ids=pending["item_ids"],
            reason=pending["reason"],
            eligibility_confirmed=True,
            policy_reference=pending["policy_reference"],
        )
        if not result.get("ok"):
            return {**tool_error_update(state, result), "pending_return": None}

        ids = ", ".join(r["return_id"] for r in result["returns"])
        names = ", ".join(r["product_name"] for r in result["returns"])
        steps = "\n".join(f"- {s}" for s in result["next_steps"])
        text = (f"Your return has been created.\n\nReturn ID: {ids}\nItem: {names} (order #{pending['order_id']})\n\n"
                f"Next steps:\n{steps}\n\n{result['processing_info']}\n{pending['policy_reference']}")
        return {"return_result": result, "pending_return": None, "final_response": text,
                "actions_taken": with_actions(state, "Return created")}

    return order_agent
