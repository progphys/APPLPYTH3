import os
import pytest

# 1) Устанавливаем переменные окружения для ТЕСТОВОЙ базы и Celery (in-memory).
os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASS", "test")
os.environ.setdefault("DB_NAME", "test_db")
os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_PORT", "5432")
os.environ.setdefault("CELERY_BROKER_URL", "memory://")  # in-memory брокер для Celery

from fastapi_cache import FastAPICache
from fastapi_cache.backends.inmemory import InMemoryBackend
FastAPICache.init(InMemoryBackend(), prefix="fastapi-cache")
from src import models
from src.database import sync_engine  
from src.links import models as links_models 
from fastapi.testclient import TestClient
from src.main import app

@pytest.fixture(scope="session", autouse=True)
def create_test_tables():
    models.Base.metadata.create_all(bind=sync_engine)
    links_models.metadata.create_all(bind=sync_engine)
    yield
    links_models.metadata.drop_all(bind=sync_engine)
    models.Base.metadata.drop_all(bind=sync_engine)

@pytest.fixture(autouse=True)
def clean_tables_and_cache():
    from sqlalchemy import delete
    import asyncio

    # 1) Чистим таблицу links
    with sync_engine.begin() as conn:
        conn.execute(delete(links_models.links))

    # 2) Чистим кэш
    backend = FastAPICache.get_backend()
    if backend:
        loop = asyncio.new_event_loop()
        loop.run_until_complete(backend.clear())  # Очищаем ВСЁ
        loop.close()

    yield

@pytest.fixture(scope="session")
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def patch_celery(monkeypatch):

    from src.tasks.tasks import delete_expired_link
    monkeypatch.setattr(delete_expired_link, "apply_async", lambda *args, **kwargs: None)
    yield


@pytest.fixture(autouse=True)
def patch_redis(monkeypatch):
    try:
        import redis.asyncio as aioredis
        monkeypatch.setattr(aioredis, "from_url", lambda *args, **kwargs: None)
    except ImportError:
        pass
    yield
