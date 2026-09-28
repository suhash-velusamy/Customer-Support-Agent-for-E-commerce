"""Return eligibility and the confirm-then-create workflow."""

from datetime import date

import pytest

from app.graph.eligibility import check_return_eligibility, gather_return_policy
from app.rag.retriever import search_policy

TODAY = date(2026, 9, 28)


@pytest.fixture(scope="module")
def policy():
    return gather_return_policy(search_policy)


def _order(status="delivered", delivered_at="2026-09-25", returns=()):
    return {"status": status, "delivered_at": delivered_at, "returns": list(returns)}


def _item(category="footwear", item_id="X-1"):
    return {"item_id": item_id, "category": category, "product_name": "Thing"}


def test_eligible_within_window(policy):
    r = check_return_eligibility(_order(), _item(), policy, TODAY)
    assert r.eligible is True
    assert "Policy: Returns > Eligibility > 30-day return window" in r.citations


def test_outside_window(policy):
    r = check_return_eligibility(_order(delivered_at="2026-07-30"), _item(), policy, TODAY)
    assert r.eligible is False and "30-day" in r.reason


def test_electronics_shorter_window_from_policy(policy):
    r = check_return_eligibility(_order(delivered_at="2026-09-08"), _item("electronics"), policy, TODAY)
    assert r.eligible is False and "15-day" in r.reason


@pytest.mark.parametrize("category", ["swimwear", "gift_card", "personal_care"])
def test_non_returnable(policy, category):
    r = check_return_eligibility(_order(), _item(category), policy, TODAY)
    assert r.eligible is False
    assert r.citations == ["Policy: Returns > Non-returnable items > Non-returnable product categories"]


def test_not_delivered(policy):
    assert check_return_eligibility(_order(status="shipped", delivered_at=None), _item(), policy, TODAY).eligible is False


def test_already_returned(policy):
    order = _order(returns=[{"item_id": "X-1", "status": "requested"}])
    assert check_return_eligibility(order, _item(), policy, TODAY).eligible is False


def test_missing_policy_evidence_is_not_eligible():
    r = check_return_eligibility(_order(), _item(), [], TODAY)
    assert r.eligible is None and "No policy evidence" in r.reason


# --- through the graph -------------------------------------------------------

def _returns_count(db):
    return db.execute("SELECT COUNT(*) FROM returns").fetchone()[0]


def test_eligible_return_requires_confirmation(agent, db):
    s = agent.chat("I want to return the shoes I bought last week.", "r1")
    assert s["return_eligible"] is True and s["pending_return"]["order_id"] == "10250"
    assert _returns_count(db) == 2  # nothing created yet
    s = agent.chat("yes please", "r1")
    assert s["return_result"]["ok"] and "RET-5003" in s["final_response"]
    assert _returns_count(db) == 3


def test_declining_does_not_create(agent, db):
    agent.chat("I want to return the shoes I bought last week.", "r2")
    s = agent.chat("no thanks", "r2")
    assert s["pending_return"] is None and _returns_count(db) == 2


def test_ineligible_return_blocked(agent, db):
    s = agent.chat("I want to return my order 10270", "r3")
    assert s["return_eligible"] is False and "30-day" in s["final_response"]
    s = agent.chat("yes", "r3")
    assert _returns_count(db) == 2


def test_non_returnable_item_blocked(agent, db):
    s = agent.chat("I want to return the swimsuit from order 10271", "r4")
    assert s["return_eligible"] is False and "non-returnable" in s["final_response"]
    assert "Policy: Returns > Non-returnable items" in s["final_response"]


def test_missing_policy_evidence_blocks_return_and_escalates(db_path, db):
    from app.graph.graph import SupportAgent

    agent = SupportAgent(db_path=db_path, use_llm=False, search_policy=lambda q, k=3: [])
    s = agent.chat("I want to return the shoes I bought last week.", "r5")
    assert s["return_eligible"] is None and s["escalation_required"]
    assert any("Policy ambiguity" in r for r in s["escalation_reason"])
    assert _returns_count(db) == 2


def test_confirm_without_pending_return_does_nothing(agent, db):
    s = agent.chat("yes", "r6")
    assert s.get("return_result") is None and _returns_count(db) == 2


def test_ambiguous_return_asks_which_order(agent):
    s = agent.chat("I want to return my shoes", "r7")
    assert "#10250" in s["final_response"] and "#10270" in s["final_response"]
    assert s.get("pending_return") is None
