"""Fakes shared by the outside-scholarship E2E tests. No real Azure or Graph access.

Document Intelligence and the LLM read the text PyMuPDF writes onto each test page, so
every assertion reflects which pages actually reached each check: fronts carry the
check number and amount, backs carry the PID. Microsoft Graph is an httpx
MockTransport answering `employeeId in (...)` filters from an in-memory directory.
"""

import json
import re
from types import SimpleNamespace

import fitz
import httpx

FRONT = "front"
BACK = "back"
ROUTE = "/api/banking/outside-scholarships"
FIRST_DATA_ROW = 6
HEADER_ROW = 5
FIRST_CHECK_NUMBER = 1001

_FILTER_VALUE_RE = re.compile(r"'((?:[^']|'')*)'")


def build_pdf(sides, back_pids=None):
    """One page per side. A back carries the PID of the check whose front precedes it.

    `back_pids` maps a check number to the PID printed on its back; checks it does not
    name get P + the zero-padded check number.
    """
    back_pids = back_pids or {}
    document = fitz.open()
    check_number = FIRST_CHECK_NUMBER - 1
    for side in sides:
        page = document.new_page()
        if side == FRONT:
            check_number += 1
            page.insert_text((72, 72), f"Check No: {check_number}")
            page.insert_text((72, 100), f"Amount: ${(check_number - 1000) * 100}.00")
        else:
            page.insert_text((72, 72), f"PID: {back_pids.get(check_number, f'P{check_number:07d}')}")
    return document.tobytes()


class FakeDocumentIntelligence:
    """Returns the text written on each page of the check PDF, like DI OCR would."""

    def __init__(self):
        self.calls = 0

    def begin_analyze_document(self, model_id, request=None, **kwargs):
        self.calls += 1
        pdf_bytes = request.bytes_source if request is not None else kwargs["body"]
        with fitz.open(stream=pdf_bytes, filetype="pdf") as document:
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

    Answers `$filter=employeeId in ('a','b')` from `users_by_pid`, or fails every request
    with `status_code` / a network error. Every request is kept for assertions.
    """

    def __init__(self, users_by_pid=None, status_code=200, network_error=False):
        self.users_by_pid = users_by_pid or {}
        self.status_code = status_code
        self.network_error = network_error
        self.requests = []
        self.transport = httpx.MockTransport(self._handle)

    def requested_pids(self, request):
        return [value.replace("''", "'") for value in _FILTER_VALUE_RE.findall(request.url.params["$filter"])]

    def _handle(self, request):
        self.requests.append(request)
        if self.network_error:
            raise httpx.ConnectError("graph.microsoft.com unreachable", request=request)
        if self.status_code != 200:
            return httpx.Response(
                self.status_code,
                json={"error": {"code": "Authorization_RequestDenied", "message": "Insufficient privileges."}},
            )
        users = [user for pid in self.requested_pids(request) for user in self.users_by_pid.get(pid, [])]
        return httpx.Response(200, json={"value": users})


def upload(client, app, sides, classify_reply=None, back_pids=None, graph=None):
    """POST a generated check PDF through the real route with Azure and Graph faked."""
    from api.dependencies import get_azure_client, get_graph_user_directory
    from services.azure_services import GraphUserDirectory

    llm = FakeLLM(sides, classify_reply)
    document_intelligence = FakeDocumentIntelligence()
    azure_client = SimpleNamespace(
        llm=llm,
        get_di=lambda: document_intelligence,
        di_model_id="prebuilt-check.us",
    )
    graph = graph or FakeGraph()
    app.dependency_overrides[get_azure_client] = lambda: azure_client
    app.dependency_overrides[get_graph_user_directory] = lambda: GraphUserDirectory(transport=graph.transport)

    response = client.post(
        ROUTE,
        files={"files": ("checks.pdf", build_pdf(sides, back_pids), "application/pdf")},
        data={"aid_term": "F"},
    )
    return response, llm, document_intelligence
