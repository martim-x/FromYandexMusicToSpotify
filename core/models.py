"""core/models.py — Pydantic модели."""

from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class YandexCredentials(BaseModel):
    cookie: str = Field(..., min_length=10)
    uid: str | None = None


class SpotifyCredentials(BaseModel):
    access_token: str = Field(..., min_length=10)
    token_type: str = "Bearer"
    expires_in: int = 3600
    refresh_token: str | None = None


class ProviderSchema(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    name: str = Field(..., max_length=50)

    model_config = {"from_attributes": True}


class VersionSchema(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    version: UUID = Field(default_factory=uuid4)
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    model_config = {"from_attributes": True}


class CredentialSchema(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    data: dict
    data_hash: str = ""
    provider_id: UUID
    version_id: UUID
    expired: bool = False

    model_config = {"from_attributes": True}


class ArchiveRow(BaseModel):
    version_id: UUID
    timestamp: datetime
    provider: str
    expired: bool
