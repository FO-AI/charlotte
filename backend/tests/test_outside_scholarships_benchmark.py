"""Opt-in timing benchmark: a 50-check outside-scholarship upload, end to end through the route.

Skipped unless OUTSIDE_SCHOLARSHIPS_BENCHMARK is set; its value labels the report, e.g.

    OUTSIDE_SCHOLARSHIPS_BENCHMARK=before pytest tests/test_outside_scholarships_benchmark.py -s

No real Azure or Graph access. The LLM is a fake that sleeps for assumed call latencies,
which are recorded in the report, and conftest answers the Graph lookup from an empty directory. Local CPU work (page rendering, PDF splitting,
Excel) is real, on scan-like pages. Each run writes backend/reports/outside_scholarships_benchmark_<label>_<cpus>.json.

The pipeline's thread pool defaults to min(32, CPUs + 4) workers, so each run also emulates a
2-vCPU App Service instance, where that default is 6.
"""

import json
import os
import subprocess
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import fitz
import numpy as np
import pytest

_LABEL = os.getenv("OUTSIDE_SCHOLARSHIPS_BENCHMARK")
pytestmark = pytest.mark.skipif(not _LABEL, reason="set OUTSIDE_SCHOLARSHIPS_BENCHMARK=<label> to run")

_ROUTE = "/api/banking/outside-scholarships"
_REPORTS_DIR = Path(__file__).resolve().parents[1] / "reports"
_CHECK_COUNT = 50
_SIDES = ["front", "back"] * _CHECK_COUNT

# Assumed network latencies. Replace with numbers from real run logs when available.
_SIDE_CLASSIFICATION_SECONDS = 3.0
_EXTRACTION_SECONDS = 4.0

_SCAN_DPI = 300
_LETTER_INCHES = (8.5, 11.0)
_EXTRACTED_CHECK = {
    "pid_list": ["730000001"],
    "amount": "100.00",
    "check_number": "1001",
    "name": "Student Name",
    "provider": "Scholarship Foundation",
    "scholarship_name": None,
}


def _scan_like_pdf():
    """Letter pages that each embed one grayscale JPEG scan: white paper, grain, rules, strokes."""
    width_in, height_in = _LETTER_INCHES
    pixels_w, pixels_h = int(width_in * _SCAN_DPI), int(height_in * _SCAN_DPI)
    rng = np.random.default_rng(0)
    pixels = np.full((pixels_h, pixels_w), 248.0) + rng.normal(0, 2, (pixels_h, pixels_w))
    for row in range(300, pixels_h - 300, 120):
        pixels[row:row + 3, 200:pixels_w - 200] = 40
    for _ in range(400):
        y, x = rng.integers(200, pixels_h - 240), rng.integers(200, pixels_w - 400)
        pixels[y:y + 28, x:x + rng.integers(40, 300)] = 60
    scan = fitz.Pixmap(fitz.csGRAY, pixels_w, pixels_h, pixels.clip(0, 255).astype(np.uint8).tobytes(), False)
    scan_jpeg = scan.tobytes("jpeg")

    document = fitz.open()
    for _ in _SIDES:
        page = document.new_page(width=width_in * 72, height=height_in * 72)
        page.insert_image(page.rect, stream=scan_jpeg)
    return document.tobytes()


class _StageClock:
    """First start, last end, call count, and peak concurrency for one kind of fake call."""

    def __init__(self):
        self._lock = threading.Lock()
        self.first_start = None
        self.last_end = None
        self.calls = 0
        self.in_flight = 0
        self.peak_in_flight = 0

    def start(self):
        now = time.perf_counter()
        with self._lock:
            self.calls += 1
            self.in_flight += 1
            self.peak_in_flight = max(self.peak_in_flight, self.in_flight)
            self.first_start = now if self.first_start is None else min(self.first_start, now)

    def finish(self):
        now = time.perf_counter()
        with self._lock:
            self.in_flight -= 1
            self.last_end = now if self.last_end is None else max(self.last_end, now)


class _LatencyLLM:
    """Answers side classification from the scripted sides and extraction with a fixed check."""

    def __init__(self):
        self.classification = _StageClock()
        self.extraction = _StageClock()
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, model, messages, response_format):
        content = messages[0]["content"]
        page_labels = [part["text"] for part in content[1:] if part["type"] == "text"]
        if page_labels:
            pages = [int(label.removeprefix("Page ")) for label in page_labels]
            reply = {"pages": [{"page": page, "side": _SIDES[page - 1]} for page in pages]}
            clock, seconds = self.classification, _SIDE_CLASSIFICATION_SECONDS
        else:
            reply, clock, seconds = _EXTRACTED_CHECK, self.extraction, _EXTRACTION_SECONDS
        clock.start()
        time.sleep(seconds)
        clock.finish()
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(reply)))])


def _commit():
    repo = Path(__file__).resolve().parents[2]
    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=repo, capture_output=True, text=True).stdout.strip()
    dirty = subprocess.run(["git", "status", "--porcelain"], cwd=repo, capture_output=True, text=True).stdout.strip()
    return f"{commit}-dirty" if dirty else commit


@pytest.fixture(scope="module")
def scan_like_pdf():
    return _scan_like_pdf()


@pytest.mark.parametrize("emulated_cpu_count", [None, 2], ids=["host-cpus", "2-vcpu"])
def test_fifty_check_upload_timing(client, override_auth, app, monkeypatch, scan_like_pdf, emulated_cpu_count):
    from api.dependencies import get_azure_client

    if emulated_cpu_count is not None:
        monkeypatch.setattr(os, "cpu_count", lambda: emulated_cpu_count)
    llm = _LatencyLLM()
    app.dependency_overrides[get_azure_client] = lambda: SimpleNamespace(llm=llm)

    upload_start = time.perf_counter()
    response = client.post(
        _ROUTE,
        files={"files": ("checks.pdf", scan_like_pdf, "application/pdf")},
        data={"aid_term": "F"},
    )
    upload_end = time.perf_counter()

    assert response.status_code == 200, response.text
    assert llm.extraction.calls == _CHECK_COUNT

    cpu_count = os.cpu_count()
    classification, extraction = llm.classification, llm.extraction
    report = {
        "label": _LABEL,
        "commit": _commit(),
        "cpu_count_seen_by_pipeline": cpu_count,
        "pages": len(_SIDES),
        "checks": _CHECK_COUNT,
        "assumed_latency_seconds": {
            "side_classification_call": _SIDE_CLASSIFICATION_SECONDS,
            "extraction_call": _EXTRACTION_SECONDS,
        },
        "seconds": {
            "upload_to_excel": round(upload_end - upload_start, 2),
            "side_classification": round(classification.last_end - classification.first_start, 2),
            "upload_to_first_extraction": round(extraction.first_start - upload_start, 2),
            "first_to_last_extraction": round(extraction.last_end - extraction.first_start, 2),
        },
        "peak_in_flight": {
            "side_classification": classification.peak_in_flight,
            "extraction": extraction.peak_in_flight,
        },
    }
    _REPORTS_DIR.mkdir(exist_ok=True)
    report_path = _REPORTS_DIR / f"outside_scholarships_benchmark_{_LABEL}_{cpu_count}cpu.json"
    report_path.write_text(json.dumps(report, indent=2))
    print(f"\n{report_path.name}: {json.dumps(report['seconds'])} peak={json.dumps(report['peak_in_flight'])}")
