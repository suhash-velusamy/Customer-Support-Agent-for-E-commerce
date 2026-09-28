"""get_order tool implementation."""

import sqlite3

from app.mcp.tools.common import NOT_VERIFIED, error, fetch_owned_order


def get_order(conn: sqlite3.Connection, order_id: str, customer_id: str) -> dict:
    order = fetch_owned_order(conn, order_id, customer_id)
    if order is None:
        return error("order_not_verified", NOT_VERIFIED)

    items = conn.execute(
        "SELECT item_id, product_id, product_name, category, quantity, price "
        "FROM order_items WHERE order_id = ? ORDER BY item_id",
        (order["order_id"],),
    ).fetchall()
    returns = conn.execute(
        "SELECT return_id, item_id, reason, status, created_at FROM returns WHERE order_id = ? ORDER BY created_at",
        (order["order_id"],),
    ).fetchall()
    delivered_at = conn.execute(
        "SELECT delivered_at FROM shipments WHERE order_id = ?", (order["order_id"],)
    ).fetchone()

    return {
        "ok": True,
        "order_id": order["order_id"],
        "customer_id": order["customer_id"],
        "order_date": order["order_date"],
        "status": order["status"],
        "total_amount": order["total_amount"],
        "shipment_id": order["shipment_id"],
        "delivered_at": delivered_at["delivered_at"] if delivered_at else None,
        "payment_status": order["payment_status"],
        "refund_status": order["refund_status"],
        "refund_requested_at": order["refund_requested_at"],
        "items": [dict(i) for i in items],
        "returns": [dict(r) for r in returns],
    }
