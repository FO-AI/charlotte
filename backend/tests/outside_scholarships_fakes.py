"""Fakes shared by the outside-scholarship E2E tests. No real Azure or Graph access.

Every generated page is filled with a colour that encodes its page index, so the fake LLM
can tell from an image alone which page it was sent, and every assertion reflects which
pages actually reached each check. Fronts belong to a check number and amount; backs
carry the PIDs written on them. Microsoft Graph is an httpx MockTransport answering
`employeeId in (...)` filters from an in-memory directory.
"""

import base64
import json
import re
import struct
import threading
import time
from dataclasses import dataclass
from types import SimpleNamespace
from typing import List, Optional

import fitz
import httpx

from services.banking.outside_scholarships.nodes import PYMUPDF_LOCK

FRONT = "front"
BACK = "back"
ROUTE = "/api/banking/outside-scholarships"
EXPORT_ROUTE = "/api/banking/outside-scholarships/export"
LOOKUP_ROUTE = "/api/banking/outside-scholarships/active-directory-names"
FIRST_DATA_ROW = 6
REVIEW_FIRST_DATA_ROW = 7
HEADER_ROW = 5
REVIEW_HEADER_ROW = 6
FIRST_CHECK_NUMBER = 1001

_FILTER_VALUE_RE = re.compile(r"'((?:[^']|'')*)'")
# A page's index is written as three 4-bit colour channels, each scaled to 0-255 in steps of 17.
_MARKER_CHANNEL_SHIFTS = (8, 4, 0)
_MARKER_CHANNEL_MAX = 15
_MARKER_CHANNEL_STEP = 17
_PNG_SIZE_OFFSET = slice(16, 24)


def default_pid(check_number):
    """The nine-digit PID written on a check's back when a test does not choose one."""
    return f"730{check_number:06d}"


def check_amount(check_number):
    return f"{(check_number - 1000) * 100}.00"


@dataclass(frozen=True)
class ScriptedPage:
    """What one page of a generated PDF shows. `pids` is None on a front."""

    page_number: int
    side: str
    check_number: int
    pids: Optional[List[str]]


def scripted_pages(sides, back_pids=None):
    """One page per side. A back belongs to the check whose front comes before it.

    `back_pids` maps a check number to the PID, or list of raw PID strings, written on its
    back; checks it does not name get `default_pid`.
    """
    back_pids = back_pids or {}
    pages = []
    check_number = FIRST_CHECK_NUMBER - 1
    for page_number, side in enumerate(sides, start=1):
        pids = None
        if side == FRONT:
            check_number += 1
        else:
            written = back_pids.get(check_number, default_pid(check_number))
            pids = [written] if isinstance(written, str) else list(written)
        pages.append(ScriptedPage(page_number, side, check_number, pids))
    return pages


def _marker_color(page_index):
    return tuple(((page_index >> shift) & _MARKER_CHANNEL_MAX) / _MARKER_CHANNEL_MAX for shift in _MARKER_CHANNEL_SHIFTS)


def build_pdf(pages):
    document = fitz.open()
    for page_index, scripted in enumerate(pages):
        page = document.new_page()
        page.draw_rect(page.rect, color=None, fill=_marker_color(page_index))
        if scripted.side == FRONT:
            page.insert_text((72, 72), f"Check No: {scripted.check_number}")
            page.insert_text((72, 100), f"Amount: ${check_amount(scripted.check_number)}")
        else:
            page.insert_text((72, 72), f"PID: {', '.join(scripted.pids)}")
    return document.tobytes()


def _page_index_from_png(png_bytes):
    """Read back the marker colour, sampled below the text, that build_pdf filled the page with."""
    with PYMUPDF_LOCK:
        pixmap = fitz.Pixmap(png_bytes)
        pixel = pixmap.pixel(pixmap.width // 2, 3 * pixmap.height // 4)
    return sum(round(value / _MARKER_CHANNEL_STEP) << shift for value, shift in zip(pixel, _MARKER_CHANNEL_SHIFTS))


def _png_size(png_bytes):
    return struct.unpack(">II", png_bytes[_PNG_SIZE_OFFSET])


class _InFlight:
    """Counts calls in progress and the most that were ever in progress at once."""

    def __init__(self):
        self._lock = threading.Lock()
        self.current = 0
        self.peak = 0

    def __enter__(self):
        with self._lock:
            self.current += 1
            self.peak = max(self.peak, self.current)

    def __exit__(self, *exc_info):
        with self._lock:
            self.current -= 1


class FakeLLM:
    """Scripted stand-in for the Azure OpenAI client.

    Side classification: each thumbnail is labelled "Page N", and the reply comes from the
    scripted sides (or `classify_reply(pages)`).

    Extraction: the fake finds each image's page from its marker colour, fails the call
    unless the images are one check's front followed by, at most, the back right after it,
    and replies with that check's fields (or `extraction_reply(check_number, fields)`).
    Workers run concurrently, so what each check received is keyed by check number.

    `classification_delay(first_page)`, `classification_barrier` and
    `extraction_delay(check_number)` let a test hold calls open to observe concurrency.
    """

    def __init__(
        self,
        pages,
        classify_reply=None,
        extraction_reply=None,
        classification_delay=lambda first_page: 0.0,
        classification_barrier=None,
        extraction_delay=lambda check_number: 0.0,
    ):
        self.pages = pages
        self.classify_reply = classify_reply or self._scripted_sides
        self.extraction_reply = extraction_reply or (lambda check_number, fields: json.dumps(fields))
        self.classification_delay = classification_delay
        self.classification_barrier = classification_barrier
        self.extraction_delay = extraction_delay
        self.classifications = _InFlight()
        self.extractions = _InFlight()
        self._lock = threading.Lock()
        self.classified_pages = []
        self.image_sizes_by_check = {}
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    @property
    def extraction_calls(self):
        return len(self.image_sizes_by_check)

    def image_counts_by_check(self):
        return {check_number: len(sizes) for check_number, sizes in self.image_sizes_by_check.items()}

    def _scripted_sides(self, pages):
        return json.dumps({"pages": [{"page": page, "side": self.pages[page - 1].side} for page in pages]})

    def _create(self, model, messages, response_format):
        content = messages[0]["content"]
        page_labels = [part["text"] for part in content[1:] if part["type"] == "text"]
        if page_labels:
            return self._classify([int(label.removeprefix("Page ")) for label in page_labels])
        return self._extract([part for part in content if part["type"] == "image_url"])

    def _classify(self, pages):
        with self._lock:
            self.classified_pages.append(pages)
        with self.classifications:
            if self.classification_barrier is not None:
                self.classification_barrier.wait()
            time.sleep(self.classification_delay(pages[0]))
        return self._reply(self.classify_reply(pages))

    def _extract(self, image_parts):
        images = [base64.b64decode(part["image_url"]["url"].split(",", 1)[1]) for part in image_parts]
        front, *backs = [self.pages[_page_index_from_png(image)] for image in images]
        assert front.side == FRONT, f"extraction started with page {front.page_number}, a {front.side}"
        assert len(backs) <= 1, f"check {front.check_number} was sent {len(images)} images"
        for back in backs:
            assert (back.side, back.page_number) == (BACK, front.page_number + 1), (
                f"check {front.check_number} was sent page {back.page_number} as its back"
            )

        with self._lock:
            assert front.check_number not in self.image_sizes_by_check, f"check {front.check_number} extracted twice"
            self.image_sizes_by_check[front.check_number] = [_png_size(image) for image in images]
        with self.extractions:
            time.sleep(self.extraction_delay(front.check_number))

        check_number = front.check_number
        fields = {
            "pid_list": backs[0].pids if backs else [],
            "amount": check_amount(check_number),
            "check_number": str(check_number),
            "name": f"Payee {check_number}",
            "provider": f"Provider {check_number}",
            "scholarship_name": f"Scholarship {check_number}",
        }
        return self._reply(self.extraction_reply(check_number, fields))

    @staticmethod
    def _reply(text):
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text))])


def graph_user(employee_id, given_name=None, surname=None, display_name=None):
    """A Graph /users record with the properties the lookup selects."""
    return {
        "employeeId": employee_id,
        "givenName": given_name,
        "surname": surname,
        "displayName": display_name,
    }


class FakeGraph:
    """Microsoft Graph /users stand-in, keyed by employeeId.

    Answers `$filter=employeeId in ('a','b')` from `user_by_pid`, or fails every request
    with `status_code` / a network error. Every request is kept for assertions.
    """

    def __init__(self, user_by_pid=None, status_code=200, network_error=False):
        self.user_by_pid = user_by_pid or {}
        self.status_code = status_code
        self.network_error = network_error
        self.requests = []
        self.transport = httpx.MockTransport(self._handle)

    def requested_pids(self, request):
        return [value.replace("''", "'") for value in _FILTER_VALUE_RE.findall(request.url.params["$filter"])]

    def all_requested_pids(self):
        return [pid for request in self.requests for pid in self.requested_pids(request)]

    def _handle(self, request):
        self.requests.append(request)
        if self.network_error:
            raise httpx.ConnectError("graph.microsoft.com unreachable", request=request)
        if self.status_code != 200:
            return httpx.Response(
                self.status_code,
                json={"error": {"code": "Authorization_RequestDenied", "message": "Insufficient privileges."}},
            )
        users = [self.user_by_pid[pid] for pid in self.requested_pids(request) if pid in self.user_by_pid]
        return httpx.Response(200, json={"value": users})


def upload(client, app, sides, back_pids=None, graph=None, **llm_options):
    """POST a generated check PDF through the real route with the LLM and Graph faked.

    The fake Azure client has an LLM and nothing else, so no Document Intelligence is
    available. Without `graph`, conftest's empty offline directory answers the lookup.
    `llm_options` go to FakeLLM. On success the response body is the review preview JSON.
    """
    from api.dependencies import get_azure_client, get_graph_user_directory
    from services.azure_services import GraphUserDirectory

    pages = scripted_pages(sides, back_pids)
    llm = FakeLLM(pages, **llm_options)
    app.dependency_overrides[get_azure_client] = lambda: SimpleNamespace(llm=llm)
    if graph is not None:
        app.dependency_overrides[get_graph_user_directory] = lambda: GraphUserDirectory(transport=graph.transport)

    response = client.post(
        ROUTE,
        files={"files": ("checks.pdf", build_pdf(pages), "application/pdf")},
        data={"aid_term": "F"},
    )
    return response, llm


def preview_payload(response):
    assert response.headers["content-type"].startswith("application/json")
    return response.json()


def preview_pid_amount_rows(response):
    """(PID, amount) rows implied by the preview: one row per PID, or one blank-PID row."""
    rows = []
    for check in preview_payload(response)["checks"]:
        amount = float(check["amount"]) if check.get("amount") is not None else 0.0
        pids = check.get("pids") or []
        if not pids:
            rows.append(("", amount))
            continue
        for entry in pids:
            rows.append((entry.get("pid") or "", amount))
    return rows


def ad_display_name(entry):
    ad = entry.get("active_directory") or {}
    if ad.get("status") == "found":
        return ad.get("name") or ""
    if ad.get("status") == "lookup_failed":
        return "Lookup failed"
    return ""


def preview_pid_and_directory_name_rows(response):
    rows = []
    for check in preview_payload(response)["checks"]:
        pids = check.get("pids") or []
        if not pids:
            rows.append(("", ""))
            continue
        for entry in pids:
            rows.append((entry.get("pid") or "", ad_display_name(entry)))
    return rows


def export_payload_from_preview(preview, verified_indexes=None):
    """Build an export body that treats preview values as both extracted and reviewed."""
    verified_indexes = set(verified_indexes or [])
    checks = []
    for check in preview.get("checks") or []:
        index = check.get("check_index")
        extracted_fields = {
            "amount": check.get("amount"),
            "check_number": check.get("check_number"),
            "name": check.get("name"),
            "provider": check.get("provider"),
            "scholarship_name": check.get("scholarship_name"),
            "pids": list(check.get("pids") or []),
        }
        checks.append(
            {
                "check_index": index,
                "extracted": extracted_fields,
                "reviewed": {
                    **extracted_fields,
                    "pids": [dict(entry) for entry in (check.get("pids") or [])],
                },
                "verified": index in verified_indexes,
            }
        )
    return {
        "aid_year": preview.get("aid_year"),
        "aid_term": preview.get("aid_term"),
        "checks": checks,
    }


def export_excel(client, app, preview, verified_indexes=None, graph=None):
    """POST the export route for a preview payload; returns the Excel response."""
    from api.dependencies import get_azure_client, get_graph_user_directory
    from services.azure_services import GraphUserDirectory

    app.dependency_overrides[get_azure_client] = lambda: SimpleNamespace(llm=None)
    if graph is not None:
        app.dependency_overrides[get_graph_user_directory] = lambda: GraphUserDirectory(transport=graph.transport)

    response = client.post(EXPORT_ROUTE, json=export_payload_from_preview(preview, verified_indexes))
    return response
