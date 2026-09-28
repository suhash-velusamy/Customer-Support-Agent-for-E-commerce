# CLAUDE.md — Customer Support Agent

## Project Title

**Customer Support Agent for E-commerce**

## Project Goal

Build a production-style, locally runnable customer-support AI agent that can resolve routine e-commerce support requests end-to-end and hand complex, sensitive, or repeatedly unresolved cases to a human with a structured summary.

The implementation must be functional, testable, and easy to demonstrate. Do not build only a mock UI or a static chatbot. The agent must actually use:

- **LangGraph** for orchestration
- **MCP tools** for order/shipment/return operations
- **RAG** for company policies and FAQs
- **Tavily Web Search** for courier disruptions and product recall notices
- **SQLite** for seeded mock order data
- A clear **human handoff** path

---

# 1. Background

Online retailers receive large volumes of repetitive support questions such as:

- Order status
- Shipment tracking
- Returns
- Refunds
- Exchanges
- Warranty questions

Human support agents are expensive and customers dislike waiting. However, complex complaints, repeated failures, angry customers, sensitive cases, and explicit requests for human assistance should still be escalated.

The system should automate routine requests while keeping strict safety and privacy boundaries.

---

# 2. Core Objective

Build a support agent that:

1. Understands the customer's intent.
2. Detects sentiment and escalation triggers.
3. Retrieves only the order information required to answer the request.
4. Uses company policy through RAG before making policy-related decisions.
5. Uses MCP tools for operational actions.
6. Uses web search only when external information is required.
7. Confirms return eligibility before creating a return.
8. Produces a clear answer for resolved requests.
9. Produces a structured case summary for human agents when escalation is required.
10. Never exposes another customer's data.
11. Never promises actions that violate company policy.

---

# 3. Target Users

### Primary
- Online shoppers

### Secondary
- Customer support teams / human support agents

---

# 4. Example User Queries

The system must support examples such as:

> Where is my order #10245?

> I want to return the shoes I bought last week.

> My refund still hasn't arrived after 10 days.

> This is the third time my order is late. I want to speak to a manager.

Also support natural variations, spelling mistakes, incomplete questions, and conversational follow-ups.

---

# 5. Required System Components

## 5.1 MCP Server

Create an MCP server exposing these tools.

### `get_order`

**Purpose:** Retrieve order details.

Input:
- `order_id`

Return:
- Order ID
- Customer ID
- Order date
- Items
- Item quantities
- Total amount
- Order status
- Shipment ID if available
- Payment/refund status
- Return status if applicable

Do not expose unrelated customer information.

---

### `track_shipment`

**Purpose:** Retrieve shipment information.

Input:
- `order_id` or `shipment_id`

Return:
- Carrier
- Tracking number
- Current shipment status
- Current location
- Estimated delivery date
- Last update timestamp

---

### `initiate_return`

**Purpose:** Create a return request.

Input:
- `order_id`
- Item identifier(s)
- Return reason

The tool must NOT blindly create a return.

The LangGraph workflow must verify eligibility through the Policy Agent/RAG layer first.

Return:
- Return ID
- Confirmation status
- Next steps
- Expected processing information

---

# 6. Database

Use a seeded **SQLite** database.

Create approximately **50–100 mock orders**.

Suggested tables:

### `customers`
- `customer_id`
- `name`
- `email`

### `orders`
- `order_id`
- `customer_id`
- `order_date`
- `status`
- `total_amount`
- `shipment_id`
- `payment_status`
- `refund_status`

### `order_items`
- `item_id`
- `order_id`
- `product_id`
- `product_name`
- `quantity`
- `price`

### `shipments`
- `shipment_id`
- `order_id`
- `carrier`
- `tracking_number`
- `status`
- `location`
- `estimated_delivery`

### `returns`
- `return_id`
- `order_id`
- `item_id`
- `reason`
- `status`
- `created_at`

Seed realistic scenarios including:

- Delivered orders
- Processing orders
- Shipped orders
- Delayed orders
- Cancelled orders
- Eligible returns
- Ineligible returns
- Pending refunds
- Completed refunds
- Multiple delayed orders for the same customer

Use deterministic seed data so tests remain reproducible.

---

# 7. RAG Knowledge Base

Create a local knowledge base containing a sample e-commerce policy document.

The knowledge base must cover:

- Return policy
- Refund policy
- Exchange policy
- Warranty policy
- Return windows
- Non-returnable products
- Damaged item rules
- Refund processing times
- Shipping policies
- FAQs

The Policy Agent must retrieve relevant policy sections before answering policy-related questions.

Every policy-sensitive answer should include a concise policy reference/citation such as:

`Policy: Returns > Eligibility > 30-day return window`

Do not invent policy rules.

---

# 8. Tavily Web Search

Use Tavily for external information when appropriate.

Primary use cases:

1. Courier service disruptions
2. Product recall notices

Example:

If an order is delayed and the carrier has a known disruption, search for current carrier disruption information.

If a customer asks whether a product has been recalled, search for current recall notices.

### Important

Do not use web search for information already available in the local order database or policy knowledge base.

Clearly distinguish external web information from company policy.

---

# 9. LangGraph Agent Architecture

Implement the system as a LangGraph state machine.

## Required Nodes

### 9.1 Triage Router

Responsibilities:

- Classify intent
- Detect sentiment
- Detect escalation triggers
- Extract order ID if present
- Determine which specialist agent should handle the request

Suggested intent categories:

```text
ORDER_STATUS
SHIPMENT_TRACKING
RETURN_REQUEST
REFUND_STATUS
POLICY_QUESTION
WARRANTY
COMPLAINT
GENERAL_FAQ
HUMAN_HANDOFF
UNKNOWN
```

Suggested sentiment:

```text
POSITIVE
NEUTRAL
NEGATIVE
ANGRY
```

Escalation triggers include:

- Explicit request for human support
- Request for manager/supervisor
- Repeated complaint
- Strong negative/angry sentiment
- Sensitive case
- Agent unable to resolve the issue
- Tool failure after reasonable retry
- Policy ambiguity
- Potential fraud/security issue

---

### 9.2 Order Agent

Responsibilities:

- Handle order and shipment questions
- Use MCP tools
- Retrieve order data
- Track shipment
- Explain current status
- Identify relevant delays

The Order Agent must never invent order information.

---

### 9.3 Policy Agent

Responsibilities:

- Answer policy questions
- Search the RAG knowledge base
- Determine return eligibility
- Determine whether an operation is permitted

The Policy Agent must confirm eligibility before `initiate_return` is called.

---

### 9.4 Complaint Agent

Responsibilities:

- Respond respectfully to dissatisfied customers
- Acknowledge the issue
- Review available order information
- Attempt reasonable resolution
- Detect repeated complaints
- Escalate when required

Do not make emotional or financial promises that are unsupported by policy.

---

### 9.5 Human Handoff Node

Responsibilities:

- Stop automated resolution
- Produce a structured case summary
- Preserve useful conversation context
- Explain why escalation occurred

Required handoff format:

```text
Case Summary

Issue:
Customer's main problem.

Customer Intent:
What the customer wants.

Order:
Order ID and relevant order status.

History:
Relevant previous issues or repeated complaints.

Actions Taken:
Tools used, policy checks performed, searches performed.

Current Status:
What is currently known.

Reason for Escalation:
Why human intervention is required.

Recommended Next Step:
What the human support agent should review.
```

Do not include unnecessary personal information.

---

# 10. Orchestration Flow

The general flow should be:

```text
User Message
     |
     v
Triage Router
     |
     +---- Order/Shipment ------> Order Agent
     |
     +---- Policy/Return --------> Policy Agent
     |
     +---- Complaint ------------> Complaint Agent
     |
     +---- Human Request --------> Human Handoff
     |
     +---- Unknown --------------> Clarification / Human Handoff
```

Additional routing rules:

- Negative sentiment + repeated complaint → Human Handoff
- Explicit human/manager request → Human Handoff
- Return request → Policy Agent first
- Policy Agent confirms eligibility → Order Agent/MCP `initiate_return`
- Shipment delay → Order Agent, optionally Tavily for external disruption
- Product recall → Tavily search
- Refund status → Order Agent + policy context if required

The graph must retain structured state across nodes.

---

# 11. State Design

Create a typed LangGraph state.

Suggested fields:

```python
class SupportState(TypedDict):
    messages: list
    customer_id: str | None
    order_id: str | None
    intent: str | None
    sentiment: str | None
    escalation_required: bool
    escalation_reason: str | None
    order_data: dict | None
    shipment_data: dict | None
    policy_context: list
    web_context: list
    actions_taken: list
    return_eligible: bool | None
    return_result: dict | None
    final_response: str | None
    handoff_summary: dict | None
```

Adapt the exact schema if necessary, but keep state explicit and inspectable.

---

# 12. Order Ownership / Privacy Guardrail

This is mandatory.

Before sharing order details, verify that the order belongs to the authenticated/customer context.

For the demo, use a mock customer identity such as:

```text
customer_id = CUST-001
```

If a user asks:

> Where is order #10245?

the system must verify that order `10245` belongs to the current customer before returning details.

If ownership cannot be verified:

```text
I can't provide details for that order because I couldn't verify that it belongs to your account.
```

Never reveal another customer's:

- Name
- Email
- Address
- Order details
- Tracking number
- Payment information
- Return information

---

# 13. Return Workflow

Example:

```text
Customer:
"I want to return the shoes I bought last week."

        |
        v
Triage Router
        |
        v
Policy Agent
        |
        +--> Retrieve return policy
        |
        +--> Identify order/item
        |
        +--> Check return window
        |
        +--> Check item eligibility
        |
        v
Eligible?
   |          |
  Yes         No
   |          |
   v          v
Confirm      Explain policy
return       and reason
   |
   v
MCP initiate_return
   |
   v
Return confirmation
```

Never call `initiate_return` before eligibility is confirmed.

---

# 14. Refund Workflow

For:

> My refund hasn't arrived after 10 days.

The agent should:

1. Verify the relevant order.
2. Retrieve refund status.
3. Check applicable refund policy.
4. Explain the current state.
5. If the refund is outside the policy processing window, escalate or provide the appropriate next step.
6. Never promise an exact refund date unless the data supports it.

---

# 15. Shipment Delay Workflow

For a delayed order:

1. Verify order ownership.
2. Retrieve order.
3. Retrieve shipment.
4. Compare expected delivery with current status.
5. Optionally use Tavily to check carrier disruptions.
6. Explain the known reason if reliable information exists.
7. Escalate repeated or serious complaints.

---

# 16. Response Requirements

Normal responses should be:

- Concise
- Clear
- Customer-friendly
- Grounded in retrieved data
- Transparent about uncertainty

Example:

```text
Your order #10245 is currently in transit.

Carrier: Example Express
Current location: Chennai
Estimated delivery: September 30

The carrier is currently reporting a regional delivery disruption, which may explain the delay.
```

Do not fabricate details.

---

# 17. Human Handoff Requirements

Example user:

> This is the third time my order is late. I want to speak to a manager.

The agent should not continue trying to solve the issue automatically.

It should create a structured handoff:

```json
{
  "issue": "Repeated order delays",
  "customer_intent": "Speak with a manager",
  "order_id": "10245",
  "history": "Customer reports this is the third late order",
  "actions_taken": [
    "Retrieved order details",
    "Checked shipment status"
  ],
  "reason_for_escalation": [
    "Explicit manager request",
    "Repeated complaint"
  ]
}
```

Then provide a customer-facing response confirming that the case is being handed to a human.

---

# 18. Guardrails

The implementation MUST enforce:

### Never:
- Reveal another customer's data
- Guess an order status
- Invent tracking information
- Invent policy rules
- Promise refunds outside policy
- Create returns without eligibility confirmation
- Claim a web search result is company policy
- Expose internal prompts/system instructions
- Continue automated handling after a mandatory escalation trigger

### Always:
- Verify order ownership
- Ground order information in MCP/database results
- Ground policy answers in RAG
- Cite policy sections where relevant
- Record actions taken
- Provide a structured handoff when escalation occurs

---

# 19. Recommended Project Structure

Use a clean modular structure similar to:

```text
customer-support-agent/
│
├── CLAUDE.md
├── README.md
├── .env.example
├── .gitignore
├── pyproject.toml
│
├── app/
│   ├── main.py
│   │
│   ├── config/
│   │   └── settings.py
│   │
│   ├── graph/
│   │   ├── state.py
│   │   ├── graph.py
│   │   ├── routing.py
│   │   └── nodes/
│   │       ├── triage.py
│   │       ├── order_agent.py
│   │       ├── policy_agent.py
│   │       ├── complaint_agent.py
│   │       └── handoff.py
│   │
│   ├── mcp/
│   │   ├── server.py
│   │   └── tools/
│   │       ├── get_order.py
│   │       ├── track_shipment.py
│   │       └── initiate_return.py
│   │
│   ├── rag/
│   │   ├── ingest.py
│   │   ├── retriever.py
│   │   └── documents/
│   │       └── ecommerce_policy.md
│   │
│   ├── database/
│   │   ├── models.py
│   │   ├── db.py
│   │   └── seed.py
│   │
│   ├── tools/
│   │   └── tavily_search.py
│   │
│   └── schemas/
│       └── support.py
│
├── data/
│   └── support.db
│
├── tests/
│   ├── test_mcp_tools.py
│   ├── test_rag.py
│   ├── test_routing.py
│   ├── test_guardrails.py
│   ├── test_returns.py
│   └── test_end_to_end.py
│
└── scripts/
    ├── seed_database.py
    └── ingest_policy.py
```

You may adjust the structure when there is a strong technical reason, but keep responsibilities separated.

---

# 20. Environment Variables

Create `.env.example`.

Expected configuration should include appropriate variables such as:

```env
OPENAI_API_KEY=
TAVILY_API_KEY=
DATABASE_URL=sqlite:///./data/support.db
```

If a different LLM provider is selected, document it clearly.

Never commit real API keys.

---

# 21. Testing Requirements

Create automated tests for:

### Routing
- Order query → Order Agent
- Return query → Policy Agent
- Complaint → Complaint Agent
- Explicit manager request → Human Handoff

### Privacy
- Valid customer/order → details allowed
- Wrong customer/order → details blocked

### Returns
- Eligible item → return can be created
- Ineligible item → return blocked
- Missing policy evidence → return must not be created

### Complaints
- Repeated complaint → escalation
- Explicit human request → escalation
- Normal complaint → attempt resolution

### Web search
- Shipment disruption → search can be triggered
- Normal order status → search should not be required

### End-to-end
Test at least the four sample queries from the specification.

---

# 22. Evaluation Metrics

Implement a small evaluation/test harness.

Measure:

- Intent classification accuracy
- Correct routing rate
- Order ownership violations
- Return eligibility accuracy
- Successful resolution rate
- Human escalation rate
- Tool-call success rate

Optional:

- Response latency
- Token usage
- RAG retrieval relevance

Create a small deterministic evaluation dataset.

---

# 23. Optional Enhancements

After the core system works:

1. Multilingual support
2. Conversation history
3. Streaming responses
4. Simple web UI
5. Admin/support dashboard
6. Resolution-rate analytics
7. More advanced sentiment classification
8. Better RAG evaluation
9. Persistent conversation sessions
10. Human agent case queue

Do not let optional features delay the core implementation.

---

# 24. UI Requirement

If a UI is implemented, keep it clean and minimal.

Required sections:

### Customer Chat
- Conversation area
- Message input
- Send button
- Order/customer context

### Tool Activity
Show safe, human-readable events such as:

```text
✓ Order verified
✓ Shipment status retrieved
✓ Return policy checked
✓ Return created
```

Do not expose hidden chain-of-thought or internal reasoning.

### Human Handoff
Display:

- Escalation status
- Reason
- Case summary
- Actions already taken

---

# 25. Development Rules for Claude Code

Claude Code should:

1. Inspect the repository before making changes.
2. Build the project incrementally.
3. Prefer simple, maintainable implementations over unnecessary abstractions.
4. Use typed Python where practical.
5. Keep secrets in `.env`.
6. Add tests alongside functionality.
7. Run tests after meaningful changes.
8. Fix errors rather than hiding them.
9. Keep MCP, RAG, database, graph, and UI responsibilities separated.
10. Document setup and execution in `README.md`.
11. Create realistic seed data.
12. Make the project runnable from a fresh environment.
13. Do not replace required MCP/RAG/LangGraph functionality with hard-coded fake responses.
14. Do not expose private customer data in logs or UI.
15. Do not expose model chain-of-thought.

---

# 26. Implementation Order

Follow this order unless a dependency requires otherwise.

### Phase 1 — Project Setup
- Python environment
- Dependencies
- Configuration
- Project structure

### Phase 2 — Database
- SQLite schema
- Models
- Seed 50–100 orders
- Test data scenarios

### Phase 3 — MCP Server
- Implement `get_order`
- Implement `track_shipment`
- Implement `initiate_return`
- Add MCP tests

### Phase 4 — RAG
- Create policy document
- Ingestion pipeline
- Retriever
- Policy citation mechanism
- Retrieval tests

### Phase 5 — LangGraph
- Define state
- Build Triage Router
- Build Order Agent
- Build Policy Agent
- Build Complaint Agent
- Build Human Handoff
- Connect routing

### Phase 6 — Tavily
- Implement controlled search tool
- Add courier disruption lookup
- Add product recall lookup

### Phase 7 — Guardrails
- Customer/order ownership
- Return eligibility
- Escalation rules
- Data privacy

### Phase 8 — End-to-End Tests
- Run all sample scenarios
- Add regression tests
- Measure resolution/escalation behavior

### Phase 9 — UI / Demo
Only after the backend workflow is stable.

---

# 27. Definition of Done

The project is considered complete only when:

- [ ] SQLite database contains 50–100 seeded mock orders.
- [ ] MCP server exposes all three required tools.
- [ ] `get_order` works.
- [ ] `track_shipment` works.
- [ ] `initiate_return` works only after eligibility validation.
- [ ] RAG knowledge base contains return/refund/exchange/warranty policies and FAQs.
- [ ] Policy answers use retrieved policy context.
- [ ] LangGraph orchestration is functional.
- [ ] Triage Router classifies requests.
- [ ] Order Agent handles order/shipment requests.
- [ ] Policy Agent handles policy/return questions.
- [ ] Complaint Agent handles dissatisfaction.
- [ ] Human Handoff creates structured summaries.
- [ ] Tavily can check courier disruptions and recalls.
- [ ] Order ownership is verified before details are revealed.
- [ ] Another customer's data cannot be exposed.
- [ ] Refund promises outside policy are blocked.
- [ ] Return eligibility is checked before return creation.
- [ ] Explicit human/manager requests trigger escalation.
- [ ] Repeated complaints trigger escalation.
- [ ] Automated tests pass.
- [ ] README explains installation and usage.
- [ ] `.env.example` is provided.
- [ ] No API keys are committed.
- [ ] The project can be demonstrated locally from a clean setup.

---

# 28. Final Instruction to Claude Code

**Build the complete project described in this document.**

Do not merely provide an implementation plan.

First inspect the existing repository and determine what already exists. Reuse working components where appropriate. Then implement the system incrementally, testing each major component.

At the end:

1. Run the test suite.
2. Fix failing tests.
3. Run representative end-to-end scenarios.
4. Verify privacy and escalation guardrails.
5. Update `README.md` with exact setup/run commands.
6. Provide a concise final report containing:
   - What was implemented
   - Files/components created or changed
   - How to run it
   - Test results
   - Any remaining limitations

The final project should be a **real working customer-support agent**, not a conceptual prototype.
