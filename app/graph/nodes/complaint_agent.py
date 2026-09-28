"""Complaint Agent: acknowledge, review the order, attempt resolution, escalate repeats."""

from app.graph.deps import Deps
from app.graph.nodes.common import fmt_date, tool_error_update, top_citation, with_actions

OFFER_HUMAN = "If you'd prefer, I can pass this to a human support specialist."


def make_complaint_agent(deps: Deps):
    tools = deps.tools

    async def complaint_agent(state: dict) -> dict:
        customer = state["customer_id"]
        entities = state.get("entities", {})
        actions: list[str] = []

        listing = await tools.call("list_customer_orders", customer_id=customer)
        if not listing.get("ok"):
            return tool_error_update(state, listing)
        actions.append("Order history reviewed")
        late_orders = [o for o in listing["orders"] if o["late"]]

        order_id = state.get("order_id")
        if not order_id:
            delayed_now = [o for o in listing["orders"] if o["shipment_status"] == "delayed"]
            order_id = delayed_now[0]["order_id"] if len(delayed_now) == 1 else None

        repeated = entities.get("repeated") or state.get("complaint_count", 0) >= 2
        if repeated:
            return {
                "order_id": order_id,
                "escalation_required": True,
                "escalation_reason": [*state.get("escalation_reason", []), "Repeated complaint"],
                "actions_taken": with_actions(state, *actions),
            }

        lines = ["I'm sorry about this experience, and thank you for letting us know."]
        update: dict = {"order_id": order_id}
        if order_id:
            order = await tools.call("get_order", order_id=order_id, customer_id=customer)
            if not order.get("ok"):
                return tool_error_update(state, order, *actions)
            actions += ["Order verified", "Order details retrieved"]
            update["order_data"] = order
            if order["shipment_id"]:
                shipment = await tools.call("track_shipment", order_id=order_id, customer_id=customer)
                if shipment.get("ok"):
                    actions.append("Shipment status retrieved")
                    update["shipment_data"] = shipment
                    if shipment["status"] == "delivered":
                        lines.append(f"Order #{order_id} was delivered on {fmt_date(shipment['delivered_at'])}.")
                    else:
                        lines.append(f"Order #{order_id} is currently {shipment['status'].replace('_', ' ')} with "
                                     f"{shipment['carrier']}, last seen in {shipment['location']}, with an estimated "
                                     f"delivery of {fmt_date(shipment['estimated_delivery'])}.")
                    if shipment["status"] == "delayed":
                        update["delay_detected"] = True
                        policy = deps.search_policy("delayed shipments carrier delays", k=2)
                        actions.append("Shipping policy checked")
                        update["policy_context"] = policy
                        rule = top_citation(policy, "Delayed shipments")
                        if rule:
                            lines.append(f"{rule['text']}\n{rule['citation']}")
            else:
                lines.append(f"Order #{order_id} is currently {order['status']}.")
        else:
            lines.append("Could you share the order number this is about, so I can look into it?")

        if len(late_orders) >= 2:
            update["complaint_history"] = f"{len(late_orders)} late or delayed orders on record"
        lines.append(OFFER_HUMAN)
        return {**update, "final_response": "\n\n".join(lines), "actions_taken": with_actions(state, *actions)}

    return complaint_agent
