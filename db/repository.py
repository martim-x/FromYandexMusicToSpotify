"""db/repository.py — реализация репозиториев (Repository pattern)."""

from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from core.interfaces import AbstractCredentialRepository
from core.models import CredentialSchema, HistoryRow, VersionSchema
from db.models import Credential, Provider, Version


def _log(msg: str) -> None:
    print(f"[repository] {msg}")


class VersionRepository:
    def __init__(self, session: Session):
        self.session = session

    def add(self, version: Version) -> Version:
        self.session.add(version)
        self.session.flush()
        _log(f"version добавлена → {version.id}")
        return version

    def get(self, version_id: UUID) -> Version | None:
        return self.session.get(Version, version_id)


class CredentialRepository(AbstractCredentialRepository):
    def __init__(self, session: Session):
        self.session = session

    def add(self, entity: CredentialSchema) -> CredentialSchema:
        row = Credential(
            id=entity.id,
            data=entity.data,
            provider_id=entity.provider_id,
            version_id=entity.version_id,
        )
        self.session.add(row)
        self.session.flush()
        _log(f"credential добавлен → {entity.id}")
        return entity

    def get(self, entity_id: UUID) -> CredentialSchema | None:
        row = self.session.get(Credential, entity_id)
        return CredentialSchema.model_validate(row) if row else None

    def list(self, limit: int = 10) -> list[CredentialSchema]:
        rows = self.session.execute(select(Credential).limit(limit)).scalars().all()
        return [CredentialSchema.model_validate(r) for r in rows]

    def get_latest_by_provider(self, provider_id: UUID) -> CredentialSchema | None:
        stmt = (
            select(Credential)
            .join(Version, Version.id == Credential.version_id)
            .where(
                Credential.provider_id == provider_id, Version.expired == False
            )  # noqa: E712
            .order_by(Version.timestamp.desc())
            .limit(1)
        )
        row = self.session.execute(stmt).scalar_one_or_none()
        return CredentialSchema.model_validate(row) if row else None

    def mark_expired(self, provider_id: UUID) -> None:
        subq = select(Credential.version_id).where(
            Credential.provider_id == provider_id
        )
        self.session.execute(
            update(Version)
            .where(Version.id.in_(subq), Version.expired == False)  # noqa: E712
            .values(expired=True)
        )
        _log(f"provider {provider_id} → помечено expired")

    def history(self, limit: int = 10) -> list[HistoryRow]:
        stmt = (
            select(Version, Provider.name)
            .join(Credential, Credential.version_id == Version.id)
            .join(Provider, Provider.id == Credential.provider_id)
            .order_by(Version.timestamp.desc())
            .limit(limit)
        )
        rows = self.session.execute(stmt).all()
        return [
            HistoryRow(
                version_id=v.id,
                timestamp=v.timestamp,
                provider=name,
                expired=v.expired,
            )
            for v, name in rows
        ]
