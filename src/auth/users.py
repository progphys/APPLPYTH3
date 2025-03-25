# Импорт стандартного модуля uuid для работы с уникальными идентификаторами
import uuid
from typing import Optional

# Depends используется для определения зависимостей в маршрутах и функциях,
# Request позволяет получать данные HTTP-запроса, если потребуется
from fastapi import Depends, Request

# Импорт базовых классов и утилит из fastapi_users для управления пользователями:
# - BaseUserManager: базовый класс для реализации логики управления пользователями
# - UUIDIDMixin: миксин, позволяющий использовать UUID в качестве идентификатора пользователя
# - FastAPIUsers: основной класс для интеграции аутентификации в FastAPI
# - models: содержит типы и интерфейсы, используемые в fastapi_users
from fastapi_users import BaseUserManager, FastAPIUsers, UUIDIDMixin, models

# Импорт классов для настройки аутентификации:
# - AuthenticationBackend: объединяет транспорт и стратегию аутентификации
# - BearerTransport: определяет механизм передачи токена (Bearer-токены)
# - JWTStrategy: реализует стратегию работы с JWT токенами
from fastapi_users.authentication import (
    AuthenticationBackend,
    BearerTransport,
    JWTStrategy,
)

# Импорт класса для работы с базой данных пользователей через SQLAlchemy
from fastapi_users.db import SQLAlchemyUserDatabase


# Импорт модели пользователя (User) и функции для получения объекта базы данных пользователей
from auth.db import User, get_user_db

# Константа для секретного ключа, используемая для подписи JWT и генерации токенов для верификации
from config import SECRET

# Определяем класс UserManager, который отвечает за управление пользователями.
# Он наследует функционал для работы с UUID (UUIDIDMixin) и базовую логику управления (BaseUserManager).
class UserManager(UUIDIDMixin, BaseUserManager[User, uuid.UUID]):
    # - verification_token_secret используется при запросе верификации аккаунта
    verification_token_secret = SECRET

    # Асинхронный метод, вызываемый после успешной регистрации пользователя.
    async def on_after_register(self, user: User, request: Optional[Request] = None):
        print(f"User {user.id} has registered.")

    # Асинхронный метод, вызываемый после запроса на верификацию аккаунта.
    # Выводит сообщение с информацией о пользователе и токене верификации.
    async def on_after_request_verify(
        self, user: User, token: str, request: Optional[Request] = None
    ):
        print(f"Verification requested for user {user.id}. Verification token: {token}")

# Функция-генератор для получения экземпляра UserManager.
# Используется Depends для получения объекта базы данных пользователей (SQLAlchemyUserDatabase).
async def get_user_manager(user_db: SQLAlchemyUserDatabase = Depends(get_user_db)):
    yield UserManager(user_db)

# Настройка транспорта для аутентификации с использованием Bearer-токенов.
# tokenUrl указывает URL для получения JWT при логине.
bearer_transport = BearerTransport(tokenUrl="auth/jwt/login")

# Функция для создания и возвращения экземпляра стратегии JWT.
# Здесь задаются секретный ключ и время жизни токена (3600 секунд).
def get_jwt_strategy() -> JWTStrategy[models.UP, models.ID]:
    return JWTStrategy(secret=SECRET, lifetime_seconds=3600)

# Создание backend-а для аутентификации:
# - name: имя метода аутентификации ("jwt")
# - transport: механизм передачи токена (Bearer)
# - get_strategy: функция, возвращающая стратегию JWT.
auth_backend = AuthenticationBackend(
    name="jwt",
    transport=bearer_transport,
    get_strategy=get_jwt_strategy,
)

# Создание экземпляра FastAPIUsers, который объединяет менеджер пользователей и список бэкендов аутентификации.
# Здесь указывается, что модель пользователя - User, а идентификатор имеет тип uuid.UUID.
fastapi_users = FastAPIUsers[User, uuid.UUID](get_user_manager, [auth_backend])

# Определение зависимости для получения текущего активного пользователя.
# Используется для защиты маршрутов, где доступ разрешён только аутентифицированным и активным пользователям.
current_active_user = fastapi_users.current_user(active=True)
