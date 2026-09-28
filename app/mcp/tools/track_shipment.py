"""track_shipment tool implementation."""

import sqlite3

from app.mcp.tools.common import NOT_VERIFIED, error, normalize_order_id


def track_shipment(
    conn: sqlite3.Connection,
    customer_id: str,
    order_id: str | None = None,
    shipment_id: str | None = None,
) -> dict:
    if not order_id and not shipment_id:
        return error("missing_input", "Provide an order_id or a shipment_id.")

    # Ownership is checked through the join, for both lookup paths.
    query = (
        "SELECT s.*, o.status AS order_status FROM shipments s JOIN orders o ON o.order_id = s.order_id "
        "WHERE o.customer_id = ? AND "
    )
    if shipment_id:
        row = conn.execute(query + "s.shipment_id = ?", (customer_id, shipment_id.strip())).fetchone()
    else:
        row = conn.execute(query + "s.order_id = ?", (customer_id, normalize_order_id(order_id))).fetchone()

    if row is None:
        if order_id:
            owned = conn.execute(
                "SELECT status FROM orders WHERE order_id = ? AND customer_id = ?",
                (normalize_order_id(order_id), customer_id),
            ).fetchone()
            if owned is not None:
                return error("no_shipment", f"This order has no shipment yet (order status: {owned['status']}).")
        return error("order_not_verified", NOT_VERIFIED)

    return {
        "ok": True,
        "order_id": row["order_id"],
        "shipment_id": row["shipment_id"],
        "carrier": row["carrier"],
        "tracking_number": row["tracking_number"],
        "status": row["status"],
        "location": row["location"],
        "estimated_delivery": row["estimated_delivery"],
        "delivered_at": row["delivered_at"],
        "last_update": row["last_update"],
    }
