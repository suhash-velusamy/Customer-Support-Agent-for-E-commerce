"""initiate_return tool implementation.

Policy eligibility (return window, non-returnable categories) is decided by the Policy Agent
using RAG. This tool refuses to act unless the caller passes that confirmation together with
the policy citation it relied on, and it independently re-checks the facts it owns in the
database (ownership, delivery, item membership, duplicate returns).
"""

import sqlite3
from datetime import datetime

from app.mcp.tools.common import NOT_VERIFIED, error, fetch_owned_order


def _next_return_id(conn: sqlite3.Connection) -> str:
    row = conn.execute(
        "SELECT MAX(CAST(SUBSTR(return_id, 5) AS INTEGER)) FROM returns WHERE return_id LIKE 'RET-%'"
    ).fetchone()
    return f"RET-{(row[0] or 5000) + 1}"


def initiate_return(
    conn: sqlite3.Connection,
    customer_id: str,
    order_id: str,
    item_ids: list[str],
    reason: str,
    eligibility_confirmed: bool,
    policy_reference: str,
    now: datetime | None = None,
) -> dict:
    if not eligibility_confirmed or not policy_reference.strip():
        return error(
            "eligibility_not_confirmed",
            "Return eligibility must be confirmed against company policy before a return can be created.",
        )
    if not item_ids:
        return error("missing_input", "Specify at least one item to return.")
    if not reason.strip():
        return error("missing_input", "A return reason is required.")

    order = fetch_owned_order(conn, order_id, customer_id)
    if order is None:
        return error("order_not_verified", NOT_VERIFIED)
    if order["status"] != "delivered":
        return error("not_delivered", f"Only delivered orders can be returned (order status: {order['status']}).")

    order_items = {
        r["item_id"]: r["product_name"]
        for r in conn.execute("SELECT item_id, product_name FROM order_items WHERE order_id = ?", (order["order_id"],))
    }
    unknown = [i for i in item_ids if i not in order_items]
    if unknown:
        return error("unknown_item", f"Item(s) not part of this order: {', '.join(unknown)}.")

    already = {
        r["item_id"]
        for r in conn.execute(
            "SELECT item_id FROM returns WHERE order_id = ? AND status != 'rejected'", (order["order_id"],)
        )
    }
    duplicates = [i for i in item_ids if i in already]
    if duplicates:
        return error("already_returned", f"A return already exists for: {', '.join(duplicates)}.")

    created_at = (now or datetime.now()).replace(microsecond=0).isoformat()
    created = []
    for item_id in item_ids:
        return_id = _next_return_id(conn)
        conn.execute(
            "INSERT INTO returns VALUES (?,?,?,?,?,?)",
            (return_id, order["order_id"], item_id, reason.strip(), "requested", created_at),
        )
        created.append({"return_id": return_id, "item_id": item_id, "product_name": order_items[item_id]})
    conn.commit()

    return {
        "ok": True,
        "order_id": order["order_id"],
        "returns": created,
        "status": "requested",
        "policy_reference": policy_reference,
        "next_steps": [
            "You'll receive a return shipping label by email.",
            "Pack the item(s) in their original packaging and drop them off with the carrier.",
        ],
        "processing_info": "Your refund is processed after the returned item is received and inspected, "
        "within the timeframe set out in the refund policy.",
    }
