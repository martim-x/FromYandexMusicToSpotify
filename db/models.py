"""db/models.py - все ORM модели."""

import enum
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
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

    credential: Mapped["Credential"] = relationship(back_populates="version")
    logs: Mapped[list["Log"]] = relationship(back_populates="version")


class Credential(Base):
    __tablename__ = "credentials"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    data: Mapped[dict] = mapped_column(JSON, nullable=False)
    data_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    provider_id: Mapped[UUID] = mapped_column(
        ForeignKey("providers.id"), nullable=False
    )
    version_id: Mapped[UUID] = mapped_column(ForeignKey("versions.id"), nullable=False)
    expired: Mapped[bool] = mapped_column(Boolean, default=False)

    provider: Mapped["Provider"] = relationship(back_populates="credentials")
    version: Mapped["Version"] = relationship(back_populates="credential")


class LogLevel(str, enum.Enum):
    info = "info"
    warn = "warn"
    error = "error"


class Log(Base):
    __tablename__ = "logs"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    timestamp: Mapped[str] = mapped_column(DateTime, server_default=func.now())
    status: Mapped[str] = mapped_column(Enum(LogLevel), default=LogLevel.info)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    version_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("versions.id"), nullable=False
    )

    version: Mapped["Version | None"] = relationship(back_populates="logs")


class Playlist(Base):
    __tablename__ = "playlists"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    url: Mapped[str] = mapped_column(String(500), nullable=False, unique=True)
    provider_id: Mapped[UUID] = mapped_column(
        ForeignKey("providers.id"), nullable=False
    )
    exists: Mapped[bool] = mapped_column(Boolean, default=True)

    provider: Mapped["Provider"] = relationship()
    from_links: Mapped[list["Transfer"]] = relationship(
        foreign_keys="Transfer.from_id", back_populates="from_playlist"
    )
    to_links: Mapped[list["Transfer"]] = relationship(
        foreign_keys="Transfer.to_id", back_populates="to_playlist"
    )


class Transfer(Base):
    __tablename__ = "transfers"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    from_id: Mapped[UUID] = mapped_column(ForeignKey("playlists.id"), nullable=False)
    to_id: Mapped[UUID] = mapped_column(ForeignKey("playlists.id"), nullable=False)
    version_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("versions.id"), nullable=False
    )
    timestamp: Mapped[str] = mapped_column(DateTime, server_default=func.now())
    status: Mapped[str] = mapped_column(String(20), default="pending")

    total: Mapped[int] = mapped_column(Integer, default=0)
    matched: Mapped[int] = mapped_column(Integer, default=0)
    partial: Mapped[int] = mapped_column(Integer, default=0)
    not_found: Mapped[int] = mapped_column(Integer, default=0)

    from_playlist: Mapped["Playlist"] = relationship(
        foreign_keys=[from_id], back_populates="from_links"
    )
    to_playlist: Mapped["Playlist"] = relationship(
        foreign_keys=[to_id], back_populates="to_links"
    )
    tracks: Mapped[list["Track"]] = relationship(
        back_populates="transfer", cascade="all, delete-orphan"
    )
    verified_tracks: Mapped[list["VerifiedTrack"]] = relationship(
        back_populates="transfer"
    )


class TrackStatus(str, enum.Enum):
    pending = "pending"
    matched = "matched"
    partial = "partial"
    not_found = "not_found"


class Track(Base):
    __tablename__ = "tracks"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    transfer_id: Mapped[UUID] = mapped_column(
        ForeignKey("transfers.id"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(
        Enum(TrackStatus), default=TrackStatus.pending, index=True
    )

    yandex_id: Mapped[str | None] = mapped_column(
        String(100), nullable=True, index=True
    )
    yandex_title: Mapped[str] = mapped_column(String(500), nullable=False)
    yandex_artist: Mapped[str] = mapped_column(String(500), nullable=False)
    yandex_album: Mapped[str | None] = mapped_column(String(500), nullable=True)
    yandex_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    yandex_duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    spotify_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    spotify_title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    spotify_artist: Mapped[str | None] = mapped_column(String(500), nullable=True)

    transfer: Mapped["Transfer"] = relationship(back_populates="tracks")
    verified: Mapped["VerifiedTrack | None"] = relationship(
        back_populates="track", uselist=False
    )


class VerifiedTrack(Base):
    __tablename__ = "verified_tracks"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    track_id: Mapped[UUID] = mapped_column(
        ForeignKey("tracks.id"), nullable=False, unique=True
    )
    transfer_id: Mapped[UUID] = mapped_column(
        ForeignKey("transfers.id"), nullable=False, index=True
    )

    track: Mapped["Track"] = relationship(back_populates="verified")
    transfer: Mapped["Transfer"] = relationship(back_populates="verified_tracks")
