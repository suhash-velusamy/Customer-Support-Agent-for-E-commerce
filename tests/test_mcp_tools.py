"""Tests for MCP tools: direct function calls plus calls through the MCP protocol."""

import json
from datetime import datetime

import pytest
from mcp import Client

from app.database.db import connect
from app.database.seed import seed
from app.mcp.server import create_server
from app.mcp.tools.get_order import get_order
from app.mcp.tools.initiate_return import initiate_return
from app.mcp.tools.list_customer_orders import list_customer_orders
from app.mcp.tools.track_shipment import track_shipment

ME = "CUST-001"
NOW = datetime(2026, 9, 28, 12, 0)
POLICY = "Policy: Returns > Eligibility > 30-day return window"


# --- get_order ---------------------------------------------------------------

def test_get_order_owned(db):
    r = get_order(db, "10245", ME)
    assert r["ok"] and r["status"] == "delayed" and r["shipment_id"] == "SHP-10245"
    assert r["items"][0]["product_name"] == "Smartwatch Series 3"


@pytest.mark.parametrize("raw", ["#10245", "order 10245", " 10245 "])
def test_get_order_normalizes_id(db, raw):
    assert get_order(db, raw, ME)["ok"]


def test_get_order_other_customer_blocked(db):
    r = get_order(db, "10300", ME)
    assert not r["ok"] and r["error"] == "order_not_verified"
    assert "CUST-002" not in json.dumps(r)


def test_get_order_missing_same_error_as_foreign(db):
    assert get_order(db, "99999", ME)["message"] == get_order(db, "10300", ME)["message"]


def test_get_order_includes_returns_and_refund(db):
    r = get_order(db, "10260", ME)
    assert r["refund_status"] == "pending" and r["returns"][0]["return_id"] == "RET-5001"


# --- track_shipment ----------------------------------------------------------

def test_track_by_order(db):
    r = track_shipment(db, ME, order_id="10245")
    assert r["ok"] and r["carrier"] == "Example Express" and r["location"] == "Chennai"
    assert r["tracking_number"].startswith("EXX")


def test_track_by_shipment_id(db):
    assert track_shipment(db, ME, shipment_id="SHP-10281")["status"] == "in_transit"


def test_track_foreign_shipment_blocked(db):
    for kwargs in ({"order_id": "10300"}, {"shipment_id": "SHP-10300"}):
        r = track_shipment(db, ME, **kwargs)
        assert not r["ok"] and r["error"] == "order_not_verified"


def test_track_processing_order_has_no_shipment(db):
    assert track_shipment(db, ME, order_id="10280")["error"] == "no_shipment"


def test_track_requires_input(db):
    assert track_shipment(db, ME)["error"] == "missing_input"


# --- initiate_return ---------------------------------------------------------

def _return(db, **overrides):
    args = dict(customer_id=ME, order_id="10250", item_ids=["10250-1"], reason="Too small",
                eligibility_confirmed=True, policy_reference=POLICY, now=NOW)
    args.update(overrides)
    return initiate_return(db, **args)


def test_return_created_when_confirmed(db):
    r = _return(db)
    assert r["ok"] and r["returns"][0]["return_id"] == "RET-5003"
    row = db.execute("SELECT status FROM returns WHERE return_id='RET-5003'").fetchone()
    assert row["status"] == "requested"


@pytest.mark.parametrize("overrides", [{"eligibility_confirmed": False}, {"policy_reference": "  "}])
def test_return_blocked_without_policy_confirmation(db, overrides):
    r = _return(db, **overrides)
    assert r["error"] == "eligibility_not_confirmed"
    assert db.execute("SELECT COUNT(*) FROM returns").fetchone()[0] == 2


def test_return_blocked_for_foreign_order(db):
    assert _return(db, order_id="10300", item_ids=["10300-1"])["error"] == "order_not_verified"


def test_return_blocked_for_undelivered_order(db):
    assert _return(db, order_id="10281", item_ids=["10281-1"])["error"] == "not_delivered"


def test_return_blocked_for_item_not_in_order(db):
    assert _return(db, item_ids=["10245-1"])["error"] == "unknown_item"


def test_duplicate_return_blocked(db):
    assert _return(db)["ok"]
    assert _return(db)["error"] == "already_returned"


# --- list_customer_orders ----------------------------------------------------

def test_list_customer_orders_only_own(db):
    orders = list_customer_orders(db, ME)["orders"]
    ids = {o["order_id"] for o in orders}
    assert "10245" in ids and "10300" not in ids
    assert {o["order_id"] for o in orders if o["late"]} == {"10245", "10231", "10238"}


# --- through the MCP protocol ------------------------------------------------

@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def server(tmp_path):
    path = tmp_path / "mcp.db"
    conn = connect(path)
    seed(conn)
    conn.close()
    return create_server(path)


def _payload(result) -> dict:
    if result.structured_content is not None:
        data = result.structured_content
        return data.get("result", data)
    return json.loads(result.content[0].text)


@pytest.mark.anyio
async def test_mcp_lists_three_tools(server):
    async with Client(server) as client:
        names = {t.name for t in (await client.list_tools()).tools}
    assert names == {"get_order", "track_shipment", "initiate_return", "list_customer_orders"}


@pytest.mark.anyio
async def test_mcp_tool_calls(server):
    async with Client(server) as client:
        order = _payload(await client.call_tool("get_order", {"order_id": "10245", "customer_id": ME}))
        ship = _payload(await client.call_tool("track_shipment", {"order_id": "10245", "customer_id": ME}))
        blocked = _payload(await client.call_tool("get_order", {"order_id": "10300", "customer_id": ME}))
        ret = _payload(await client.call_tool("initiate_return", {
            "customer_id": ME, "order_id": "10250", "item_ids": ["10250-1"], "reason": "Too small",
            "eligibility_confirmed": True, "policy_reference": POLICY,
        }))
    assert order["status"] == "delayed"
    assert ship["carrier"] == "Example Express"
    assert blocked["error"] == "order_not_verified"
    assert ret["ok"] and ret["status"] == "requested"
