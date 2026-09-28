"""Triage Router: intent, sentiment, escalation triggers and entity extraction.

Rules are always applied (they are deterministic and enforce the mandatory escalation
triggers). When an LLM is configured it refines intent/sentiment for phrasings the
rules don't cover; it can never remove an escalation trigger.
"""

import difflib
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel

from app.graph.deps import Deps
from app.graph.routing import choose_route

INTENTS = (
    "ORDER_STATUS", "SHIPMENT_TRACKING", "RETURN_REQUEST", "REFUND_STATUS", "POLICY_QUESTION",
    "WARRANTY", "COMPLAINT", "GENERAL_FAQ", "PRODUCT_RECALL", "HUMAN_HANDOFF", "UNKNOWN",
)
SENTIMENT_RANK = {"POSITIVE": 0, "NEUTRAL": 1, "NEGATIVE": 2, "ANGRY": 3}

HANDED_OFF_REPLY = (
    "Your case has already been passed to a human support specialist, who will follow up with you. "
    "They have the full case summary, so there's no need to repeat anything."
)
logger = logging.getLogger(__name__)

GREETING_REPLY = ("Hi! I can help with order status and tracking, returns, refunds, exchanges, warranty and our "
                  "store policies. What can I do for you? If it's about an order, include the order number.")
THANKS_REPLY = "You're welcome! Is there anything else I can help with?"
# Whole-message greetings/thanks only, so "hi, where is my order?" is still classified normally.
SMALL_TALK = re.compile(
    r"^\s*(hi+|hello|hey+|hiya|good (morning|afternoon|evening)|thanks|thank you( so much)?|thx|cheers|ok(ay)?"
    r"|cool|great)( there)?[\s!.,:)]*$", re.IGNORECASE)
RETURN_CANCELLED_REPLY = "No problem, I haven't created a return. Is there anything else I can help with?"


def _rx(pattern: str) -> re.Pattern:
    return re.compile(pattern, re.IGNORECASE)


MANAGER = _rx(r"\b(manager|supervisor)\b")
HUMAN = _rx(r"\b(human|real person|a person|live agent|an agent|representative|someone real|talk to someone"
            r"|speak to someone|customer service rep)\b")
FRAUD = _rx(r"\b(fraud\w*|hack(ed)?|unauthori[sz]ed|stolen|scam(med)?|chargeback|identity theft"
            r"|someone else (used|ordered|accessed)|didn'?t (place|make) this order)\b")
SENSITIVE = _rx(r"\b(lawyer|attorney|sue|suing|lawsuit|legal action|court|consumer (court|forum)|injur(ed|y|ies)"
                r"|hurt|burn(ed|t)?|caught fire|on fire|exploded|electric shock|hospital|allergic reaction"
                r"|harass\w*|discriminat\w*|bereavement|passed away|died)\b")
COMPENSATION = _rx(r"\b(compensat\w*|refund me (now|immediately)|full refund (now|immediately)|free (item|product)"
                   r"|discount code|voucher|store credit|goodwill|money back now)\b")
INJECTION = _rx(r"(ignore (all |your |the )?(previous |prior )?instructions|system prompt|your (instructions|prompt)"
                r"|developer mode|reveal (your )?prompt)")
REPEATED = _rx(r"\b((second|third|fourth|fifth|\d+(st|nd|rd|th)) time|again|keeps? (happening|being late)"
               r"|every (single )?time|repeatedly|multiple times|how many times|yet another)\b")
ANGRY = _rx(r"(furious|ridiculous|unacceptable|worst|outrageous|disgusting|pathetic|useless|\bangry\b|livid"
            r"|fed up|sick of|!{2,}|\bwtf\b)")
NEGATIVE = _rx(r"(late|delay|still (not|hasn'?t|haven'?t)|hasn'?t (arrived|come)|not (happy|received|arrived)"
               r"|never (arrived|came)|disappoint|frustrat|annoy|terrible|\bbad\b|\bpoor\b|problem|issue|wrong"
               r"|broken|damaged|missing|upset)")
POSITIVE = _rx(r"\b(thank|thanks|great|awesome|love|perfect|appreciate)")
COMPLAINT = _rx(r"(complain|unhappy|disappointed|terrible service|unacceptable|not happy|fed up|worst|poor service"
                r"|very bad|so bad|awful)")

CONFIRM = _rx(r"^\s*(yes|yeah|yep|sure|ok(ay)?|please do|go ahead|confirm|do it|please)\b")
DENY = _rx(r"^\s*(no|nope|don'?t|cancel|never ?mind|not now)\b")

ORDER_ID = re.compile(r"#?\b(\d{5})\b")
DAMAGED = _rx(r"\b(damaged|broken|cracked|defective|smashed|torn)\b")
RECENT = _rx(r"\b(last week|this week|few days ago|recently|yesterday|days ago)\b")
REASON = _rx(r"(because [^.!?]+|too (small|big|large|tight|loose|short|long)|doesn'?t fit|wrong size"
             r"|changed my mind|not as described|didn'?t like)")

CATEGORY_WORDS = {
    "footwear": ["shoe", "shoes", "sneaker", "sneakers", "trainers", "boots", "footwear"],
    "electronics": ["earbuds", "headphones", "smartwatch", "watch", "charger", "electronics"],
    "apparel": ["shirt", "t-shirt", "tshirt", "jacket", "denim", "clothes"],
    "swimwear": ["swimsuit", "swimwear", "bikini"],
    "home": ["mug", "mugs", "lamp"],
    "gift_card": ["gift card", "giftcard"],
    "personal_care": ["serum", "cream", "skincare"],
    "baby": ["stroller", "pram"],
}

# Words worth correcting when misspelled ("retrun", "ordr", "refnd").
VOCAB = [
    "return", "refund", "order", "where", "track", "tracking", "shipment", "shipping", "delivery", "delivered",
    "manager", "supervisor", "human", "warranty", "exchange", "policy", "complaint", "late", "delayed",
    "package", "status", "cancel", "damaged", "broken", "arrived", "received",
]


def _fix_spelling(text: str) -> str:
    def fix(match: re.Match) -> str:
        word = match.group(0)
        lower = word.lower()
        if len(lower) < 4 or lower in VOCAB:
            return word
        close = difflib.get_close_matches(lower, VOCAB, n=1, cutoff=0.8)
        return close[0] if close and abs(len(close[0]) - len(lower)) <= 1 else word

    return re.sub(r"[A-Za-z]+", fix, text)


@dataclass
class TriageResult:
    intent: str
    sentiment: str
    order_id: str | None
    triggers: list[str] = field(default_factory=list)
    entities: dict = field(default_factory=dict)

    @property
    def escalate(self) -> bool:
        return bool(self.triggers)


def _sentiment(text: str) -> str:
    shouting = len(re.findall(r"\b[A-Z]{3,}\b", text)) >= 2
    if ANGRY.search(text) or shouting:
        return "ANGRY"
    if NEGATIVE.search(text) or REPEATED.search(text):
        return "NEGATIVE"
    if POSITIVE.search(text):
        return "POSITIVE"
    return "NEUTRAL"


def _intent(text: str, order_id: str | None, previous_intent: str | None) -> str:
    personal = re.search(r"\b(my|i bought|i ordered|i got|i want|i'd like|i need|i would like)\b", text, re.I)
    if MANAGER.search(text) or HUMAN.search(text):
        return "HUMAN_HANDOFF"
    if re.search(r"\brecall", text, re.I):
        return "PRODUCT_RECALL"
    if re.search(r"\b(return|send (it|them|this)? ?back)\b", text, re.I) and personal \
            and not re.search(r"\bpolicy\b", text, re.I):
        return "RETURN_REQUEST"
    if re.search(r"\b(warranty|guarantee|stopped working|not working|defect)", text, re.I):
        return "WARRANTY"
    if re.search(r"\brefund", text, re.I):
        if re.search(r"\b(my|status|still|where|hasn'?t|haven'?t|when will|received|arrived)\b", text, re.I) \
                and not re.search(r"\bhow long\b", text, re.I):
            return "REFUND_STATUS"
        return "POLICY_QUESTION"
    if REPEATED.search(text) or COMPLAINT.search(text):
        return "COMPLAINT"
    if re.search(r"\b(policy|policies|return|exchange|non-returnable)\b", text, re.I):
        return "POLICY_QUESTION"
    if re.search(r"\b(track|tracking|carrier|courier)\b", text, re.I):
        return "SHIPMENT_TRACKING"
    if re.search(r"\b(where|status|order|package|parcel|deliver|shipped|arrive|late|delayed)\b", text, re.I) \
            and (order_id or re.search(r"\b(my|where)\b", text, re.I)):
        return "ORDER_STATUS"
    if re.search(r"\b(ship|shipping|cancel|how do i|can i|do you|how long)\b", text, re.I):
        return "GENERAL_FAQ"
    if order_id:
        # A bare order number is a follow-up to whatever we were discussing.
        return previous_intent if previous_intent in ("ORDER_STATUS", "SHIPMENT_TRACKING", "REFUND_STATUS",
                                                      "RETURN_REQUEST", "COMPLAINT") else "ORDER_STATUS"
    return "UNKNOWN"


def classify(raw_text: str, previous_intent: str | None = None) -> TriageResult:
    text = _fix_spelling(raw_text)
    id_match = ORDER_ID.search(text)
    order_id = id_match.group(1) if id_match else None
    sentiment = _sentiment(raw_text)
    intent = _intent(text, order_id, previous_intent)
    repeated = bool(REPEATED.search(text))

    item_hint = next((cat for cat, words in CATEGORY_WORDS.items()
                      if any(re.search(rf"\b{re.escape(w)}\b", text, re.I) for w in words)), None)
    reason = REASON.search(text)
    entities = {
        "item_hint": item_hint,
        "recent": bool(RECENT.search(text)),
        "reason": reason.group(0).strip() if reason else None,
        "damaged": bool(DAMAGED.search(text)),
        "repeated": repeated,
        "injection": bool(INJECTION.search(text)),
        "text": text,
    }

    triggers = []
    if MANAGER.search(text):
        triggers.append("Explicit manager request")
    elif HUMAN.search(text):
        triggers.append("Explicit request for human support")
    if repeated and sentiment in ("NEGATIVE", "ANGRY"):
        triggers.append("Repeated complaint")
    if sentiment == "ANGRY":
        triggers.append("Strong negative/angry sentiment")
    if FRAUD.search(text):
        triggers.append("Potential fraud/security issue")
    if SENSITIVE.search(text):
        triggers.append("Sensitive case (legal, safety or personal circumstances)")
    if COMPENSATION.search(text):
        triggers.append("Compensation request requires human approval")
    return TriageResult(intent, sentiment, order_id, triggers, entities)


class _LLMTriage(BaseModel):
    intent: Literal[INTENTS]  # type: ignore[valid-type]
    sentiment: Literal["POSITIVE", "NEUTRAL", "NEGATIVE", "ANGRY"]


LLM_PROMPT = (
    "You classify e-commerce customer support messages. Intents: "
    "ORDER_STATUS (where is my order), SHIPMENT_TRACKING (tracking/carrier details), RETURN_REQUEST (customer "
    "wants to return an item they bought), REFUND_STATUS (status of their own refund), POLICY_QUESTION (general "
    "questions about returns/refunds/exchanges/shipping rules), WARRANTY, COMPLAINT (dissatisfaction), "
    "GENERAL_FAQ, PRODUCT_RECALL (asks whether a product has been recalled), HUMAN_HANDOFF (asks for a human/manager), UNKNOWN. Classify only; do not answer."
)


LLM_COOLDOWN_SECONDS = 300


async def _llm_refine(deps: Deps, text: str, result: TriageResult) -> None:
    # After a failure (rate limit, exhausted key, outage) skip the LLM for a while instead of
    # making every customer message wait through retries.
    if time.monotonic() < deps.extra.get("llm_paused_until", 0):
        return
    try:
        out = await deps.llm.with_structured_output(_LLMTriage).ainvoke(
            [SystemMessage(LLM_PROMPT), HumanMessage(text)]
        )
    except Exception as exc:  # noqa: BLE001 - fall back to rules if the LLM call fails
        deps.extra["llm_paused_until"] = time.monotonic() + LLM_COOLDOWN_SECONDS
        # Log the error type only; never the customer's message.
        logger.warning("LLM triage unavailable (%s); using rules only for the next %d minutes.",
                       type(exc).__name__, LLM_COOLDOWN_SECONDS // 60)
        return
    if result.intent != "HUMAN_HANDOFF":
        result.intent = out.intent
    if SENTIMENT_RANK[out.sentiment] > SENTIMENT_RANK[result.sentiment]:
        result.sentiment = out.sentiment
    if out.intent == "HUMAN_HANDOFF" and not result.triggers:
        result.triggers.append("Explicit request for human support")


# Fields reset at the start of every turn.
TURN_DEFAULTS = {
    "escalation_required": False,
    "escalation_reason": [],
    "order_data": None,
    "shipment_data": None,
    "policy_context": [],
    "web_context": [],
    "delay_detected": False,
    "return_eligible": None,
    "return_result": None,
    "final_response": None,
    "handoff_summary": None,
    "guardrail_violations": [],
}


def make_triage_node(deps: Deps):
    async def triage(state: dict) -> dict:
        text = state["messages"][-1].content
        update: dict = dict(TURN_DEFAULTS)
        update.setdefault("actions_taken", state.get("actions_taken", []))

        if state.get("handed_off"):
            return {**update, "intent": "HUMAN_HANDOFF", "route": "respond", "final_response": HANDED_OFF_REPLY}

        pending = state.get("pending_return")
        if pending and CONFIRM.search(text):
            return {**update, "intent": "CONFIRM_RETURN", "sentiment": "NEUTRAL", "route": "order_agent",
                    "return_eligible": True, "entities": {}}
        if pending and DENY.search(text):
            return {**update, "intent": "CANCEL_RETURN", "route": "respond", "pending_return": None,
                    "final_response": RETURN_CANCELLED_REPLY, "entities": {}}

        small_talk = SMALL_TALK.match(text)
        if small_talk:
            reply = THANKS_REPLY if re.match(r"\s*(thanks|thank you|thx|cheers)", text, re.I) else GREETING_REPLY
            return {**update, "intent": "SMALL_TALK", "sentiment": "POSITIVE", "route": "respond",
                    "final_response": reply, "entities": {}}

        result = classify(text, state.get("intent"))
        if deps.llm is not None:
            await _llm_refine(deps, text, result)

        update.update(
            intent=result.intent,
            sentiment=result.sentiment,
            entities=result.entities,
            escalation_required=result.escalate,
            escalation_reason=list(result.triggers),
            pending_return=None,
            order_id=result.order_id or state.get("order_id"),
            complaint_count=state.get("complaint_count", 0) + (result.intent == "COMPLAINT"),
            unknown_count=state.get("unknown_count", 0) + 1 if result.intent == "UNKNOWN" else 0,
        )
        update["route"] = choose_route({**state, **update})
        return update

    return triage
