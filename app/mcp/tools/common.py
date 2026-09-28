"""Shared helpers for MCP tools: ownership verification and error results."""

import re
import sqlite3

# Same message whether the order doesn't exist or belongs to someone else,
# so callers can't probe which order IDs exist.
NOT_VERIFIED = "I can't provide details for that order because I couldn't verify that it belongs to your account."


def error(code: str, message: str) -> dict:
    return {"ok": False, "error": code, "message": message}


def normalize_order_id(order_id: str) -> str:
    """Accept '#10245', 'order 10245', ' 10245 ' etc."""
    match = re.search(r"\d+", str(order_id))
    return match.group(0) if match else str(order_id).strip()


def fetch_owned_order(conn: sqlite3.Connection, order_id: str, customer_id: str) -> sqlite3.Row | None:
    """Return the order row only if it belongs to customer_id."""
    return conn.execute(
        "SELECT * FROM orders WHERE order_id = ? AND customer_id = ?",
        (normalize_order_id(order_id), customer_id),
    ).fetchone()
