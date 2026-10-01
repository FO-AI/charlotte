"""Outside-scholarships PDF upload size guard."""

from types import SimpleNamespace

from api.dependencies import get_azure_client
from outside_scholarships_fakes import FRONT, ROUTE, FakeLLM, scripted_pages, upload
from services.banking.outside_scholarships import service as os_service


def test_upload_rejects_pdf_over_max_bytes(client, override_auth, app, monkeypatch):
    monkeypatch.setattr(os_service, "MAX_UPLOAD_BYTES", 64)
    # Satisfy the azure_client dependency without touching real Azure (same as upload()).
    llm = FakeLLM(scripted_pages([FRONT]))
    app.dependency_overrides[get_azure_client] = lambda: SimpleNamespace(llm=llm)

    # Minimal PDF header so the route accepts the content type; body exceeds the patched cap.
    oversized = b"%PDF-1.1\n" + (b"x" * 128)
    response = client.post(
        ROUTE,
        files={"files": ("big.pdf", oversized, "application/pdf")},
        data={"aid_term": "F"},
    )
    assert response.status_code == 400, response.text
    assert "too large" in response.json()["detail"].lower()


def test_upload_accepts_pdf_under_max_bytes(client, override_auth, app, monkeypatch):
    monkeypatch.setattr(os_service, "MAX_UPLOAD_BYTES", 5 * 1024 * 1024)
    response, _llm = upload(client, app, [FRONT])
    assert response.status_code == 200, response.text
