"""Web UI API: chat flow, activity events, handoff panel data, and no raw data leakage."""

import pytest
from fastapi.testclient import TestClient

from app.web.server import create_app


@pytest.fixture
def client(agent):
    return TestClient(create_app(agent))


def _chat(client, message, session_id="web-1"):
    r = client.post("/api/chat", json={"message": message, "session_id": session_id})
    assert r.status_code == 200
    return r.json()


def test_index_served(client):
    r = client.get("/")
    assert r.status_code == 200 and "Customer chat" in r.text and "Tool activity" in r.text


def test_session_info(client):
    s = client.get("/api/session").json()
    assert s["customer_id"] == "CUST-001" and s["session_id"]


def test_order_status_with_activity(client):
    d = _chat(client, "Where is my order #10245?")
    assert "Example Express" in d["reply"]
    assert d["activity"][:3] == ["Order verified", "Order details retrieved", "Shipment status retrieved"]
    assert d["context"] == {"customer_id": "CUST-001", "order_id": "10245", "order_status": "delayed"}
    assert d["handoff"] is None


def test_activity_is_per_turn(client):
    _chat(client, "Where is my order #10245?")
    d = _chat(client, "What is your return policy?")
    assert d["activity"] == ["Policy searched"]


def test_handoff_panel_data(client):
    d = _chat(client, "This is the third time my order is late. I want to speak to a manager.", "web-2")
    assert d["handed_off"] and d["escalated_now"]
    summary = d["handoff"]["summary"]
    assert summary["reason_for_escalation"] == ["Explicit manager request", "Repeated complaint"]
    assert d["handoff"]["text"].startswith("Case Summary")


def test_no_raw_data_or_other_customer_leak(client):
    d = _chat(client, "Where is order #10300?", "web-3")
    body = str(d)
    assert "couldn't verify" in d["reply"]
    for leaked in ("CUST-002", "Mumbai", "FedEx", "tracking_number", "order_data", "messages"):
        assert leaked not in body


def test_input_validation(client):
    assert client.post("/api/chat", json={"message": ""}).status_code == 422
    assert client.post("/api/chat", json={"message": "x" * 2001}).status_code == 422
    assert client.post("/api/chat", json={"message": "   "}).status_code == 422
