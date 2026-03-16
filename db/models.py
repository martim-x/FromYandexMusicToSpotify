"""db/models.py — ORM таблицы: providers, versions, credentials."""

from uuid import UUID, uuid4

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base


class Provider(Base):
    __tablename__ = "providers"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)

    credentials: Mapped[list["Credential"]] = relationship(back_populates="provider")


class Version(Base):
    __tablename__ = "versions"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    version: Mapped[UUID] = mapped_column(default=uuid4)
    timestamp: Mapped[str] = mapped_column(DateTime, server_default=func.now())
    expired: Mapped[bool] = mapped_column(Boolean, default=False)

    credential: Mapped["Credential"] = relationship(back_populates="version")


class Credential(Base):
    __tablename__ = "credentials"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    data: Mapped[dict] = mapped_column(JSON, nullable=False)
    provider_id: Mapped[UUID] = mapped_column(
        ForeignKey("providers.id"), nullable=False
    )
    version_id: Mapped[UUID] = mapped_column(ForeignKey("versions.id"), nullable=False)

    provider: Mapped["Provider"] = relationship(back_populates="credentials")
    version: Mapped["Version"] = relationship(back_populates="credential")
