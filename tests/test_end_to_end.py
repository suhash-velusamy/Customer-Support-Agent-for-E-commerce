"""The four sample queries from the specification, plus complaint handling."""

from app.graph.nodes.handoff import render_summary


def test_where_is_my_order(agent):
    s = agent.chat("Where is my order #10245?", "e1")
    text = s["final_response"]
    assert s["route"] == "order_agent"
    for expected in ("#10245", "delayed", "Carrier: Example Express", "Current location: Chennai",
                     "Estimated delivery: September 30", "Policy: Shipping > Delivery times > Delayed shipments"):
        assert expected in text
    assert s["delay_detected"] and not s["escalation_required"]
    assert s["actions_taken"][:3] == ["Order verified", "Order details retrieved", "Shipment status retrieved"]


def test_return_shoes_bought_last_week(agent):
    s = agent.chat("I want to return the shoes I bought last week.", "e2")
    assert s["route"] == "policy_agent"
    assert "Trail Running Shoes" in s["final_response"] and "eligible" in s["final_response"]
    assert "Policy: Returns > Eligibility > 30-day return window" in s["final_response"]
    s = agent.chat("yes", "e2")
    assert "Return ID: RET-5003" in s["final_response"]
    assert "Return created" in s["actions_taken"]


def test_refund_not_arrived(agent):
    s = agent.chat("My refund still hasn't arrived after 10 days.", "e3")
    assert s["intent"] == "REFUND_STATUS" and s["order_data"]["order_id"] == "10260"
    assert "pending" in s["final_response"] and "October 2" in s["final_response"]


def test_third_late_order_manager(agent):
    s = agent.chat("This is the third time my order is late. I want to speak to a manager.", "e4")
    summary = s["handoff_summary"]
    assert s["route"] == "handoff" and s["handed_off"]
    assert summary["issue"] == "Repeated order delays"
    assert summary["customer_intent"] == "Speak with a manager"
    assert summary["order_id"] == "10245"
    assert summary["reason_for_escalation"] == ["Explicit manager request", "Repeated complaint"]
    assert "Retrieved order details" in summary["actions_taken"]
    assert "Checked shipment status" in summary["actions_taken"]
    assert "3 late or delayed orders" in summary["history"]
    assert "manager" in s["final_response"]
    rendered = render_summary(summary)
    for heading in ("Case Summary", "Issue:", "Customer Intent:", "Order:", "History:", "Actions Taken:",
                    "Current Status:", "Reason for Escalation:", "Recommended Next Step:"):
        assert heading in rendered


# --- complaints --------------------------------------------------------------

def test_normal_complaint_attempts_resolution(agent):
    s = agent.chat("I'm not happy, order 10245 is taking forever", "c1")
    assert s["route"] == "complaint_agent" and not s["escalation_required"]
    assert "sorry" in s["final_response"].lower() and "Example Express" in s["final_response"]


def test_repeated_complaint_escalates(agent):
    s = agent.chat("My order is late again, this keeps happening", "c2")
    assert s["escalation_required"] and "Repeated complaint" in s["escalation_reason"]


def test_second_complaint_in_conversation_escalates(agent):
    agent.chat("I'm disappointed with order 10245", "c3")
    s = agent.chat("Still disappointed, this is poor service", "c3")
    assert s["escalation_required"] and "Repeated complaint" in s["escalation_reason"]


def test_explicit_human_request_escalates(agent):
    s = agent.chat("Can I talk to a real person please", "c4")
    assert s["handoff_summary"]["customer_intent"] == "Speak with a human agent"


def test_follow_up_uses_conversation_context(agent):
    agent.chat("Where is my order #10281?", "c5")
    s = agent.chat("can I get the tracking number?", "c5")
    assert s["order_data"]["order_id"] == "10281" and "Tracking number:" in s["final_response"]


def test_policy_question_is_cited(agent):
    s = agent.chat("Can I exchange a jacket for a different size?", "c6")
    assert "Policy: Exchanges" in s["final_response"]
