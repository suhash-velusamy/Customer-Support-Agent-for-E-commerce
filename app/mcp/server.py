"""MCP server exposing get_order, track_shipment and initiate_return.

Run over stdio:  python -m app.mcp.server

Every tool takes the authenticated customer_id; the tools only return data for
orders owned by that customer.
"""

from pathlib import Path

from mcp.server.mcpserver import MCPServer

from app.database.db import get_connection
from app.mcp.tools.get_order import get_order as _get_order
from app.mcp.tools.initiate_return import initiate_return as _initiate_return
from app.mcp.tools.list_customer_orders import list_customer_orders as _list_customer_orders
from app.mcp.tools.track_shipment import track_shipment as _track_shipment


def create_server(db_path: Path | str | None = None) -> MCPServer:
    mcp = MCPServer("ecommerce-support")

    @mcp.tool()
    def get_order(order_id: str, customer_id: str) -> dict:
        """Retrieve an order's details, items, payment/refund status and returns.
        Only returns data if the order belongs to customer_id."""
        with get_connection(db_path) as conn:
            return _get_order(conn, order_id, customer_id)

    @mcp.tool()
    def track_shipment(customer_id: str, order_id: str | None = None, shipment_id: str | None = None) -> dict:
        """Retrieve carrier, tracking number, status, location and ETA for an order's shipment.
        Only returns data if the shipment belongs to customer_id."""
        with get_connection(db_path) as conn:
            return _track_shipment(conn, customer_id, order_id=order_id, shipment_id=shipment_id)

    @mcp.tool()
    def initiate_return(
        customer_id: str,
        order_id: str,
        item_ids: list[str],
        reason: str,
        eligibility_confirmed: bool,
        policy_reference: str,
    ) -> dict:
        """Create a return request. Requires prior policy eligibility confirmation and the
        policy citation used. Refuses otherwise."""
        with get_connection(db_path) as conn:
            return _initiate_return(
                conn, customer_id, order_id, item_ids, reason, eligibility_confirmed, policy_reference
            )

    @mcp.tool()
    def list_customer_orders(customer_id: str, limit: int = 20) -> dict:
        """List customer_id's own recent orders (items, status, delivery and late flag), newest first."""
        with get_connection(db_path) as conn:
            return _list_customer_orders(conn, customer_id, limit)

    return mcp


if __name__ == "__main__":
    create_server().run()
