from unittest.mock import MagicMock


def test_outside_scholarships_rejects_non_pdf(client, override_auth, app):
    """Validation returns 400; Depends still injects a client, but it is unused."""
    from api.dependencies import get_azure_client

    azure = MagicMock()
    app.dependency_overrides[get_azure_client] = lambda: azure

    response = client.post(
        "/api/banking/outside-scholarships",
        files={"files": ("notes.txt", b"not a pdf", "text/plain")},
        data={"aid_term": "F"},
    )
    assert response.status_code == 400
    assert "PDF" in response.json()["detail"]
    # FastAPI resolves Depends before the handler; the mock is injected but never used.
    assert azure.mock_calls == []
