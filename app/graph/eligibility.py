"""Return eligibility, decided from retrieved policy text (not hard-coded rules).

The return window lengths and the non-returnable list are read from the policy chunks
returned by RAG. If a required rule wasn't retrieved, eligibility is unknown (None)
and no return may be created.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date

# Queries used to gather the return rules from the knowledge base.
RETURN_POLICY_QUERIES = [
    "30-day return window from delivery date",
    "electronics return window",
    "non-returnable product categories",
    "return order status requirement delivered",
]

# How each product category is named in the policy's non-returnable list.
CATEGORY_POLICY_TERMS = {
    "swimwear": ["swimwear"],
    "gift_card": ["gift card"],
    "personal_care": ["personal care"],
}


@dataclass
class Eligibility:
    eligible: bool | None  # None = insufficient policy evidence
    reason: str
    citations: list[str] = field(default_factory=list)


def gather_return_policy(search: Callable[..., list[dict]]) -> list[dict]:
    seen: dict[str, dict] = {}
    for query in RETURN_POLICY_QUERIES:
        for chunk in search(query, k=3):
            seen.setdefault(chunk["chunk_id"], chunk)
    return list(seen.values())


def _rule(chunks: list[dict], title: str) -> dict | None:
    return next((c for c in chunks if c["citation"].endswith(f"> {title}")), None)


def _days(rule: dict) -> int | None:
    match = re.search(r"(\d+) days", rule["text"])
    return int(match.group(1)) if match else None


def _missing(what: str) -> Eligibility:
    return Eligibility(None, f"No policy evidence was found for: {what}.")


def check_return_eligibility(order: dict, item: dict, policy: list[dict], today: date) -> Eligibility:
    status_rule = _rule(policy, "Order status requirement")
    if status_rule is None:
        return _missing("order status requirement")
    if order["status"] != "delivered":
        return Eligibility(False, f"The order hasn't been delivered yet (status: {order['status']}), "
                                  "so a return can't be started.", [status_rule["citation"]])

    if any(r["item_id"] == item["item_id"] and r["status"] != "rejected" for r in order.get("returns", [])):
        return Eligibility(False, "A return has already been requested for this item.")

    non_returnable = _rule(policy, "Non-returnable product categories")
    if non_returnable is None:
        return _missing("non-returnable products")
    terms = CATEGORY_POLICY_TERMS.get(item["category"], [])
    if any(term in non_returnable["text"].lower() for term in terms):
        return Eligibility(False, f"{item['product_name']} is in a non-returnable product category.",
                           [non_returnable["citation"]])

    window_title = "Electronics return window" if item["category"] == "electronics" else "30-day return window"
    window_rule = _rule(policy, window_title)
    window = _days(window_rule) if window_rule else None
    if window is None:
        return _missing("return window")
    if not order.get("delivered_at"):
        return Eligibility(None, "The delivery date for this order isn't available.")

    age = (today - date.fromisoformat(order["delivered_at"])).days
    if age > window:
        return Eligibility(False, f"It was delivered {age} days ago, which is outside the {window}-day return "
                                  "window.", [window_rule["citation"]])
    return Eligibility(True, f"It was delivered {age} days ago, within the {window}-day return window, and is "
                             "not in a non-returnable category.",
                       [window_rule["citation"], non_returnable["citation"]])
