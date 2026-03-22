"""db/repository.py — Repository pattern."""

from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from core.interfaces import AbstractCredentialRepository
from core.models import ArchiveRow, CredentialSchema
from db.models import Credential, Provider, Version


class VersionRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, version: Version) -> Version:
        self.session.add(version)
        self.session.flush()
        return version

    def get(self, version_id: UUID) -> Version | None:
        return self.session.get(Version, version_id)


class CredentialRepository(AbstractCredentialRepository):
    def __init__(self, session: Session) -> None:
        self.session = session

    def is_duplicate(self, provider_id: UUID, data_hash: str) -> bool:
        row = self.session.execute(
            select(Credential.id)
            .where(
                Credential.provider_id == provider_id,
                Credential.data_hash == data_hash,
                Credential.expired == False,  # noqa: E712
            )
            .limit(1)
        ).scalar_one_or_none()
        return row is not None

    def add(self, entity: CredentialSchema) -> CredentialSchema:
        self.session.add(
            Credential(
                id=entity.id,
                data=entity.data,
                data_hash=entity.data_hash,
                provider_id=entity.provider_id,
                version_id=entity.version_id,
            )
        )
        self.session.flush()
        return entity

    def get(self, entity_id: UUID) -> CredentialSchema | None:
        row = self.session.get(Credential, entity_id)
        return CredentialSchema.model_validate(row) if row else None

    def get_all(self, limit: int = 10) -> list[CredentialSchema]:
        rows = self.session.execute(select(Credential).limit(limit)).scalars().all()
        return [CredentialSchema.model_validate(r) for r in rows]

    def get_latest_by_provider(self, provider_id: UUID) -> CredentialSchema | None:
        stmt = (
            select(Credential)
            .join(Version, Version.id == Credential.version_id)
            .where(
                Credential.provider_id == provider_id,
                Credential.expired == False,  # noqa: E712
            )
            .order_by(Version.timestamp.desc())
            .limit(1)
        )
        row = self.session.execute(stmt).scalar_one_or_none()
        return CredentialSchema.model_validate(row) if row else None

    def mark_expired(self, provider_id: UUID) -> None:
        self.session.execute(
            update(Credential)
            .where(
                Credential.provider_id == provider_id,
                Credential.expired == False,  # noqa: E712
            )
            .values(expired=True)
        )

    def get_archive(self, limit: int = 10) -> list[ArchiveRow]:
        stmt = (
            select(Credential, Provider.name)
            .join(Version, Version.id == Credential.version_id)
            .join(Provider, Provider.id == Credential.provider_id)
            .order_by(Version.timestamp.desc())
            .limit(limit)
        )
        return [
            ArchiveRow(
                version_id=cred.version_id,
                timestamp=cred.version.timestamp,
                provider=name,
                expired=cred.expired,
            )
            for cred, name in self.session.execute(stmt).all()
        ]
