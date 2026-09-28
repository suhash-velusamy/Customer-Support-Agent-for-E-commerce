"""Run the evaluation harness. Usage: python scripts/run_evaluation.py"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config.settings import PROJECT_ROOT  # noqa: E402
from app.evaluation.evaluate import format_report, run_evaluation  # noqa: E402

if __name__ == "__main__":
    report = run_evaluation()
    out = PROJECT_ROOT / "data" / "eval_report.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(format_report(report))
    print(f"\nFull results: {out}")
    sys.exit(0 if report["metrics"]["cases_passed"] == report["metrics"]["cases"] else 1)
