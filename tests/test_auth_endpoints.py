import pytest

def test_register_and_login_flow(client):
    register_data = {"email": "user@example.com", "password": "strongpassword"}
    response = client.post("/auth/register", json=register_data)
    assert response.status_code == 201, "Регистрация должна возвращать 201 Created"
    data = response.json()
    assert data["email"] == "user@example.com"
    assert "id" in data

    response2 = client.post("/auth/register", json=register_data)
    assert response2.status_code in (400, 409), "Повторная регистрация должна возвращать ошибку"

def test_login_with_valid_and_invalid_credentials(client):
    login_data = {"username": "user@example.com", "password": "strongpassword"}
    resp = client.post("/auth/jwt/login", data=login_data)
    assert resp.status_code == 200, "Логин с верными данными должен вернуть 200"
    assert "access_token" in resp.json() or "access-token" in resp.headers.get("set-cookie", "").lower()

    bad_login = {**login_data, "password": "wrongpass"}
    resp2 = client.post("/auth/jwt/login", data=bad_login)
    assert resp2.status_code in (400, 401), "Логин с неверными данными должен вернуть ошибку"
    if resp2.status_code == 400:
        detail = resp2.json().get("detail")
        assert detail == "LOGIN_BAD_CREDENTIALS"
