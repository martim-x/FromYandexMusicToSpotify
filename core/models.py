"""
core/models.py — Pydantic модели для валидации данных на всех слоях.
Никаких паролей. Только сессионные данные.
"""

from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

# ── Буфер (то что fetcher кладёт в JSON файл) ────────────────────────


class YandexCredentials(BaseModel):
    cookie: str = Field(..., min_length=10, description="Строка куков music.yandex.ru")
    expired: bool = False


class SpotifyCredentials(BaseModel):
    access_token: str = Field(..., min_length=10)
    token_type: str = "Bearer"
    expires_in: int = 3600
    refresh_token: str | None = None
    expired: bool = False


# ── Провайдер ─────────────────────────────────────────────────────────


class ProviderSchema(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    name: str = Field(..., max_length=50)

    model_config = {"from_attributes": True}


# ── Версия (запись в archive) ─────────────────────────────────────────


class VersionSchema(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    version: UUID = Field(default_factory=uuid4)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    expired: bool = False

    model_config = {"from_attributes": True}


# ── Credentials (запись в таблицу credentials) ────────────────────────


class CredentialSchema(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    data: dict
    provider_id: UUID
    version_id: UUID

    model_config = {"from_attributes": True}


# ── Результат --history ───────────────────────────────────────────────


class HistoryRow(BaseModel):
    version_id: UUID
    timestamp: datetime
    provider: str
    expired: bool
