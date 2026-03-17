"""db/models.py - ORM таблицы."""

import enum
from uuid import UUID, uuid4

from sqlalchemy import JSON, Boolean, DateTime, Enum, ForeignKey, Integer, String, func
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
    data_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    provider_id: Mapped[UUID] = mapped_column(
        ForeignKey("providers.id"), nullable=False
    )
    version_id: Mapped[UUID] = mapped_column(ForeignKey("versions.id"), nullable=False)

    provider: Mapped["Provider"] = relationship(back_populates="credentials")
    version: Mapped["Version"] = relationship(back_populates="credential")


class TransferStatus(str, enum.Enum):
    running = "running"
    done = "done"
    failed = "failed"


class TrackStatus(str, enum.Enum):
    matched = "matched"
    partial = "partial"
    not_found = "not_found"


class TransferLog(Base):
    __tablename__ = "transfer_log"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    created_at: Mapped[str] = mapped_column(DateTime, server_default=func.now())
    status: Mapped[str] = mapped_column(
        Enum(TransferStatus), default=TransferStatus.running
    )

    yandex_playlist_id: Mapped[str] = mapped_column(String, nullable=False)
    yandex_playlist_name: Mapped[str] = mapped_column(String, nullable=True)
    yandex_playlist_url: Mapped[str] = mapped_column(String, nullable=True)

    spotify_playlist_id: Mapped[str] = mapped_column(String, nullable=False)
    spotify_playlist_name: Mapped[str] = mapped_column(String, nullable=True)
    spotify_playlist_url: Mapped[str] = mapped_column(String, nullable=True)

    total: Mapped[int] = mapped_column(Integer, default=0)
    matched: Mapped[int] = mapped_column(Integer, default=0)
    partial: Mapped[int] = mapped_column(Integer, default=0)
    not_found: Mapped[int] = mapped_column(Integer, default=0)

    tracks: Mapped[list["TransferTrack"]] = relationship(
        back_populates="transfer", cascade="all, delete-orphan"
    )


class TransferTrack(Base):
    __tablename__ = "transfer_tracks"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    transfer_id: Mapped[UUID] = mapped_column(
        ForeignKey("transfer_log.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(Enum(TrackStatus), nullable=False)

    yandex_title: Mapped[str] = mapped_column(String, nullable=False)
    yandex_artist: Mapped[str] = mapped_column(String, nullable=False)

    spotify_id: Mapped[str | None] = mapped_column(String, nullable=True)
    spotify_title: Mapped[str | None] = mapped_column(String, nullable=True)
    spotify_artist: Mapped[str | None] = mapped_column(String, nullable=True)

    transfer: Mapped["TransferLog"] = relationship(back_populates="tracks")
