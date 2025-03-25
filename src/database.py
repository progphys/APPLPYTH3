from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from config import DB_HOST, DB_NAME, DB_PASS, DB_PORT, DB_USER
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
# Ссылка на нашу БД
DATABASE_URL = f"postgresql+asyncpg://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"



# Используем синхронный движок
sync_engine = create_engine(f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}") 
# Инициализируем ассинхроный драйвер для подключения к БД
engine = create_async_engine(DATABASE_URL)

# Задаем фабрику сессий, после фиксации транзакции, объекты не будут сразу же истекать
async_session_maker = async_sessionmaker(engine, expire_on_commit=False)

# Ассинхронный генератор, при вызове создающий сессию и возвращающиию ей
async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_maker() as session:
        yield session
