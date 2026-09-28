"""Triage classification and routing."""

import pytest

from app.graph.nodes.triage import classify
from app.graph.routing import choose_route


def route(text: str) -> str:
    r = classify(text)
    return choose_route({"intent": r.intent, "escalation_required": r.escalate})


@pytest.mark.parametrize("text, intent", [
    ("Where is my order #10245?", "ORDER_STATUS"),
    ("wher is my ordr 10245", "ORDER_STATUS"),
    ("Can you give me the tracking number for 10281?", "SHIPMENT_TRACKING"),
    ("I want to return the shoes I bought last week.", "RETURN_REQUEST"),
    ("i want to retrun my jacket", "RETURN_REQUEST"),
    ("My refund still hasn't arrived after 10 days.", "REFUND_STATUS"),
    ("How long do refunds take?", "POLICY_QUESTION"),
    ("What is your return policy?", "POLICY_QUESTION"),
    ("Is my smartwatch covered by warranty?", "WARRANTY"),
    ("I'm really disappointed with the service", "COMPLAINT"),
    ("Do you ship internationally?", "GENERAL_FAQ"),
    ("I want to speak to a manager", "HUMAN_HANDOFF"),
    ("can I talk to a real person", "HUMAN_HANDOFF"),
    ("banana", "UNKNOWN"),
])
def test_intent(text, intent):
    assert classify(text).intent == intent


def test_order_id_extraction():
    assert classify("status of order #10245 please").order_id == "10245"
    assert classify("where's my stuff").order_id is None


def test_bare_order_id_follows_previous_intent():
    assert classify("10260", previous_intent="REFUND_STATUS").intent == "REFUND_STATUS"
    assert classify("10245").intent == "ORDER_STATUS"


@pytest.mark.parametrize("text, sentiment", [
    ("Where is my order?", "NEUTRAL"),
    ("My order is late", "NEGATIVE"),
    ("This is RIDICULOUS, WHERE IS MY ORDER", "ANGRY"),
    ("Thanks, that's great", "POSITIVE"),
])
def test_sentiment(text, sentiment):
    assert classify(text).sentiment == sentiment


@pytest.mark.parametrize("text, expected_route", [
    ("Where is my order #10245?", "order_agent"),
    ("My refund still hasn't arrived", "order_agent"),
    ("I want to return the shoes I bought last week.", "policy_agent"),
    ("What is your exchange policy?", "policy_agent"),
    ("I'm not happy with how this order went", "complaint_agent"),
    ("I want to speak to a manager", "handoff"),
    ("This is the third time my order is late", "handoff"),
    ("Someone made an unauthorized order on my account", "handoff"),
    ("asdfgh", "clarify"),
])
def test_routes(text, expected_route):
    assert route(text) == expected_route


def test_escalation_triggers():
    r = classify("This is the third time my order is late. I want to speak to a manager.")
    assert r.triggers == ["Explicit manager request", "Repeated complaint"]
    assert classify("Where is my order?").triggers == []


# --- small talk and LLM fallback ---------------------------------------------

def test_greetings_and_thanks_do_not_count_as_unclear(agent):
    for msg in ("hi", "Hello!", "thanks", "hey there"):
        s = agent.chat(msg, "st1")
        assert s["intent"] == "SMALL_TALK" and not s["escalation_required"], msg
    assert "You're welcome" in agent.chat("thank you", "st1")["final_response"]


def test_greeting_with_request_is_classified_normally(agent):
    s = agent.chat("hi, where is my order #10245?", "st2")
    assert s["intent"] == "ORDER_STATUS" and "Example Express" in s["final_response"]


class _FailingLLM:
    def __init__(self):
        self.calls = 0

    def with_structured_output(self, schema):
        return self

    async def ainvoke(self, messages):
        self.calls += 1
        raise RuntimeError("429 Too Many Requests")


def test_llm_failure_pauses_llm_and_falls_back(agent):
    llm = _FailingLLM()
    agent.deps.llm = llm
    s1 = agent.chat("Where is my order #10245?", "llm1")
    s2 = agent.chat("What is your return policy?", "llm1")
    assert llm.calls == 1  # second message skipped the LLM during the cooldown
    assert s1["intent"] == "ORDER_STATUS" and s2["intent"] == "POLICY_QUESTION"
