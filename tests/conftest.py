import os
import pytest

# 1) Устанавливаем переменные окружения для ТЕСТОВОЙ базы и Celery (in-memory).
os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASS", "test")
os.environ.setdefault("DB_NAME", "test_db")
os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_PORT", "5432")
os.environ.setdefault("CELERY_BROKER_URL", "memory://")  # in-memory брокер для Celery

# 2) Инициализируем FastAPICache (InMemoryBackend), чтобы не использовать Redis.
from fastapi_cache import FastAPICache
from fastapi_cache.backends.inmemory import InMemoryBackend
FastAPICache.init(InMemoryBackend(), prefix="fastapi-cache")

# 3) Импортируем модели, движок, приложение
from src import models  # ORM-модели (Base) — например, для пользователей
from src.database import sync_engine  # Синхронный engine
from src.links import models as links_models  # Тут лежит ваша таблица links
from fastapi.testclient import TestClient
from src.main import app

# ---------------- Фикстура для создания/удаления таблиц (scope="session") ----------------
@pytest.fixture(scope="session", autouse=True)
def create_test_tables():
    """
    1) При старте тестовой сессии создаём все таблицы (users + links).
    2) По окончании тестовой сессии удаляем (drop) их.
    """
    # Создаём таблицы, связанные с ORM (Base)
    models.Base.metadata.create_all(bind=sync_engine)
    # Создаём таблицы, связанные с core-моделью links
    links_models.metadata.create_all(bind=sync_engine)

    yield

    # После всех тестов дропаем
    links_models.metadata.drop_all(bind=sync_engine)
    models.Base.metadata.drop_all(bind=sync_engine)

# ---------------- Фикстура, очищающая данные в таблице links и кэше перед КАЖДЫМ тестом ----------------
@pytest.fixture(autouse=True)
def clean_tables_and_cache():
    """
    Очищает таблицу links и сбрасывает кэш перед каждым тестом.
    """
    from sqlalchemy import delete
    import asyncio

    # 1) Чистим таблицу links
    with sync_engine.begin() as conn:
        conn.execute(delete(links_models.links))  # Если 'links' — это Table(...) в links_models

    # 2) Чистим кэш
    backend = FastAPICache.get_backend()
    if backend:
        loop = asyncio.new_event_loop()
        loop.run_until_complete(backend.clear("*"))
        loop.close()

    yield

    # Если хотите повторно почистить после теста — можно здесь, но обычно достаточно до теста.


# ---------------- Фикстура для TestClient (scope="session" или "function") ----------------
@pytest.fixture(scope="session")
def client():
    """
    Создаёт TestClient на вашем FastAPI-приложении. 
    scope="session" означает, что во время одной сессии Pytest будет 
    переиспользовать один и тот же TestClient.
    """
    with TestClient(app) as test_client:
        yield test_client

# ---------------- Патчим Celery, чтобы задачи не ходили во внешний брокер ----------------
@pytest.fixture(autouse=True)
def patch_celery(monkeypatch):
    """
    Заменяем delete_expired_link.apply_async, чтобы не отправлять реальных задач в Celery.
    """
    from src.tasks.tasks import delete_expired_link
    monkeypatch.setattr(delete_expired_link, "apply_async", lambda *args, **kwargs: None)
    yield

# ---------------- Патчим Redis (aioredis), если у вас где-то в коде import redis.asyncio ----------------
@pytest.fixture(autouse=True)
def patch_redis(monkeypatch):
    try:
        import redis.asyncio as aioredis
        monkeypatch.setattr(aioredis, "from_url", lambda *args, **kwargs: None)
    except ImportError:
        pass
    yield
