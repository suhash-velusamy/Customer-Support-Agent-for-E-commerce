"""Output guardrail: last check on every customer-facing reply before it is sent.

The specialist nodes already build replies only from verified data, so this should never
fire in normal operation. It is defence in depth against regressions and future
LLM-generated text: it blocks replies that leak another customer's identifiers, any email
address, internal instructions, or promises the policy doesn't allow.
"""

import re
from dataclasses import dataclass

SAFE_FALLBACK = ("I'm sorry, I can't share that. A support specialist can help with this request if you'd "
                 "like me to connect you.")

EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
CUSTOMER_ID = re.compile(r"\bCUST-\d{3,}\b")
INTERNALS = re.compile(r"(system prompt|LLM_PROMPT|You classify e-commerce|OPENROUTER_API_KEY|TAVILY_API_KEY"
                       r"|api[_ ]key)", re.IGNORECASE)
PROMISES = re.compile(
    r"(\b(I|we) (promise|guarantee)\b"
    r"|\byour refund will (arrive|be (in|on) your account) (on|by)\b"
    r"|\b(we will|we'll|I will|I'll) (give|send|offer) you (a |an )?(full refund|compensation|voucher|discount"
    r"|store credit|free)"
    r"|\b(compensation|goodwill payment|discount code) (has been|is) (approved|issued|applied))",
    re.IGNORECASE,
)


@dataclass
class GuardResult:
    text: str
    violations: list[str]

    @property
    def blocked(self) -> bool:
        return bool(self.violations)


def check_output(text: str, customer_id: str | None) -> GuardResult:
    violations = []
    if any(cid != customer_id for cid in CUSTOMER_ID.findall(text)):
        violations.append("other customer identifier")
    if EMAIL.search(text):
        violations.append("email address")
    if INTERNALS.search(text):
        violations.append("internal instructions or secrets")
    if PROMISES.search(text):
        violations.append("unsupported promise")
    return GuardResult(SAFE_FALLBACK if violations else text, violations)
