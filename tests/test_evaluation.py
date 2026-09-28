"""Evaluation harness as a regression gate."""

import pytest

from app.evaluation.evaluate import format_report, run_evaluation


@pytest.fixture(scope="module")
def report():
    return run_evaluation()


def test_all_cases_pass(report):
    assert report["metrics"]["cases_passed"] == report["metrics"]["cases"], format_report(report)


def test_metric_thresholds(report):
    m = report["metrics"]
    assert m["ownership_violations"] == 0
    assert m["intent_accuracy"] >= 0.95
    assert m["routing_accuracy"] >= 0.95
    assert m["return_eligibility_accuracy"] == 1.0
    assert m["tool_call_success_rate"] == 1.0


def test_report_has_required_metrics(report):
    for key in ("intent_accuracy", "routing_accuracy", "ownership_violations", "return_eligibility_accuracy",
                "resolution_rate", "escalation_rate", "tool_call_success_rate"):
        assert report["metrics"][key] is not None
