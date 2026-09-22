from unittest.mock import MagicMock


def test_outside_scholarships_rejects_non_pdf(client, override_auth, app):
    """Invalid content type fails with 400; Azure methods are never called."""
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
    azure.assert_not_called()
