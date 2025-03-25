from fastapi import Depends
from fastapi_users.db import SQLAlchemyBaseUserTableUUID, SQLAlchemyUserDatabase
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase
from database import engine, get_async_session


# Создаем базовый класс для моделей SQLAlchemy.
# Все модели будут наследоваться от этого класса, что позволяет SQLAlchemy управлять ими.
class Base(DeclarativeBase):
    pass

# Определяем модель пользователя.
# Наследуемся от SQLAlchemyBaseUserTableUUID для использования стандартных полей (например, UUID, email, hashed_password)
# и от базового класса Base для регистрации модели в метаданных SQLAlchemy.
class User(SQLAlchemyBaseUserTableUUID, Base):
    pass

# Асинхронная функция для создания базы данных и всех таблиц, определённых в моделях.
async def create_db_and_tables():
    # Открываем асинхронное соединение с базой данных через движок.
    async with engine.begin() as conn:
        # Выполняем синхронное создание всех таблиц, определённых в Base.metadata.
        await conn.run_sync(Base.metadata.create_all)

# Определяем зависимость FastAPI для получения экземпляра базы данных пользователей.
# Эта функция используется для внедрения зависимости в маршрутах FastAPI, чтобы обеспечить доступ к базе данных.
async def get_user_db(session: AsyncSession = Depends(get_async_session)):
    # Создаем и возвращаем объект SQLAlchemyUserDatabase, связывающий асинхронную сессию с моделью User.
    # Это позволяет выполнять CRUD-операции с пользователями через FastAPI Users.
    yield SQLAlchemyUserDatabase(session, User)