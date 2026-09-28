"""list_customer_orders tool: the authenticated customer's own recent orders.

Used to identify an order when the customer doesn't give an order number
("the shoes I bought last week") and to review delivery/complaint history.
"""

import sqlite3


def list_customer_orders(conn: sqlite3.Connection, customer_id: str, limit: int = 20) -> dict:
    rows = conn.execute(
        "SELECT o.order_id, o.order_date, o.status, o.refund_status, o.refund_requested_at, "
        "s.status AS shipment_status, s.estimated_delivery, s.delivered_at "
        "FROM orders o LEFT JOIN shipments s ON s.order_id = o.order_id "
        "WHERE o.customer_id = ? ORDER BY o.order_date DESC, o.order_id DESC LIMIT ?",
        (customer_id, limit),
    ).fetchall()

    orders = []
    for row in rows:
        items = conn.execute(
            "SELECT item_id, product_name, category, quantity FROM order_items WHERE order_id = ? ORDER BY item_id",
            (row["order_id"],),
        ).fetchall()
        late = row["shipment_status"] == "delayed" or (
            row["delivered_at"] is not None and row["delivered_at"] > row["estimated_delivery"]
        )
        orders.append({**dict(row), "late": late, "items": [dict(i) for i in items]})
    return {"ok": True, "orders": orders}
