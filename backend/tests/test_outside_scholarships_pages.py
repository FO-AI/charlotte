"""E2E: outside-scholarship uploads where some checks have no scanned back.

No real Azure access. Document Intelligence and the LLM are fakes that read the text
PyMuPDF writes onto each test page, so every assertion reflects which pages actually
reached each check: fronts carry the check number and amount, backs carry the PID.
"""

import json
from types import SimpleNamespace

import fitz
import pytest
from openpyxl import load_workbook

from services.banking.outside_scholarships.nodes import PYMUPDF_LOCK

FRONT = "front"
BACK = "back"
_ROUTE = "/api/banking/outside-scholarships"
_FIRST_DATA_ROW = 6
_FIRST_CHECK_NUMBER = 1001


def _build_pdf(sides):
    """One page per side. A back carries the PID of the check whose front precedes it."""
    document = fitz.open()
    check_number = _FIRST_CHECK_NUMBER - 1
    for side in sides:
        page = document.new_page()
        if side == FRONT:
            check_number += 1
            page.insert_text((72, 72), f"Check No: {check_number}")
            page.insert_text((72, 100), f"Amount: ${(check_number - 1000) * 100}.00")
        else:
            page.insert_text((72, 72), f"PID: P{check_number:07d}")
    return document.tobytes()


class FakeDocumentIntelligence:
    """Returns the text written on each page of the check PDF, like DI OCR would."""

    def __init__(self):
        self.calls = 0

    def begin_analyze_document(self, model_id, request=None, **kwargs):
        self.calls += 1
        pdf_bytes = request.bytes_source if request is not None else kwargs["body"]
        with PYMUPDF_LOCK, fitz.open(stream=pdf_bytes, filetype="pdf") as document:
            lines = [line for page in document for line in page.get_text().splitlines() if line.strip()]
        result = SimpleNamespace(
            pages=[SimpleNamespace(lines=[SimpleNamespace(content=line) for line in lines])],
            content="\n".join(lines),
            key_value_pairs=[],
        )
        return SimpleNamespace(result=lambda: result)


class FakeLLM:
    """Scripted stand-in for the Azure OpenAI client.

    Side-classification requests label each image with a "Page N" text part; the fake
    answers from the scripted sides (or `classify_reply`). Verification requests echo
    the DI candidate back and record how many images each check number received.
    Workers run concurrently, so image counts are keyed by check number, not call order.
    """

    def __init__(self, sides, classify_reply=None):
        self.sides = sides
        self.classify_reply = classify_reply or self._scripted_reply
        self.classified_pages = []
        self.verify_image_counts = {}
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _scripted_reply(self, pages):
        return json.dumps({"pages": [{"page": page, "side": self.sides[page - 1]} for page in pages]})

    def _create(self, model, messages, response_format):
        content = messages[0]["content"]
        page_labels = [part["text"] for part in content[1:] if part["type"] == "text"]
        if page_labels:
            pages = [int(label.removeprefix("Page ")) for label in page_labels]
            self.classified_pages.append(pages)
            return self._reply(self.classify_reply(pages))

        di_candidate_line = next(
            line for line in content[0]["text"].splitlines() if line.startswith('{"pid_list"')
        )
        di_candidate = json.loads(di_candidate_line)
        image_count = sum(1 for part in content if part["type"] == "image_url")
        self.verify_image_counts[di_candidate["check_number"]] = image_count
        return self._reply(di_candidate_line)

    @staticmethod
    def _reply(text):
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text))])


def _upload(client, app, sides, classify_reply=None):
    from api.dependencies import get_azure_client

    llm = FakeLLM(sides, classify_reply)
    document_intelligence = FakeDocumentIntelligence()
    azure_client = SimpleNamespace(
        llm=llm,
        get_di=lambda: document_intelligence,
        di_model_id="prebuilt-check.us",
    )
    app.dependency_overrides[get_azure_client] = lambda: azure_client

    response = client.post(
        _ROUTE,
        files={"files": ("checks.pdf", _build_pdf(sides), "application/pdf")},
        data={"aid_term": "F"},
    )
    return response, llm, document_intelligence


def _excel_rows(response, tmp_path):
    """Save the returned workbook for inspection and return (PID, amount) per data row."""
    workbook_path = tmp_path / "outside_scholarships.xlsx"
    workbook_path.write_bytes(response.content)
    worksheet = load_workbook(workbook_path).active
    return [
        (pid or "", amount)
        for pid, amount, *_ in worksheet.iter_rows(min_row=_FIRST_DATA_ROW, values_only=True)
    ]


@pytest.mark.parametrize(
    ("sides", "expected_rows", "expected_image_counts"),
    [
        pytest.param(
            [FRONT],
            [("", 100.0)],
            {"1001": 1},
            id="single-front",
        ),
        pytest.param(
            [FRONT, BACK, FRONT],
            [("P0001001", 100.0), ("", 200.0)],
            {"1001": 2, "1002": 1},
            id="odd-page-count",
        ),
        pytest.param(
            [FRONT, BACK, FRONT, FRONT, BACK],
            [("P0001001", 100.0), ("", 200.0), ("P0001003", 300.0)],
            {"1001": 2, "1002": 1, "1003": 2},
            id="missing-back-in-middle",
        ),
        pytest.param(
            [FRONT, FRONT, FRONT, FRONT],
            [("", 100.0), ("", 200.0), ("", 300.0), ("", 400.0)],
            {"1001": 1, "1002": 1, "1003": 1, "1004": 1},
            id="all-fronts-even-count",
        ),
        pytest.param(
            [FRONT, BACK, FRONT, BACK],
            [("P0001001", 100.0), ("P0001002", 200.0)],
            {"1001": 2, "1002": 2},
            id="every-check-has-back",
        ),
    ],
)
def test_pages_group_into_checks_by_detected_side(
    client, override_auth, app, tmp_path, sides, expected_rows, expected_image_counts
):
    response, llm, _ = _upload(client, app, sides)

    assert response.status_code == 200, response.text
    assert _excel_rows(response, tmp_path) == expected_rows
    assert llm.verify_image_counts == expected_image_counts


@pytest.mark.parametrize(
    ("sides", "orphan_page"),
    [
        pytest.param([BACK, FRONT], 1, id="leading-back"),
        pytest.param([FRONT, BACK, BACK], 3, id="two-backs-in-a-row"),
    ],
)
def test_back_without_front_is_rejected_with_page_number(client, override_auth, app, sides, orphan_page):
    response, _, document_intelligence = _upload(client, app, sides)

    assert response.status_code == 400
    assert f"Page {orphan_page} " in response.json()["detail"]
    assert document_intelligence.calls == 0


@pytest.mark.parametrize(
    "classify_reply",
    [
        pytest.param(lambda pages: "not json", id="not-json"),
        pytest.param(
            lambda pages: json.dumps({"pages": [{"page": page, "side": FRONT} for page in pages[:-1]]}),
            id="page-missing",
        ),
        pytest.param(
            lambda pages: json.dumps({"pages": [{"page": page, "side": "sideways"} for page in pages]}),
            id="unknown-side",
        ),
    ],
)
def test_invalid_classifier_reply_fails_before_extraction(client, override_auth, app, classify_reply):
    response, _, document_intelligence = _upload(client, app, [FRONT, BACK], classify_reply)

    assert response.status_code == 500
    assert document_intelligence.calls == 0


def test_classifier_formatting_variations_are_accepted(client, override_auth, app, tmp_path):
    sides = [FRONT, BACK, FRONT]

    def loosely_formatted_reply(pages):
        return json.dumps(
            {"pages": [{"page": str(page), "side": f" {sides[page - 1].title()} "} for page in pages]}
        )

    response, _, _ = _upload(client, app, sides, loosely_formatted_reply)

    assert response.status_code == 200, response.text
    assert _excel_rows(response, tmp_path) == [("P0001001", 100.0), ("", 200.0)]


def test_pages_beyond_one_batch_keep_pdf_page_numbers(client, override_auth, app, tmp_path):
    sides = [FRONT, BACK] * 6

    response, llm, _ = _upload(client, app, sides)

    assert response.status_code == 200, response.text
    # Batches are sent concurrently, so compare them independent of arrival order.
    assert sorted(llm.classified_pages) == [list(range(1, 11)), [11, 12]]
    assert [pid for pid, _ in _excel_rows(response, tmp_path)] == [f"P{1000 + i:07d}" for i in range(1, 7)]
