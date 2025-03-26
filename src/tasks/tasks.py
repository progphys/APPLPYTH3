from sqlalchemy import delete
from sqlalchemy.orm import sessionmaker
from datetime import datetime
from database import sync_engine 
from links.models import links  
from celery import Celery

celery_app = Celery('tasks', broker="redis://redis:6379/0")
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=sync_engine)

@celery_app.task() 
def delete_expired_link(link_id: int):
    session = SessionLocal()
    try:
        stmt = delete(links).where(links.c.id == link_id)
        session.execute(stmt)
        session.commit()
        print(f"Ссылка с id {link_id} удалена в {datetime.utcnow()}")
    except Exception as e:
        session.rollback()
        print(f"Ошибка удаления ссылки с id {link_id}: {e}")
        raise e
    finally:
        session.close()