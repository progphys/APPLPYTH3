from sqlalchemy import text
from src.tasks.tasks import delete_expired_link
from src.database import sync_engine
from sqlalchemy.orm import sessionmaker

def test_delete_expired_link_task(client):
    long_url = "http://todelete.com"
    # Передаем expires_at в формате ISO с указанием 'Z'
    resp = client.post("/links/shorten", json={"long_link": long_url, "expires_at": "2100-01-01T00:00:00Z"})
    assert resp.status_code == 200
    link_id = resp.json()["id"]

    Session = sessionmaker(bind=sync_engine)
    session = Session()
    result = session.execute(text(f"SELECT id FROM links WHERE id = {link_id}"))
    row = result.first()
    assert row is not None  # ссылка существует до удаления

    # Вызываем функцию удаления напрямую (apply_async уже патчена)
    delete_expired_link(link_id)
    result_after = session.execute(text(f"SELECT id FROM links WHERE id = {link_id}"))
    row_after = result_after.first()
    session.close()
    assert row_after is None, "Запись должна быть удалена задачей Celery"

    # Повторный вызов не должен бросать исключений
    delete_expired_link(link_id)
