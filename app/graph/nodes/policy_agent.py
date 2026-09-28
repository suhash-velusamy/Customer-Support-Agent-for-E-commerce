"""Policy Agent: RAG-grounded policy answers and return eligibility."""

from datetime import date, timedelta

from app.graph.deps import Deps
from app.graph.eligibility import check_return_eligibility, gather_return_policy
from app.tools.tavily_search import WEB_LABEL, format_web_results
from app.graph.nodes.common import fmt_date, tool_error_update, top_citation, with_actions

NO_EVIDENCE = ("I couldn't find anything in our policy that answers that. I don't want to guess, so I can "
               "connect you with a support specialist if you'd like.")
RECENT_DAYS = 14


def make_policy_agent(deps: Deps):
    tools = deps.tools

    async def policy_agent(state: dict) -> dict:
        if state.get("intent") == "RETURN_REQUEST":
            return await _return_request(state)
        if state.get("intent") == "PRODUCT_RECALL":
            return await _recall_check(state)
        return _answer_question(state)

    def _answer_question(state: dict) -> dict:
        entities = state.get("entities", {})
        results = deps.search_policy(entities.get("text") or state["messages"][-1].content, k=3)
        actions = ["Policy searched"]
        if not results:
            return {"policy_context": [], "final_response": NO_EVIDENCE,
                    "actions_taken": with_actions(state, *actions)}

        top = results[0]
        text = f"{top['text']}\n{top['citation']}"
        update = {"policy_context": results, "final_response": text}

        # Warranty claims and damage reports need a specialist per policy.
        if state.get("intent") == "WARRANTY" and entities.get("damaged") or \
                (state.get("intent") == "WARRANTY" and "not working" in entities.get("text", "").lower()):
            claims = top_citation(results, "Warranty claims") or \
                top_citation(deps.search_policy("warranty claims reviewed by specialist", k=2), "Warranty claims")
            if claims:
                update.update(
                    policy_context=[*results, claims],
                    escalation_required=True,
                    escalation_reason=[*state.get("escalation_reason", []),
                                       "Warranty claim requires specialist review"],
                )
        return {**update, "actions_taken": with_actions(state, *actions)}

    async def _recall_product(state: dict) -> tuple[str | None, list[str]]:
        """Product name to check, taken from the customer's own order data."""
        customer = state["customer_id"]
        hint = state.get("entities", {}).get("item_hint")
        if state.get("order_id"):
            order = await tools.call("get_order", order_id=state["order_id"], customer_id=customer)
            if order.get("ok"):
                items = [i for i in order["items"] if hint is None or i["category"] == hint] or order["items"]
                return items[0]["product_name"], ["Order verified"]
        if hint:
            listing = await tools.call("list_customer_orders", customer_id=customer)
            for o in listing.get("orders", []):
                for i in o["items"]:
                    if i["category"] == hint:
                        return i["product_name"], ["Order history reviewed"]
        return None, []

    async def _recall_check(state: dict) -> dict:
        product, actions = await _recall_product(state)
        if product is None:
            return {"final_response": "Which product would you like me to check for recalls? You can give the "
                                      "product name or the order number it came from.",
                    "actions_taken": with_actions(state, *actions)}
        web = await deps.web.product_recalls(product)
        if not web["ok"]:
            return {"final_response": f"I can't check recall notices for the {product} right now. Please try again "
                                      "later, or I can connect you with a support specialist.",
                    "actions_taken": with_actions(state, *actions)}
        actions.append("Product recall search performed")
        if not web["results"]:
            text = (f"I searched recent recall notices and didn't find any reports about the {product}. This is "
                    f"based on public web results, so it isn't a guarantee.\n({WEB_LABEL})")
        else:
            text = ("Here's what I found in public recall notices. Please check the sources, since these may "
                    "refer to a similar product from another seller.\n\n"
                    f"{format_web_results(web['results'], product + ' recall notices')}")
        return {"web_context": web["results"], "final_response": text,
                "actions_taken": with_actions(state, *actions)}

    async def _find_order(state: dict, item_hint: str | None, recent: bool) -> tuple[dict | None, dict]:
        """Return (order, update). update carries a response/escalation when no single order was found."""
        customer = state["customer_id"]
        if state.get("order_id"):
            order = await tools.call("get_order", order_id=state["order_id"], customer_id=customer)
            if not order.get("ok"):
                return None, tool_error_update(state, order)
            return order, {}

        listing = await tools.call("list_customer_orders", customer_id=customer)
        if not listing.get("ok"):
            return None, tool_error_update(state, listing)
        candidates = [o for o in listing["orders"]
                      if item_hint is None or any(i["category"] == item_hint for i in o["items"])]
        if recent:
            cutoff = deps.today() - timedelta(days=RECENT_DAYS)
            candidates = [o for o in candidates if date.fromisoformat(o["order_date"]) >= cutoff]
        if item_hint is None and len(candidates) > 1:
            candidates = []  # too vague to pick; ask for specifics

        if len(candidates) == 1:
            order = await tools.call("get_order", order_id=candidates[0]["order_id"], customer_id=customer)
            if not order.get("ok"):
                return None, tool_error_update(state, order)
            return order, {}
        if len(candidates) > 1:
            options = "\n".join(
                f"- #{o['order_id']} ({', '.join(i['product_name'] for i in o['items'])}, "
                f"ordered {fmt_date(o['order_date'])})" for o in candidates[:5]
            )
            return None, {"final_response": f"I found a few orders that could match:\n{options}\n\n"
                                            "Which order is it?"}
        return None, {"final_response": "I couldn't find a matching order on your account. Could you share "
                                        "the order number and which item you'd like to return?"}

    async def _return_request(state: dict) -> dict:
        entities = state.get("entities", {})
        policy = gather_return_policy(deps.search_policy)
        actions = ["Return policy checked"]

        order, update = await _find_order(state, entities.get("item_hint"), entities.get("recent", False))
        if order is None:
            return {**update, "policy_context": policy,
                    "actions_taken": [*update.get("actions_taken", with_actions(state)), *actions]}
        actions.insert(0, "Order verified")

        items = order["items"]
        if entities.get("item_hint"):
            items = [i for i in items if i["category"] == entities["item_hint"]] or items
        if len(items) > 1:
            names = "\n".join(f"- {i['product_name']}" for i in items)
            return {"order_id": order["order_id"], "order_data": order, "policy_context": policy,
                    "final_response": f"Order #{order['order_id']} has several items:\n{names}\n\n"
                                      "Which one would you like to return?",
                    "actions_taken": with_actions(state, *actions)}
        item = items[0]

        if entities.get("damaged"):
            damaged = deps.search_policy("item arrived damaged on arrival report photos", k=2)
            rule = top_citation(damaged, "Damaged on arrival")
            if rule:
                return {"order_id": order["order_id"], "order_data": order, "policy_context": [*policy, rule],
                        "escalation_required": True,
                        "escalation_reason": [*state.get("escalation_reason", []),
                                              "Damaged item report requires photo review"],
                        "actions_taken": with_actions(state, *actions, "Damaged-item policy checked")}

        result = check_return_eligibility(order, item, policy, deps.today())
        base = {"order_id": order["order_id"], "order_data": order, "policy_context": policy,
                "return_eligible": result.eligible}
        citations = "\n".join(result.citations)

        if result.eligible is None:
            return {**base, "escalation_required": True,
                    "escalation_reason": [*state.get("escalation_reason", []),
                                          f"Policy ambiguity: {result.reason}"],
                    "actions_taken": with_actions(state, *actions, "Return eligibility could not be confirmed")}

        if not result.eligible:
            text = (f"I'm sorry, but the {item['product_name']} from order #{order['order_id']} can't be returned. "
                    f"{result.reason}\n{citations}")
            return {**base, "final_response": text,
                    "actions_taken": with_actions(state, *actions, "Return eligibility checked: not eligible")}

        pending = {
            "order_id": order["order_id"],
            "item_ids": [item["item_id"]],
            "product_names": [item["product_name"]],
            "reason": entities.get("reason") or "Not specified by customer",
            "policy_reference": result.citations[0],
        }
        text = (f"Your {item['product_name']} from order #{order['order_id']} is eligible for return. "
                f"{result.reason}\n{citations}\n\n"
                "Would you like me to create the return now? Reply \"yes\" to confirm.")
        return {**base, "pending_return": pending, "final_response": text,
                "actions_taken": with_actions(state, *actions, "Return eligibility confirmed")}

    return policy_agent
