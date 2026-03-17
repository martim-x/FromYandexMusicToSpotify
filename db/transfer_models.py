"""db/transfer_models.py - ORM для истории переноса треков."""

from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base


class TransferLog(Base):
    __tablename__ = "transfer_log"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    date: Mapped[str] = mapped_column(DateTime, server_default=func.now())
    status: Mapped[str] = mapped_column(String(20), default="pending")

    yandex_playlist_id: Mapped[str] = mapped_column(String(100))
    yandex_playlist_name: Mapped[str] = mapped_column(String(255), nullable=True)
    yandex_playlist_url: Mapped[str] = mapped_column(String(500), nullable=True)

    spotify_playlist_id: Mapped[str] = mapped_column(String(100))
    spotify_playlist_name: Mapped[str] = mapped_column(String(255), nullable=True)
    spotify_playlist_url: Mapped[str] = mapped_column(String(500), nullable=True)

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

    yandex_title: Mapped[str] = mapped_column(String(255))
    yandex_artist: Mapped[str] = mapped_column(String(255))

    spotify_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    spotify_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    spotify_artist: Mapped[str | None] = mapped_column(String(255), nullable=True)

    status: Mapped[str] = mapped_column(String(20))

    transfer: Mapped["TransferLog"] = relationship(back_populates="tracks")
