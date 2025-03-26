from fastapi import FastAPI, Depends, HTTPException
from collections.abc import AsyncIterator
from auth.users import auth_backend, current_active_user, fastapi_users
from auth.schemas import UserCreate, UserRead
from auth.db import User
import uvicorn

from links.router import router as link_router

from redis import asyncio as aioredis
from fastapi_cache import FastAPICache
from fastapi_cache.backends.redis import RedisBackend
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    redis = aioredis.from_url("redis://redis:6379/0")
    FastAPICache.init(RedisBackend(redis), prefix="fastapi-cache")
    yield


app = FastAPI(lifespan=lifespan)


# Добавление маршрутов аутентификации с использованием fastapi_users
# Роутер для аутентификации с использованием JWT токенов.
app.include_router(
    fastapi_users.get_auth_router(auth_backend), prefix="/auth/jwt", tags=["auth"]
)

# Роутер для регистрации пользователей.
app.include_router(
    fastapi_users.get_register_router(UserRead, UserCreate),
    prefix="/auth",
    tags=["auth"],
)
#Добавили роутер для создания ссылок
app.include_router(link_router)
