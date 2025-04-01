import pytest
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from unittest.mock import patch

def test_create_short_link_anonymous(client):
    unique_url = f"https://example.com/some/very/long/url?uid={uuid4()}"
    resp = client.post("/links/shorten", json={"long_link": unique_url})
    assert resp.status_code == 200
    data = resp.json()
    assert data["long_link"] == unique_url
    assert data["auth"] is False
    assert data["user_id"] is None
    assert "short_link" in data and len(data["short_link"]) == 8
    assert data["num"] == 0
    assert data["expires_at"] is None

def test_create_short_link_authorized(client):
    unique_email = f"danya_{uuid4()}@example.com"
    register_data = {"email": unique_email, "password": "secret123"}
    client.post("/auth/register", json=register_data)
    login_resp = client.post("/auth/jwt/login", data={"username": unique_email, "password": "secret123"})
    token = login_resp.json().get("access_token")
    headers = {"Authorization": f"Bearer {token}"}

    unique_url = f"http://test.com/page?uid={uuid4()}"
    resp = client.post("/links/shorten", json={"long_link": unique_url}, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["auth"] is True
    assert data["user_id"] is not None

    resp2 = client.post("/links/shorten", json={"long_link": unique_url}, headers=headers)
    assert resp2.status_code == 400
    error = resp2.json().get("detail")
    assert "Ссылка уже существует" in error

def test_create_short_link_repeated_anonymous(client):
    unique_url = f"https://anon-duplicate-test.com/uid={uuid4()}"
    resp = client.post("/links/shorten", json={"long_link": unique_url})
    assert resp.status_code == 200
    
    resp2 = client.post("/links/shorten", json={"long_link": unique_url})
    assert resp2.status_code == 400
    detail = resp2.json()["detail"]
    assert "Ссылка уже существует" in detail

def test_create_short_link_custom_alias(client):
    custom_alias = "myalias123"
    unique_url = f"https://example.com/custom?uid={uuid4()}"
    resp = client.post("/links/shorten", json={"long_link": unique_url, "custom_alias": custom_alias})
    assert resp.status_code == 200
    data = resp.json()
    assert data["short_link"] == custom_alias
    another_url = f"https://example.com/other?uid={uuid4()}"
    resp2 = client.post("/links/shorten", json={"long_link": another_url, "custom_alias": custom_alias})
    assert resp2.status_code == 400
    error_detail = resp2.json().get("detail", "")
    assert "Custom alias уже используется" in error_detail

@pytest.mark.parametrize("url_without_scheme", [
    "example.org/path",
    "www.google.com"
])
def test_redirect_without_scheme(client, url_without_scheme):
    resp = client.post("/links/shorten", json={"long_link": url_without_scheme})
    assert resp.status_code == 200
    short_code = resp.json()["short_link"]

    redirect_resp = client.get(f"/links/?short_link={short_code}", follow_redirects=False)
    assert redirect_resp.status_code in (307, 308)
    location = redirect_resp.headers.get("location")
    assert location.startswith("http://")

def test_create_short_link_collision(client):
    with patch("src.links.router.generate_short_link", return_value="collision"):
        first_url = f"https://collision-test.com/uid={uuid4()}"
        resp1 = client.post("/links/shorten", json={"long_link": first_url})
        assert resp1.status_code == 200

    with patch("src.links.router.generate_short_link", return_value="collision"):
        second_url = f"https://collision-test.com/uid={uuid4()}"
        resp2 = client.post("/links/shorten", json={"long_link": second_url})
        assert resp2.status_code == 500
        detail = resp2.json()["detail"]
        assert "Ошибка генерации уникального alias" in detail

def test_redirect_and_stats_flow(client):
    unique_url = f"http://example.org/some/page?uid={uuid4()}"
    create_resp = client.post("/links/shorten", json={"long_link": unique_url})
    assert create_resp.status_code == 200
    link_data = create_resp.json()
    short_code = link_data["short_link"]
    assert link_data["num"] == 0

    stats_resp = client.get(f"/links/{short_code}/stats")
    assert stats_resp.status_code == 200
    stats = stats_resp.json()
    assert stats["clicks_count"] == 0

    redirect_resp = client.get(f"/links/?short_link={short_code}", follow_redirects=False)
    assert redirect_resp.status_code in (307, 308)

    stats_resp2 = client.get(f"/links/{short_code}/stats")
    assert stats_resp2.status_code == 200
    stats2 = stats_resp2.json()
    assert stats2["clicks_count"] == 1

def test_redirect_non_existing_link(client):
    resp = client.get("/links?short_link=some_random_code")
    assert resp.status_code == 404 
    detail = resp.json()["detail"]
    assert "Not Found" in detail

def test_stats_non_existing_link(client):
    resp = client.get("/links/nonexistentcode/stats")
    assert resp.status_code == 404
    detail = resp.json()["detail"]
    assert "Ссылка не найдена" in detail

def test_search_link_and_delete(client):
    unique_email = f"deluser_{uuid4()}@example.com"
    client.post("/auth/register", json={"email": unique_email, "password": "pass"})
    login_resp = client.post("/auth/jwt/login", data={"username": unique_email, "password": "pass"})
    token = login_resp.json().get("access_token")
    headers = {"Authorization": f"Bearer {token}"}

    unique_url = f"https://delete-example.com/path?uid={uuid4()}"
    create_resp = client.post("/links/shorten", json={"long_link": unique_url}, headers=headers)
    short_code = create_resp.json()["short_link"]

    search_resp = client.get(f"/links/search?long_link={unique_url}")
    assert search_resp.status_code == 200

    delete_resp = client.delete(f"/links/{short_code}", headers=headers)
    assert delete_resp.status_code == 200

def test_delete_link_of_another_user(client):
    email_a = f"userA_{uuid4()}@example.com"
    client.post("/auth/register", json={"email": email_a, "password": "passA"})
    login_resp_a = client.post("/auth/jwt/login", data={"username": email_a, "password": "passA"})
    token_a = login_resp_a.json().get("access_token")
    headers_a = {"Authorization": f"Bearer {token_a}"}

    email_b = f"userB_{uuid4()}@example.com"
    client.post("/auth/register", json={"email": email_b, "password": "passB"})
    login_resp_b = client.post("/auth/jwt/login", data={"username": email_b, "password": "passB"})
    token_b = login_resp_b.json().get("access_token")
    headers_b = {"Authorization": f"Bearer {token_b}"}

    unique_url = f"https://different-user.com/path?uid={uuid4()}"
    create_resp = client.post("/links/shorten", json={"long_link": unique_url}, headers=headers_a)
    short_code = create_resp.json()["short_link"]
    
    resp = client.delete(f"/links/{short_code}", headers=headers_b)
    assert resp.status_code == 404


@patch('src.links.router.delete_expired_link.apply_async')
def test_delete_expired_link_task(mock_celery, client):
    unique_url = f"http://todelete.com?uid={uuid4()}"
    expires_at = datetime(2100, 1, 1, 0, 0, tzinfo=timezone.utc)
    resp = client.post(
        "/links/shorten",
        json={
            "long_link": unique_url,
            "expires_at": expires_at.isoformat()
        }
    )
    assert resp.status_code == 200
    link_id = resp.json()["id"]

    mock_celery.assert_called_once_with(
        args=[link_id],
        eta=expires_at,
        queue='celery'
    )

def test_update_link(client):
    unique_email = f"updateuser_{uuid4()}@example.com"
    client.post("/auth/register", json={"email": unique_email, "password": "pass"})
    login_resp = client.post("/auth/jwt/login", data={"username": unique_email, "password": "pass"})
    token = login_resp.json().get("access_token")
    headers = {"Authorization": f"Bearer {token}"}

    original_url = f"http://original.com/path?uid={uuid4()}"
    create_resp = client.post("/links/shorten", json={"long_link": original_url}, headers=headers)
    short_code = create_resp.json()["short_link"]

    new_url = f"http://updated.com/path?uid={uuid4()}"
    update_resp = client.put(f"/links/{short_code}", json={"new_long_link": new_url}, headers=headers)
    assert update_resp.status_code == 200
    assert update_resp.json()["long_link"] == new_url

def test_update_link_of_another_user(client):
    email_a = f"userA_{uuid4()}@example.com"
    client.post("/auth/register", json={"email": email_a, "password": "passA"})
    login_resp_a = client.post("/auth/jwt/login", data={"username": email_a, "password": "passA"})
    token_a = login_resp_a.json().get("access_token")
    headers_a = {"Authorization": f"Bearer {token_a}"}

    email_b = f"userB_{uuid4()}@example.com"
    client.post("/auth/register", json={"email": email_b, "password": "passB"})
    login_resp_b = client.post("/auth/jwt/login", data={"username": email_b, "password": "passB"})
    token_b = login_resp_b.json().get("access_token")
    headers_b = {"Authorization": f"Bearer {token_b}"}

    unique_url = f"https://belongs-to-A.com/path?uid={uuid4()}"
    create_resp = client.post("/links/shorten", json={"long_link": unique_url}, headers=headers_a)
    short_code = create_resp.json()["short_link"]
    
    new_url = f"http://newurl-for-B.com/path?uid={uuid4()}"
    update_resp = client.put(f"/links/{short_code}", json={"new_long_link": new_url}, headers=headers_b)
    assert update_resp.status_code == 404

@patch('src.links.router.delete_expired_link.apply_async')
def test_get_expired_links(mock_celery, client):
    unique_url = f"http://expired.com/path?uid={uuid4()}"
    past_time = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    resp = client.post("/links/shorten", json={"long_link": unique_url, "expires_at": past_time})
    assert resp.status_code == 200

    expired_resp = client.get("/links/expired")
    assert expired_resp.status_code == 200
    expired_links = expired_resp.json()
    assert any(link["long_link"] == unique_url for link in expired_links)

@patch('src.links.router.delete_expired_link.apply_async')
def test_expired_link_redirect(mock_celery, client):
    unique_url = f"http://expired-redirect.com/path?uid={uuid4()}"
    past_time = datetime.now(timezone.utc) - timedelta(days=2)
    resp = client.post("/links/shorten", json={"long_link": unique_url, "expires_at": past_time.isoformat()})
    assert resp.status_code == 200
    short_code = resp.json()["short_link"]

    redirect_resp = client.get(f"/links/?short_link={short_code}")
    assert redirect_resp.status_code == 404
    assert "Ссылка истекла" in redirect_resp.json()["detail"]


def test_cache_invalidation_on_delete(client):
    email = f"deletecache_{uuid4()}@example.com"
    client.post("/auth/register", json={"email": email, "password": "pass"})
    login_resp = client.post("/auth/jwt/login", data={"username": email, "password": "pass"})
    token = login_resp.json().get("access_token")
    headers = {"Authorization": f"Bearer {token}"}

    url_to_del = f"http://shoulddelete-cache.com/{uuid4()}"
    resp_create = client.post("/links/shorten", json={"long_link": url_to_del}, headers=headers)
    short_code = resp_create.json()["short_link"]

    client.get(f"/links/?short_link={short_code}")

    client.delete(f"/links/{short_code}", headers=headers)
    resp_get_after_del = client.get(f"/links/?short_link={short_code}")
    assert resp_get_after_del.status_code == 404

