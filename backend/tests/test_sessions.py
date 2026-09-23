from unittest.mock import MagicMock


def test_get_user_sessions_with_mocked_cosmos(client, override_auth, app):
    from api.dependencies import get_cosmos_client

    fake_sessions = [
        {"id": "s1", "user_id": "u1", "title": "Chat 1"},
        {"id": "s2", "user_id": "u1", "title": "Chat 2"},
    ]
    cosmos = MagicMock()
    cosmos.get_sessions_for_user_id.return_value = fake_sessions
    app.dependency_overrides[get_cosmos_client] = lambda: cosmos

    response = client.get("/api/sessions/u1")
    assert response.status_code == 200
    body = response.json()
    assert body["user_id"] == "u1"
    assert body["count"] == 2
    assert body["sessions"] == fake_sessions
    cosmos.get_sessions_for_user_id.assert_called_once_with("u1")
