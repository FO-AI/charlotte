"""E2E: outside-scholarship uploads stay correct when their slow steps run concurrently.

Ways the concurrent pipeline can fail, each guarded below:
1. Side-classification batches still go out one after another, so a large PDF waits on
   one LLM call per ten pages before any check starts.
2. Batch replies are stitched together in completion order instead of page order, so a slow
   early batch shifts every later page and checks get the wrong fronts and backs.
3. More Document Intelligence calls run at once than the per-upload cap, overflowing the DI
   connection pool ("Connection pool is full, discarding connection"), or a large PDF sends
   every side-classification batch at once, beyond that same cap.
4. With rendering moved into the per-check workers, a check is verified at the wrong
   resolution (such as the classification thumbnail) or without its back.
5. PyMuPDF is used from several threads at once, which it does not support. The pipeline
   serializes it with PYMUPDF_LOCK; the fakes here take the same lock when they read PDFs.

No real Azure access: the LLM and Document Intelligence are fakes. Timing properties are
checked structurally (barriers and in-flight counters), never with wall-clock thresholds.
"""

import base64
import json
import struct
import threading
import time
from types import SimpleNamespace

import fitz
import pytest

from services.banking.outside_scholarships.nodes import PYMUPDF_LOCK
from services.banking.outside_scholarships.service import MAX_CONCURRENT_CHECKS

FRONT = "front"
BACK = "back"
_ROUTE = "/api/banking/outside-scholarships"
_FIRST_CHECK_NUMBER = 1001
_CLASSIFICATION_BATCH_SIZE = 10
_VERIFY_DPI = 200
_BARRIER_TIMEOUT_SECONDS = 5
_PNG_SIZE_OFFSET = slice(16, 24)


def _build_pdf(sides):
    """One page per side. Fronts carry a check number; backs carry the PID of the preceding front."""
    document = fitz.open()
    check_number = _FIRST_CHECK_NUMBER - 1
    for side in sides:
        page = document.new_page()
        if side == FRONT:
            check_number += 1
            page.insert_text((72, 72), f"Check No: {check_number}")
        else:
            page.insert_text((72, 72), f"PID: P{check_number:07d}")
    return document.tobytes()


def _expected_images_per_check(sides):
    counts = {}
    check_number = _FIRST_CHECK_NUMBER - 1
    for side in sides:
        if side == FRONT:
            check_number += 1
            counts[str(check_number)] = 1
        else:
            counts[str(check_number)] = 2
    return counts


def _png_size(png_bytes):
    return struct.unpack(">II", png_bytes[_PNG_SIZE_OFFSET])


class FakeDocumentIntelligence:
    """Returns each check PDF's text like DI OCR would, and tracks how many calls overlap."""

    def __init__(self, analyze_seconds=0.0):
        self.analyze_seconds = analyze_seconds
        self._lock = threading.Lock()
        self.in_flight = 0
        self.peak_in_flight = 0

    def begin_analyze_document(self, model_id, request=None, **kwargs):
        with self._lock:
            self.in_flight += 1
            self.peak_in_flight = max(self.peak_in_flight, self.in_flight)
        with PYMUPDF_LOCK, fitz.open(stream=request.bytes_source, filetype="pdf") as document:
            lines = [line for page in document for line in page.get_text().splitlines() if line.strip()]
        analyze_result = SimpleNamespace(
            pages=[SimpleNamespace(lines=[SimpleNamespace(content=line) for line in lines])],
            content="\n".join(lines),
            key_value_pairs=[],
        )

        def result():
            time.sleep(self.analyze_seconds)
            with self._lock:
                self.in_flight -= 1
            return analyze_result

        return SimpleNamespace(result=result)


class FakeLLM:
    """Classifies pages from scripted sides; verification echoes DI and records image sizes.

    `classification_delay(first_page)` lets a test make chosen batches finish later, and
    `classification_barrier` makes every batch wait until all of them are in flight together.
    """

    def __init__(self, sides, classification_delay=lambda first_page: 0.0, classification_barrier=None):
        self.sides = sides
        self.classification_delay = classification_delay
        self.classification_barrier = classification_barrier
        self.image_sizes_by_check = {}
        self._lock = threading.Lock()
        self.classifications_in_flight = 0
        self.peak_classifications_in_flight = 0
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, model, messages, response_format):
        content = messages[0]["content"]
        page_labels = [part["text"] for part in content[1:] if part["type"] == "text"]
        if page_labels:
            pages = [int(label.removeprefix("Page ")) for label in page_labels]
            with self._lock:
                self.classifications_in_flight += 1
                self.peak_classifications_in_flight = max(
                    self.peak_classifications_in_flight, self.classifications_in_flight
                )
            if self.classification_barrier is not None:
                self.classification_barrier.wait()
            time.sleep(self.classification_delay(pages[0]))
            with self._lock:
                self.classifications_in_flight -= 1
            return self._reply(json.dumps({"pages": [{"page": page, "side": self.sides[page - 1]} for page in pages]}))

        di_candidate_line = next(line for line in content[0]["text"].splitlines() if line.startswith('{"pid_list"'))
        images = [part["image_url"]["url"].split(",", 1)[1] for part in content if part["type"] == "image_url"]
        check_number = json.loads(di_candidate_line)["check_number"]
        self.image_sizes_by_check[check_number] = [_png_size(base64.b64decode(image)) for image in images]
        return self._reply(di_candidate_line)

    @staticmethod
    def _reply(text):
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text))])


def _upload(client, app, sides, llm, document_intelligence):
    from api.dependencies import get_azure_client

    app.dependency_overrides[get_azure_client] = lambda: SimpleNamespace(
        llm=llm,
        get_di=lambda: document_intelligence,
        di_model_id="prebuilt-check.us",
    )
    return client.post(
        _ROUTE,
        files={"files": ("checks.pdf", _build_pdf(sides), "application/pdf")},
        data={"aid_term": "F"},
    )


def test_classification_batches_are_sent_concurrently(client, override_auth, app):
    sides = [FRONT] * (3 * _CLASSIFICATION_BATCH_SIZE)
    # Sent one after another, the first batch waits alone until the barrier times out.
    barrier = threading.Barrier(parties=3, timeout=_BARRIER_TIMEOUT_SECONDS)
    llm = FakeLLM(sides, classification_barrier=barrier)

    response = _upload(client, app, sides, llm, FakeDocumentIntelligence())

    assert response.status_code == 200, response.text
    assert len(llm.image_sizes_by_check) == len(sides)


def test_batches_finishing_out_of_order_keep_page_order(client, override_auth, app):
    # Three batches with different side patterns, so any reordering changes the checks.
    sides = (
        [FRONT, BACK] * 5
        + [FRONT] * 10
        + [FRONT, BACK] + [FRONT] * 8
    )
    finish_last_first = {1: 0.4, 11: 0.2, 21: 0.0}
    llm = FakeLLM(sides, classification_delay=lambda first_page: finish_last_first[first_page])

    response = _upload(client, app, sides, llm, FakeDocumentIntelligence())

    assert response.status_code == 200, response.text
    images_per_check = {check: len(sizes) for check, sizes in llm.image_sizes_by_check.items()}
    assert images_per_check == _expected_images_per_check(sides)


def test_document_intelligence_calls_stay_within_the_concurrency_cap(client, override_auth, app):
    sides = [FRONT] * (3 * MAX_CONCURRENT_CHECKS)
    document_intelligence = FakeDocumentIntelligence(analyze_seconds=0.2)

    response = _upload(client, app, sides, FakeLLM(sides), document_intelligence)

    assert response.status_code == 200, response.text
    assert 1 < document_intelligence.peak_in_flight <= MAX_CONCURRENT_CHECKS


def test_classification_calls_stay_within_the_concurrency_cap(client, override_auth, app):
    sides = [FRONT] * (_CLASSIFICATION_BATCH_SIZE * (MAX_CONCURRENT_CHECKS + 2))
    llm = FakeLLM(sides, classification_delay=lambda first_page: 0.2)

    response = _upload(client, app, sides, llm, FakeDocumentIntelligence())

    assert response.status_code == 200, response.text
    assert 1 < llm.peak_classifications_in_flight <= MAX_CONCURRENT_CHECKS


@pytest.mark.parametrize(
    ("sides", "expected_page_counts"),
    [
        pytest.param([FRONT, BACK, FRONT], {"1001": 2, "1002": 1}, id="back-then-no-back"),
        pytest.param([FRONT, FRONT, BACK], {"1001": 1, "1002": 2}, id="no-back-then-back"),
    ],
)
def test_checks_are_verified_with_full_resolution_pages(client, override_auth, app, sides, expected_page_counts):
    llm = FakeLLM(sides)

    response = _upload(client, app, sides, llm, FakeDocumentIntelligence())

    assert response.status_code == 200, response.text
    with PYMUPDF_LOCK, fitz.open() as blank:
        page_rect = blank.new_page().rect
    scale = _VERIFY_DPI / 72
    rendered = (page_rect * fitz.Matrix(scale, scale)).irect
    full_resolution = (rendered.width, rendered.height)
    assert llm.image_sizes_by_check == {
        check: [full_resolution] * page_count for check, page_count in expected_page_counts.items()
    }
