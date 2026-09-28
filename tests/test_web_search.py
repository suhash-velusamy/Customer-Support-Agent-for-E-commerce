"""Tavily usage: only for courier disruptions and recalls, clearly labelled, never as policy."""

import asyncio

from app.tools.tavily_search import WEB_LABEL, WebSearch

DISRUPTION = {
    "title": "Example Express warns of delivery delays in Chennai after heavy rain",
    "url": "https://news.example.org/example-express-delays",
    "content": "Example Express says deliveries across Chennai are running 2-3 days late due to flooding.",
    "score": 0.82,
    "published_date": "2026-09-26",
}
UNRELATED = {"title": "Stock market update", "url": "https://x.example/m", "content": "Shares rose.", "score": 0.9}
RECALL = {
    "title": "Smartwatch Series 3 battery recall announced",
    "url": "https://safety.example.gov/recalls/123",
    "content": "The manufacturer has issued a voluntary recall of Smartwatch Series 3 units due to battery overheating.",
    "score": 0.77,
}


def test_search_filters_irrelevant_results(fake_web):
    fake_web.results = [DISRUPTION, UNRELATED]
    out = asyncio.run(WebSearch(client=fake_web).carrier_disruptions("Example Express", "Chennai"))
    assert out["ok"] and [r["url"] for r in out["results"]] == [DISRUPTION["url"]]
    assert all(r["source"] == "web" for r in out["results"])


def test_search_unavailable_without_key():
    ws = WebSearch(client=None, api_key="")  # simulate a missing TAVILY_API_KEY
    assert asyncio.run(ws.product_recalls("Lamp"))["error"] == "unavailable"


def test_search_failure_is_contained(fake_web):
    fake_web.fail = True
    assert asyncio.run(WebSearch(client=fake_web).product_recalls("Lamp"))["error"] == "search_failed"


def test_delayed_order_triggers_disruption_search(agent, fake_web):
    fake_web.results = [DISRUPTION]
    s = agent.chat("Where is my order #10245?", "w1")
    assert fake_web.queries and "Example Express" in fake_web.queries[0]
    assert "Carrier disruption search performed" in s["actions_taken"]
    assert s["web_context"][0]["url"] == DISRUPTION["url"]
    text = s["final_response"]
    assert WEB_LABEL in text and "may explain the delay" in text
    # Web info stays separate from the company policy citation.
    assert text.index("Policy: Shipping") < text.index(WEB_LABEL)


def test_delayed_order_without_reports_says_reason_unknown(agent, fake_web):
    s = agent.chat("Where is my order #10245?", "w2")
    assert "don't have a confirmed reason" in s["final_response"] and WEB_LABEL not in s["final_response"]


def test_normal_order_status_does_not_search(agent, fake_web):
    for i, order in enumerate(["10281", "10250", "10280"]):
        agent.chat(f"Where is my order #{order}?", f"w3-{i}")
    assert fake_web.queries == []


def test_policy_question_does_not_search(agent, fake_web):
    agent.chat("What is your return policy?", "w4")
    agent.chat("My refund still hasn't arrived", "w5")
    assert fake_web.queries == []


def test_recall_check_uses_customers_product(agent, fake_web):
    fake_web.results = [RECALL]
    s = agent.chat("Has the smartwatch from order 10245 been recalled?", "w6")
    assert s["intent"] == "PRODUCT_RECALL" and s["route"] == "policy_agent"
    assert "Smartwatch Series 3" in fake_web.queries[0]
    assert WEB_LABEL in s["final_response"] and RECALL["url"] in s["final_response"]
    assert "Policy:" not in s["final_response"]


def test_recall_with_no_reports(agent, fake_web):
    s = agent.chat("is my smartwatch recalled?", "w7")
    assert "didn't find any reports" in s["final_response"] and "isn't a guarantee" in s["final_response"]


def test_recall_for_other_customers_order_not_searched(agent, fake_web):
    s = agent.chat("Was the product in order 10300 recalled?", "w8")
    assert fake_web.queries == [] and "Which product" in s["final_response"]
