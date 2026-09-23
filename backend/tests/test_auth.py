def test_user_department_requires_auth(client):
    response = client.get("/auth/user-department")
    assert response.status_code == 403


def test_user_department_with_override(client, override_auth):
    response = client.get("/auth/user-department")
    assert response.status_code == 200
    assert response.json() == {"department": "admin"}
