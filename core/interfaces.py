"""
core/interfaces.py — абстрактные интерфейсы для каждого слоя.
Следуем принципу Dependency Inversion (SOLID).
"""

from abc import ABC, abstractmethod
from typing import Generic, TypeVar
from uuid import UUID

from core.models import CredentialSchema, HistoryRow, VersionSchema

T = TypeVar("T")


# ── Слой: Fetcher ─────────────────────────────────────────────────────


class AbstractFetcher(ABC):
    """
    Получает сессионные данные от провайдера.
    Реализации: YandexFetcher, SpotifyFetcher.
    """

    @abstractmethod
    def fetch(self, **kwargs) -> dict:
        """
        Возвращает dict с сессионными данными (куки или токен).
        Пароли и личные данные в dict не включаются.
        """

    @abstractmethod
    def save_buffer(self, data: dict) -> None:
        """Сохраняет данные в буферный JSON файл."""

    @abstractmethod
    def load_buffer(self) -> dict:
        """Читает данные из буферного JSON файла."""


# ── Слой: Repository ─────────────────────────────────────────────────


class AbstractRepository(ABC, Generic[T]):
    """
    Базовый репозиторий. Один репозиторий = одна таблица.
    """

    @abstractmethod
    def add(self, entity: T) -> T: ...

    @abstractmethod
    def get(self, entity_id: UUID) -> T | None: ...

    @abstractmethod
    def list(self, limit: int = 10) -> list[T]: ...


class AbstractCredentialRepository(AbstractRepository[CredentialSchema]):
    """Репозиторий для таблицы credentials."""

    @abstractmethod
    def get_latest_by_provider(self, provider_id: UUID) -> CredentialSchema | None: ...

    @abstractmethod
    def mark_expired(self, provider_id: UUID) -> None: ...


# ── Слой: Service ─────────────────────────────────────────────────────


class AbstractFetchService(ABC):
    """Оркестрирует fetcher → buffer."""

    @abstractmethod
    def run(self, provider: str, **kwargs) -> dict: ...


class AbstractUpdateService(ABC):
    """Читает буфер → записывает в БД и .env."""

    @abstractmethod
    def run(self, provider: str) -> VersionSchema: ...

    @abstractmethod
    def history(self, limit: int) -> list[HistoryRow]: ...
