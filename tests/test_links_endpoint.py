import pytest
from datetime import datetime, timedelta
from uuid import uuid4
from unittest.mock import patch

# Все тесты предполагают наличие фикстуры `client` (TestClient) и, возможно, других
# фикстур для базы данных, если вы их используете. Ниже я использую "client", как
# обычно бывает при тестировании FastAPI.

def test_create_short_link_anonymous(client):
    """
    Анонимное сокращение ссылки.
    1. Отправляем POST без токена.
    2. Проверяем корректность ответа (успешно, нет user_id).
    """
    unique_url = f"https://example.com/some/very/long/url?uid={uuid4()}"
    resp = client.post("/links/shorten", json={"long_link": unique_url})
    assert resp.status_code == 200, "Анонимное сокращение ссылки должно быть успешно"
    data = resp.json()
    assert data["long_link"] == unique_url
    assert data["auth"] is False
    assert data["user_id"] is None
    assert "short_link" in data and len(data["short_link"]) == 8
    assert data["num"] == 0
    assert data["expires_at"] is None


def test_create_short_link_authorized(client):
    """
    Сокращение ссылки авторизованным пользователем.
    1. Регистрируем и логиним нового юзера.
    2. Создаем ссылку.
    3. Повторно пробуем создать ту же ссылку (должна быть ошибка 400).
    """
    unique_email = f"john_{uuid4()}@example.com"
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

    # Попытка создать ту же ссылку снова
    resp2 = client.post("/links/shorten", json={"long_link": unique_url}, headers=headers)
    assert resp2.status_code == 400
    error = resp2.json().get("detail")
    assert "Ссылка уже существует" in error


def test_create_short_link_repeated_anonymous(client):
    """
    Повторное сокращение той же ссылки (без авторизации).
    Должно вернуть ошибку 400 (Ссылка уже существует).
    """
    unique_url = f"https://anon-duplicate-test.com/uid={uuid4()}"
    # Создаём первый раз
    resp = client.post("/links/shorten", json={"long_link": unique_url})
    assert resp.status_code == 200
    
    # Пытаемся создать второй раз ту же самую ссылку анонимно
    resp2 = client.post("/links/shorten", json={"long_link": unique_url})
    assert resp2.status_code == 400
    detail = resp2.json()["detail"]
    assert "Ссылка уже существует" in detail


def test_create_short_link_custom_alias(client):
    """
    Проверка custom_alias:
    1. Создать новую ссылку с заданным alias.
    2. Убедиться, что alias совпадает.
    3. Повторно создать с тем же alias - ошибка 400.
    """
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
    "example.org/path",        # без http/https
    "www.google.com",          # тоже без явного http/https
])
def test_redirect_without_scheme(client, url_without_scheme):
    """
    Проверяем, что если ссылка не начинается с http или https,
    при редиректе префикс "http://" автоматически подставляется.
    """
    resp = client.post("/links/shorten", json={"long_link": url_without_scheme})
    assert resp.status_code == 200
    short_code = resp.json()["short_link"]

    # Для отключения реального редиректа используем follow_redirects=False
    redirect_resp = client.get(f"/links/?short_link={short_code}", follow_redirects=False)
    assert redirect_resp.status_code in (307, 308), "Должен быть редирект"
    location = redirect_resp.headers.get("location")
    assert location.startswith("http://"), "Ссылка без схемы должна получить http:// автоматически"


def test_create_short_link_collision(client):
    """
    Тест искусственной коллизии alias. Если generate_short_link
    возвращает уже существующий код, должен быть HTTP 500.
    Используем patch, чтобы 'подделать' возвращаемое значение функции.
    """
    # Сначала создаём какую-то ссылку, чтобы в базе точно был short_link="collision"
    first_url = f"https://collision-test.com/uid={uuid4()}"
    with patch("links.router.generate_short_link", return_value="collision"):
        resp1 = client.post("/links/shorten", json={"long_link": first_url})
        assert resp1.status_code == 200, "Первый вызов должен быть успешным (collision раньше не было)"

    # Теперь второй вызов с тем же mocked short_link должен упасть с 500
    second_url = f"https://collision-test.com/uid={uuid4()}"
    with patch("links.router.generate_short_link", return_value="collision"):
        resp2 = client.post("/links/shorten", json={"long_link": second_url})
        assert resp2.status_code == 500
        detail = resp2.json()["detail"]
        assert "Ошибка генерации уникального alias" in detail


def test_redirect_and_stats_flow(client):
    """
    1. Создаем ссылку.
    2. Проверяем её статистику (click=0).
    3. Делаем GET /links/?short_link=... (редирект).
    4. Проверяем статистику снова (click=1, last_used обновлён).
    """
    unique_url = f"http://example.org/some/page?uid={uuid4()}"
    create_resp = client.post("/links/shorten", json={"long_link": unique_url})
    assert create_resp.status_code == 200
    link_data = create_resp.json()
    short_code = link_data["short_link"]
    assert link_data["num"] == 0

    stats_resp = client.get(f"/links/{short_code}/stats")
    assert stats_resp.status_code == 200
    stats = stats_resp.json()
    assert stats["long_link"] == unique_url
    assert stats["clicks_count"] == 0
    created = datetime.fromisoformat(stats["created_at"].replace("Z", "+00:00"))
    last_used = datetime.fromisoformat(stats["last_used"].replace("Z", "+00:00"))
    assert abs((last_used - created).total_seconds()) < 1

    # делаем редирект
    redirect_resp = client.get(f"/links/?short_link={short_code}", follow_redirects=False)
    assert redirect_resp.status_code in (307, 308)
    location = redirect_resp.headers.get("location")
    assert location is not None
    # Либо точно совпадает, либо начинается (если где-то могли добавляться параметры)
    assert location == unique_url or location.startswith(unique_url)

    # Проверяем, что num увеличился
    stats_resp2 = client.get(f"/links/{short_code}/stats")
    assert stats_resp2.status_code == 200
    stats2 = stats_resp2.json()
    assert stats2["clicks_count"] == 1
    assert stats2["last_used"] >= stats2["created_at"]


def test_redirect_non_existing_link(client):
    """
    Пытаемся редиректнуться по несуществующему short_link. Должен вернуть 404.
    """
    resp = client.get("/links/?short_link=some_random_code", follow_redirects=False)
    assert resp.status_code == 404
    detail = resp.json()["detail"]
    assert "Ссылка не найдена" in detail


def test_stats_non_existing_link(client):
    """
    Запрашиваем статистику по несуществующему short_code. Ожидаем 404.
    """
    resp = client.get("/links/nonexistentcode/stats")
    assert resp.status_code == 404
    detail = resp.json()["detail"]
    assert "Ссылка не найдена" in detail


def test_search_link_and_delete(client):
    """
    1. Регистрируемся, логинимся.
    2. Создаем ссылку.
    3. /links/search по long_link -> short_link
    4. Удаляем ссылку.
    5. Повторное удаление -> 404.
    """
    unique_email = f"deluser_{uuid4()}@example.com"
    client.post("/auth/register", json={"email": unique_email, "password": "pass"})
    login_resp = client.post("/auth/jwt/login", data={"username": unique_email, "password": "pass"})
    token = login_resp.json().get("access_token")
    headers = {"Authorization": f"Bearer {token}"}

    unique_url = f"https://delete-example.com/path?uid={uuid4()}"
    create_resp = client.post("/links/shorten", json={"long_link": unique_url}, headers=headers)
    assert create_resp.status_code == 200
    data = create_resp.json()
    short_code = data["short_link"]

    # Поиск
    search_resp = client.get(f"/links/search?long_link={unique_url}")
    assert search_resp.status_code == 200
    found_code = search_resp.json()
    assert found_code == short_code

    resp_404 = client.get("/links/search?long_link=https://no-such-link.com/")
    assert resp_404.status_code == 404
    err = resp_404.json().get("detail")
    assert "не найдена" in err

    # Удаляем
    delete_resp = client.delete(f"/links/{short_code}", headers=headers)
    assert delete_resp.status_code == 200
    msg = delete_resp.json().get("detail", "")
    assert "успешно удалена" in msg

    delete_resp2 = client.delete(f"/links/{short_code}", headers=headers)
    assert delete_resp2.status_code == 404


def test_delete_link_of_another_user(client):
    """
    Проверяем попытку удалить чужую ссылку:
    1. Пользователь А создаёт ссылку.
    2. Пользователь B пытается её удалить -> 404 "Ссылка не найдена или доступ запрещён."
    """
    # Пользователь A
    email_a = f"userA_{uuid4()}@example.com"
    client.post("/auth/register", json={"email": email_a, "password": "passA"})
    login_resp_a = client.post("/auth/jwt/login", data={"username": email_a, "password": "passA"})
    token_a = login_resp_a.json().get("access_token")
    headers_a = {"Authorization": f"Bearer {token_a}"}

    # Пользователь B
    email_b = f"userB_{uuid4()}@example.com"
    client.post("/auth/register", json={"email": email_b, "password": "passB"})
    login_resp_b = client.post("/auth/jwt/login", data={"username": email_b, "password": "passB"})
    token_b = login_resp_b.json().get("access_token")
    headers_b = {"Authorization": f"Bearer {token_b}"}

    unique_url = f"https://different-user.com/path?uid={uuid4()}"
    create_resp = client.post("/links/shorten", json={"long_link": unique_url}, headers=headers_a)
    short_code = create_resp.json()["short_link"]
    
    # B пытается удалить ссылку A
    resp = client.delete(f"/links/{short_code}", headers=headers_b)
    assert resp.status_code == 404
    detail = resp.json().get("detail", "")
    assert "не найдена" in detail or "доступ запрещён" in detail


def test_delete_expired_link_task(client):
    """
    Проверяем, что создание ссылки с будущей датой не ломается,
    а таска delete_expired_link вызывается (в коде).
    Фактическое удаление celery сделает по истечении времени, поэтому
    тест просто проверяет статус и отсутствие ошибок.
    """
    unique_url = f"http://todelete.com?uid={uuid4()}"
    expires_at = "2100-01-01T00:00:00Z"  # Очень далёкое будущее
    resp = client.post("/links/shorten", json={"long_link": unique_url, "expires_at": expires_at})
    assert resp.status_code == 200


def test_update_link(client):
    """
    1. Регистрируем и логиним пользователя.
    2. Создаем ссылку.
    3. Обновляем ссылку (меняем long_link).
    4. Проверяем, что ссылка обновлена.
    """
    unique_email = f"updateuser_{uuid4()}@example.com"
    client.post("/auth/register", json={"email": unique_email, "password": "pass"})
    login_resp = client.post("/auth/jwt/login", data={"username": unique_email, "password": "pass"})
    token = login_resp.json().get("access_token")
    headers = {"Authorization": f"Bearer {token}"}
    
    # Создаем исходную ссылку
    original_url = f"http://original.com/path?uid={uuid4()}"
    create_resp = client.post("/links/shorten", json={"long_link": original_url}, headers=headers)
    assert create_resp.status_code == 200
    short_code = create_resp.json()["short_link"]
    
    # Обновляем ссылку
    new_url = f"http://updated.com/path?uid={uuid4()}"
    update_resp = client.put(f"/links/{short_code}", json={"new_long_link": new_url}, headers=headers)
    assert update_resp.status_code == 200
    updated_link = update_resp.json()
    assert updated_link["long_link"] == new_url, "Ссылка должна быть обновлена до нового значения"


def test_update_link_of_another_user(client):
    """
    Попытка изменить ссылку, созданную другим пользователем.
    Ожидаем 404 "Ссылка не найдена или доступ запрещён."
    """
    # Пользователь A
    email_a = f"userA_{uuid4()}@example.com"
    client.post("/auth/register", json={"email": email_a, "password": "passA"})
    login_resp_a = client.post("/auth/jwt/login", data={"username": email_a, "password": "passA"})
    token_a = login_resp_a.json().get("access_token")
    headers_a = {"Authorization": f"Bearer {token_a}"}

    # Пользователь B
    email_b = f"userB_{uuid4()}@example.com"
    client.post("/auth/register", json={"email": email_b, "password": "passB"})
    login_resp_b = client.post("/auth/jwt/login", data={"username": email_b, "password": "passB"})
    token_b = login_resp_b.json().get("access_token")
    headers_b = {"Authorization": f"Bearer {token_b}"}

    # A создаёт ссылку
    unique_url = f"https://belongs-to-A.com/path?uid={uuid4()}"
    create_resp = client.post("/links/shorten", json={"long_link": unique_url}, headers=headers_a)
    short_code = create_resp.json()["short_link"]
    
    # B пытается обновить
    new_url = f"http://newurl-for-B.com/path?uid={uuid4()}"
    update_resp = client.put(f"/links/{short_code}", json={"new_long_link": new_url}, headers=headers_b)
    assert update_resp.status_code == 404
    detail = update_resp.json().get("detail", "")
    assert "Ссылка не найдена" in detail or "доступ запрещён" in detail


def test_get_expired_links(client):
    """
    Тест получения просроченных ссылок:
    1. Создаем ссылку с expires_at в прошлом.
    2. Вызываем эндпойнт /links/expired и проверяем, что созданная ссылка присутствует в списке.
    """
    unique_url = f"http://expired.com/path?uid={uuid4()}"
    past_time = (datetime.utcnow() - timedelta(days=1)).isoformat() + "Z"
    resp = client.post("/links/shorten", json={"long_link": unique_url, "expires_at": past_time})
    assert resp.status_code == 200

    # Получаем список просроченных ссылок
    expired_resp = client.get("/links/expired")
    assert expired_resp.status_code == 200
    expired_links = expired_resp.json()
    
    # Проверяем, что ссылка с unique_url присутствует
    found = any(link["long_link"] == unique_url for link in expired_links)
    assert found, "Просроченная ссылка не найдена в ответе /links/expired"


def test_expired_link_redirect(client):
    """
    Проверяем, что при переходе на ссылку, чья дата уже истекла, код всё равно
    ведёт на Redirect (т.к. в коде нет явной проверки expires_at).
    Это тест, чтобы 'пройти' ветку, где expires_at < now (ничего не делает).
    """
    unique_url = f"http://expired-redirect.com/path?uid={uuid4()}"
    past_time = (datetime.utcnow() - timedelta(days=2)).isoformat() + "Z"
    # Создаём ссылку с истекшим сроком
    resp = client.post("/links/shorten", json={"long_link": unique_url, "expires_at": past_time})
    assert resp.status_code == 200
    short_code = resp.json()["short_link"]
    # Пробуем редирект
    redirect_resp = client.get(f"/links/?short_link={short_code}", follow_redirects=False)
    # Ожидаем, что код всё ещё делает редирект на long_link
    assert redirect_resp.status_code in (307, 308)
    assert redirect_resp.headers.get("location") == unique_url


def test_cache_invalidation_on_update(client):
    """
    Тестируем, что после обновления ссылки кэш очищается.
    1. Создаем ссылку, делаем GET (чтобы закэшировалось).
    2. Обновляем ссылку.
    3. Снова GET -> должна быть новая ссылка.
    """
    email = f"cacheuser_{uuid4()}@example.com"
    client.post("/auth/register", json={"email": email, "password": "pass"})
    login_resp = client.post("/auth/jwt/login", data={"username": email, "password": "pass"})
    token = login_resp.json().get("access_token")
    headers = {"Authorization": f"Bearer {token}"}

    url_old = f"http://old-cache.com/{uuid4()}"
    resp_create = client.post("/links/shorten", json={"long_link": url_old}, headers=headers)
    assert resp_create.status_code == 200
    short_code = resp_create.json()["short_link"]

    # Делаем GET (редирект) — кэшируется
    client.get(f"/links/?short_link={short_code}", follow_redirects=False)

    # Обновляем
    url_new = f"http://new-cache.com/{uuid4()}"
    update_resp = client.put(f"/links/{short_code}", json={"new_long_link": url_new}, headers=headers)
    assert update_resp.status_code == 200
    
    # Снова редирект
    redirect_resp = client.get(f"/links/?short_link={short_code}", follow_redirects=False)
    assert redirect_resp.headers.get("location") == url_new, "Кэш должен быть сброшен, редиректим на новый URL"


def test_cache_invalidation_on_delete(client):
    """
    Аналогично проверяем, что при удалении ссылка пропадает из кэша.
    1. Создаём ссылку, делаем GET (чтобы закэшировалось).
    2. Удаляем ссылку.
    3. Повторный GET -> 404.
    """
    email = f"deletecache_{uuid4()}@example.com"
    client.post("/auth/register", json={"email": email, "password": "pass"})
    login_resp = client.post("/auth/jwt/login", data={"username": email, "password": "pass"})
    token = login_resp.json().get("access_token")
    headers = {"Authorization": f"Bearer {token}"}

    url_to_del = f"http://shoulddelete-cache.com/{uuid4()}"
    resp_create = client.post("/links/shorten", json={"long_link": url_to_del}, headers=headers)
    assert resp_create.status_code == 200
    short_code = resp_create.json()["short_link"]

    # Делаем GET (кашемся)
    client.get(f"/links/?short_link={short_code}", follow_redirects=False)

    # Удаляем
    resp_del = client.delete(f"/links/{short_code}", headers=headers)
    assert resp_del.status_code == 200

    # Проверяем, что теперь 404
    resp_get_after_del = client.get(f"/links/?short_link={short_code}", follow_redirects=False)
    assert resp_get_after_del.status_code == 404, "Должно быть 404, т.к. ссылка удалена и кэш очищен"
