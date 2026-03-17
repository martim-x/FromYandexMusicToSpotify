"""
core/interfaces.py — абстрактные интерфейсы для каждого слоя.
Dependency Inversion (SOLID).
"""

from abc import ABC, abstractmethod
from typing import Generic, TypeVar
from uuid import UUID

from core.models import CredentialSchema, ArchiveRow, VersionSchema

T = TypeVar("T")


class AbstractPuller(ABC):
    @abstractmethod
    def pull(self, **kwargs) -> dict: ...

    @abstractmethod
    def save_buffer(self, data: dict) -> None: ...

    @abstractmethod
    def load_buffer(self) -> dict: ...


class AbstractRepository(ABC, Generic[T]):
    @abstractmethod
    def add(self, entity: T) -> T: ...

    @abstractmethod
    def get(self, entity_id: UUID) -> T | None: ...

    @abstractmethod
    def get_all(self, limit: int = 10) -> list[T]: ...  # не list() — не shadow builtin


class AbstractCredentialRepository(AbstractRepository[CredentialSchema]):
    @abstractmethod
    def get_latest_by_provider(self, provider_id: UUID) -> CredentialSchema | None: ...

    @abstractmethod
    def mark_expired(self, provider_id: UUID) -> None: ...

    @abstractmethod
    def get_archive(
        self, limit: int = 10
    ) -> list[ArchiveRow]: ...  # не archive() — описательно


class AbstractPullService(ABC):
    @abstractmethod
    def run(self, provider: str, **kwargs) -> dict: ...


class AbstractPushService(ABC):
    @abstractmethod
    def run(self, provider: str) -> VersionSchema: ...

    @abstractmethod
    def get_archive(self, limit: int) -> list[ArchiveRow]: ...
