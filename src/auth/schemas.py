import uuid
from fastapi_users import schemas

# Схема для представления данных пользователя при чтении.
# Наследуемся от базовой схемы BaseUser, которая определяет стандартные поля пользователя.
# Используем uuid.UUID как тип идентификатора, что соответствует нашим настройкам модели.
class UserRead(schemas.BaseUser[uuid.UUID]):
    pass

# Схема для создания нового пользователя.
# Наследуемся от базовой схемы BaseUserCreate, которая содержит необходимые поля для регистрации,
# такие как email и пароль, и может быть расширена дополнительными параметрами.
class UserCreate(schemas.BaseUserCreate):
    pass