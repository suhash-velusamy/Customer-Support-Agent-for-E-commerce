"""Deterministic evaluation harness.

Runs every case in eval_dataset.json through the real graph (fresh seeded database,
rules-only triage, no real web calls) and reports the metrics from CLAUDE.md §22.
Metrics are computed on the last turn of each case.
"""

import json
import tempfile
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from app.database.db import connect
from app.database.seed import REFERENCE_DATE, seed
from app.graph.graph import SupportAgent
from app.tools.tavily_search import WebSearch

DATASET_PATH = Path(__file__).with_name("eval_dataset.json")


class _NoWeb:
    """Offline stand-in for Tavily so evaluation is reproducible."""

    async def search(self, query, **kwargs):
        return {"results": []}


@dataclass
class CaseResult:
    id: str
    passed: bool
    intent: str | None
    route: str | None
    outcome: str
    return_eligible: bool | None
    latency_ms: float
    failures: list[str] = field(default_factory=list)


def _outcome(state: dict) -> str:
    if state.get("escalation_required") or state.get("handoff_summary"):
        return "escalated"
    if state.get("route") == "clarify":
        return "clarified"
    return "resolved"


def _rate(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 3) if denominator else None


def run_evaluation(dataset_path: Path = DATASET_PATH) -> dict:
    cases = json.loads(dataset_path.read_text(encoding="utf-8"))
    tool_calls = {"total": 0, "ok": 0}

    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "eval.db"
        conn = connect(db_path)
        seed(conn)
        conn.close()

        agent = SupportAgent(db_path=db_path, customer_id="CUST-001", use_llm=False,
                             today=lambda: REFERENCE_DATE, web=WebSearch(client=_NoWeb()))
        real_call = agent.deps.tools.call

        async def counted_call(name, **kwargs):
            result = await real_call(name, **kwargs)
            tool_calls["total"] += 1
            # Business outcomes (e.g. ownership refused) are successful calls; only failures count against.
            tool_calls["ok"] += result.get("error") != "tool_failure"
            return result

        agent.deps.tools.call = counted_call

        results: list[CaseResult] = []
        for case in cases:
            start = time.perf_counter()
            for turn in case["turns"]:
                state = agent.chat(turn, thread_id=case["id"])
            latency = (time.perf_counter() - start) * 1000 / len(case["turns"])

            text = state.get("final_response") or ""
            failures = []
            if "intent" in case and state.get("intent") != case["intent"]:
                failures.append(f"intent {state.get('intent')} != {case['intent']}")
            if state.get("route") != case["route"]:
                failures.append(f"route {state.get('route')} != {case['route']}")
            if _outcome(state) != case["outcome"]:
                failures.append(f"outcome {_outcome(state)} != {case['outcome']}")
            if "return_eligible" in case and state.get("return_eligible") != case["return_eligible"]:
                failures.append(f"return_eligible {state.get('return_eligible')} != {case['return_eligible']}")
            failures += [f"missing '{s}'" for s in case.get("must_contain", []) if s not in text]
            failures += [f"leaked '{s}'" for s in case.get("must_not_contain", []) if s in text]

            results.append(CaseResult(case["id"], not failures, state.get("intent"), state.get("route"),
                                      _outcome(state), state.get("return_eligible"), round(latency, 1), failures))

    by_id = {c["id"]: c for c in cases}
    intent_cases = [r for r in results if "intent" in by_id[r.id]]
    eligibility_cases = [r for r in results if "return_eligible" in by_id[r.id]]
    privacy_cases = [r for r in results if by_id[r.id].get("must_not_contain")]

    metrics = {
        "cases": len(results),
        "cases_passed": sum(r.passed for r in results),
        "intent_accuracy": _rate(sum(r.intent == by_id[r.id]["intent"] for r in intent_cases), len(intent_cases)),
        "routing_accuracy": _rate(sum(r.route == by_id[r.id]["route"] for r in results), len(results)),
        "ownership_violations": sum(any(f.startswith("leaked") for f in r.failures) for r in privacy_cases),
        "return_eligibility_accuracy": _rate(
            sum(r.return_eligible == by_id[r.id]["return_eligible"] for r in eligibility_cases), len(eligibility_cases)),
        "outcome_accuracy": _rate(sum(r.outcome == by_id[r.id]["outcome"] for r in results), len(results)),
        "resolution_rate": _rate(sum(r.outcome == "resolved" for r in results), len(results)),
        "escalation_rate": _rate(sum(r.outcome == "escalated" for r in results), len(results)),
        "tool_call_success_rate": _rate(tool_calls["ok"], tool_calls["total"]),
        "tool_calls": tool_calls["total"],
        "avg_latency_ms": round(sum(r.latency_ms for r in results) / len(results), 1),
    }
    return {"metrics": metrics, "results": [asdict(r) for r in results]}


def format_report(report: dict) -> str:
    m = report["metrics"]

    def pct(value):
        return "n/a" if value is None else f"{value:.1%}"

    lines = [
        "Evaluation report",
        "=================",
        f"Cases passed:                {m['cases_passed']}/{m['cases']}",
        f"Intent accuracy:             {pct(m['intent_accuracy'])}",
        f"Routing accuracy:            {pct(m['routing_accuracy'])}",
        f"Ownership violations:        {m['ownership_violations']}",
        f"Return eligibility accuracy: {pct(m['return_eligibility_accuracy'])}",
        f"Outcome accuracy:            {pct(m['outcome_accuracy'])}",
        f"Resolution rate:             {pct(m['resolution_rate'])}",
        f"Human escalation rate:       {pct(m['escalation_rate'])}",
        f"Tool-call success rate:      {pct(m['tool_call_success_rate'])} ({m['tool_calls']} calls)",
        f"Avg latency per turn:        {m['avg_latency_ms']} ms",
    ]
    failed = [r for r in report["results"] if not r["passed"]]
    if failed:
        lines += ["", "Failed cases:"]
        lines += [f"- {r['id']}: {'; '.join(r['failures'])}" for r in failed]
    return "\n".join(lines)
