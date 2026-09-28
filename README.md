# Customer Support Agent for E-commerce

LangGraph support agent using MCP tools (orders/shipments/returns), RAG over company policy,
Tavily web search (courier disruptions, recalls), SQLite mock data, and structured human handoff.
The LLM is accessed through [OpenRouter](https://openrouter.ai) (OpenAI-compatible API; set `OPENROUTER_MODEL` to any OpenRouter model id).
See `CLAUDE.md` for the full specification.

> Status: database, MCP server, RAG and LangGraph agent implemented. All phases implemented: database, MCP server, RAG, LangGraph agent, Tavily, guardrails, evaluation and web UI.

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows  (source .venv/bin/activate on macOS/Linux)
pip install -e ".[dev]"
copy .env.example .env        # then fill in OPENROUTER_API_KEY / TAVILY_API_KEY
```

## Seed the database

```bash
python scripts/seed_database.py   # creates data/support.db (80 orders, deterministic)
```

Demo customer is `CUST-001`. Key scenario orders: `10245` (delayed, Example Express, Chennai),
`10250` (shoes delivered last week, returnable), `10260` (refund pending 10 days),
`10270` (outside return window), `10271` (non-returnable swimwear + gift card),
`10300` (belongs to CUST-002, for privacy tests).

## MCP server

```bash
python -m app.mcp.server   # stdio transport
```

Tools (all take the authenticated `customer_id` and only return that customer's data):

- `get_order(order_id, customer_id)`: order details, items, payment/refund status, returns
- `track_shipment(customer_id, order_id | shipment_id)`: carrier, tracking number, status, location, ETA
- `initiate_return(customer_id, order_id, item_ids, reason, eligibility_confirmed, policy_reference)`:
  refuses unless the Policy Agent confirmed eligibility and supplied the policy citation; also
  re-checks ownership, delivery, item membership and duplicate returns.

Unknown orders and other customers' orders return the same "couldn't verify" error, so order IDs can't be probed.

## Policy knowledge base (RAG)

```bash
python scripts/ingest_policy.py   # builds data/index/policy_chunks.json
```

The policy lives in `app/rag/documents/ecommerce_policy.md`. Each `####` rule becomes one chunk
cited by its heading path, e.g. `Policy: Returns > Eligibility > 30-day return window`.
Retrieval is local TF-IDF (scikit-learn, no API key needed); `search_policy(query)` returns
the top matches with citation, text and score, or an empty list when nothing relevant is found.
The index rebuilds automatically if the policy document is newer than it.

## Run the web UI

```bash
python -m app.web.server      # then open http://127.0.0.1:8000
```

Three panels: **Customer chat** (with suggested questions and the current order/customer context),
**Tool activity** (human-readable events per message, e.g. "✓ Order verified"), and **Human handoff**
(escalation status, reasons, case summary and actions taken). The browser only receives the reply,
activity events and handoff summary; raw tool data and internal state stay on the server.
"New conversation" starts a fresh session.

## Run the agent (CLI)

```bash
python -m app.main            # uses the OpenRouter LLM for intent classification if OPENROUTER_API_KEY is set
python -m app.main --no-llm   # deterministic rules only, no API key needed
```

Try: `Where is my order #10245?`, `I want to return the shoes I bought last week.` (then `yes`),
`My refund still hasn't arrived after 10 days.`,
`This is the third time my order is late. I want to speak to a manager.`

The CLI shows the tool activity for each turn and, when a case is escalated, the handoff summary.

### How the graph works

```
triage ─┬─ order_agent ─────┐
        ├─ policy_agent ────┤──(escalation?)──> handoff ─┐
        ├─ complaint_agent ─┤                            ├─> respond
        ├─ clarify ─────────┘──────────────────────────────┘
        └─ handoff (mandatory triggers: human/manager request, repeated complaint, anger, fraud)
```

- **Triage** uses keyword rules with typo correction. When an LLM is configured it refines intent/sentiment,
  but escalation triggers always come from the rules, so the LLM can't bypass them.
- **Returns**: the Policy Agent reads the return window and non-returnable list from the retrieved policy text,
  asks the customer to confirm, and only then does the Order Agent call `initiate_return`. Missing policy
  evidence blocks the return and escalates.
- **Refunds**: pending refunds are compared against the policy's 14-day window; beyond it the case escalates.
- **Privacy**: every tool call carries the authenticated customer ID (`DEMO_CUSTOMER_ID`, default `CUST-001`).
- Customer replies are built from tool results and quoted policy text, so the agent can't invent order facts or rules.
- Dates use `DEMO_TODAY` (default: the seed reference date, 2026-09-28) so the demo data stays consistent.
- After a handoff the conversation stays with the human; later messages get a holding reply.

### Guardrails

| Guardrail | Where it's enforced |
|---|---|
| Other customers' data never revealed | Every MCP tool filters by the authenticated `customer_id`; unknown and foreign orders get the same "couldn't verify" reply. Identity claims in messages are ignored. |
| No guessed order/tracking info | Replies are built only from tool results. |
| No invented policy | Policy answers quote retrieved text with a citation; missing evidence → no action + escalation. |
| No returns without eligibility | Policy Agent check + customer confirmation + `initiate_return` refuses without confirmation and citation. |
| No refund/compensation promises | Refund timing comes from the policy window; compensation requests escalate; output check blocks promise wording. |
| Web results never presented as policy | Labelled "External information (web search, not company policy)". |
| No internal prompt exposure | Injection attempts are refused; output check blocks prompt/secret text. |
| Mandatory escalation | Human/manager request, repeated complaint, anger, fraud/security, sensitive cases (legal, injury/safety), compensation requests, tool failure, policy ambiguity, repeated misunderstanding. No automation after handoff. |

Every reply passes through `app/guardrails.py` before it's sent. If it contains another customer's ID, an
email address, internal instructions or an unsupported promise, it is replaced with a safe fallback and
the event is recorded in the activity log.

### Web search (Tavily)

Used only for two things, and only when needed:

- **Courier disruptions**: when a shipment is delayed, the Order Agent searches recent news for the carrier
  (and location). Normal, on-time orders never trigger a search.
- **Product recalls**: "Has my smartwatch been recalled?" searches recall notices for the product
  from the customer's own order.

Results are filtered for relevance, capped at 3, and always shown under
"External information (web search, not company policy)" with source links, separate from policy citations.
Without `TAVILY_API_KEY` the searches are skipped and the agent says it has no confirmed reason for the delay.

## Evaluation

```bash
python scripts/run_evaluation.py
```

Runs the 37 cases in `app/evaluation/eval_dataset.json` through the real graph (fresh seeded database,
rules-only triage, offline web search) and reports intent accuracy, routing accuracy, ownership
violations, return-eligibility accuracy, outcome accuracy, resolution and escalation rates, tool-call
success rate and latency. Full per-case results go to `data/eval_report.json`. The script exits
non-zero if any case fails, and `tests/test_evaluation.py` runs the same harness as part of `pytest`.

Each case lists the expected intent, route, outcome (`resolved` / `escalated` / `clarified`), optional
return eligibility, and strings the reply must or must not contain (used to detect privacy leaks).

## Layout

- `app/graph/` – LangGraph state, graph, routing, agent nodes
- `app/mcp/` – MCP server, tools and the async client used by the graph
- `app/rag/` – policy document, ingestion, retriever
- `app/database/` – SQLite schema and deterministic seed data
- `app/tools/` – Tavily search wrapper
- `scripts/` – `seed_database.py`, `ingest_policy.py`
- `tests/` – pytest suite

## Test

```bash
pytest
```
