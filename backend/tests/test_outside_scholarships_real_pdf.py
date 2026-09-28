"""Opt-in: extract a real outside-scholarship PDF through the real Azure deployment, and compare runs.

Skipped unless OUTSIDE_SCHOLARSHIPS_EVAL_DIR names a folder of check PDFs, which are processed
together in file-name order. Credentials come from backend/.env, and every run makes real, billed
Azure calls, so CI never sets it. Run this file on its own, so no other test loads settings first:

    OUTSIDE_SCHOLARSHIPS_EVAL_DIR=~/checks OUTSIDE_SCHOLARSHIPS_EVAL_LABEL=llm-only \\
        pytest tests/test_outside_scholarships_real_pdf.py -s

Writes backend/reports/outside_scholarships_eval_<label>.json (gitignored) with every check the
pipeline returned and the run time. With OUTSIDE_SCHOLARSHIPS_EVAL_BASELINE=<an earlier report>, it
also writes outside_scholarships_eval_<label>_vs_<baseline label>.json: for each field, how many
checks agree and which ones differ. Checks are compared by position, so the comparison only means
something when both runs found the same number of checks. Reports hold student PIDs and names, so
the terminal gets counts only.
"""

import asyncio
import json
import os
import time
from pathlib import Path

import pytest
from dotenv import load_dotenv

_BACKEND_DIR = Path(__file__).resolve().parents[1]
_REPORTS_DIR = _BACKEND_DIR / "reports"
_EVAL_DIR = os.getenv("OUTSIDE_SCHOLARSHIPS_EVAL_DIR")
_LABEL = os.getenv("OUTSIDE_SCHOLARSHIPS_EVAL_LABEL", "latest")
_BASELINE = os.getenv("OUTSIDE_SCHOLARSHIPS_EVAL_BASELINE")
_COMPARED_FIELDS = ("pid_list", "amount", "check_number", "name", "provider", "scholarship_name")
# conftest.py fills unset Azure settings with this placeholder host so the app can import in CI.
_CI_PLACEHOLDER_HOST = "ci.invalid"

pytestmark = pytest.mark.skipif(not _EVAL_DIR, reason="set OUTSIDE_SCHOLARSHIPS_EVAL_DIR=<folder of PDFs> to run")

if _EVAL_DIR:
    # Replace conftest's placeholders with the real credentials before settings are first loaded.
    load_dotenv(_BACKEND_DIR / ".env", override=True)


def _comparable(field, value):
    return sorted(value) if field == "pid_list" and isinstance(value, list) else value


def _comparison(baseline, checks, run_seconds):
    baseline_checks = baseline["checks"]
    fields = {}
    for field in _COMPARED_FIELDS:
        differing = [
            {"check": position, "baseline": before.get(field), "this_run": after.get(field)}
            for position, (before, after) in enumerate(zip(baseline_checks, checks), start=1)
            if _comparable(field, before.get(field)) != _comparable(field, after.get(field))
        ]
        compared = min(len(baseline_checks), len(checks))
        fields[field] = {"same": compared - len(differing), "different": len(differing), "checks": differing}
    return {
        "baseline_label": baseline["label"],
        "label": _LABEL,
        "check_count": {"baseline": len(baseline_checks), "this_run": len(checks)},
        "run_seconds": {"baseline": baseline["run_seconds"], "this_run": run_seconds},
        "fields": fields,
    }


def test_real_pdf_extraction_report():
    from config.settings import settings
    from services.azure_services import AzureClient, GraphUserDirectory
    from services.banking.outside_scholarships.service import OutsideScholarshipService

    assert _CI_PLACEHOLDER_HOST not in (settings.azure_ai_resource_endpoint or ""), (
        "Settings were loaded with the test placeholders; run this file on its own."
    )
    service = OutsideScholarshipService(AzureClient(), GraphUserDirectory())

    started = time.perf_counter()
    payload = asyncio.run(service.process_folder(os.path.expanduser(_EVAL_DIR)))
    run_seconds = round(time.perf_counter() - started, 2)

    checks = payload["checks"]
    assert checks, f"no checks were extracted from {_EVAL_DIR}"
    _REPORTS_DIR.mkdir(exist_ok=True)
    report_path = _REPORTS_DIR / f"outside_scholarships_eval_{_LABEL}.json"
    report_path.write_text(json.dumps({"label": _LABEL, "run_seconds": run_seconds, "checks": checks}, indent=2))
    print(f"\n{report_path.name}: checks={len(checks)} run_seconds={run_seconds}")

    if not _BASELINE:
        return
    baseline = json.loads(Path(_BASELINE).expanduser().read_text())
    comparison = _comparison(baseline, checks, run_seconds)
    comparison_path = _REPORTS_DIR / f"outside_scholarships_eval_{_LABEL}_vs_{baseline['label']}.json"
    comparison_path.write_text(json.dumps(comparison, indent=2))
    counts = {field: (result["same"], result["different"]) for field, result in comparison["fields"].items()}
    print(f"{comparison_path.name}: check_count={comparison['check_count']} (same, different)={counts}")
