"""db/playlist_models.py - таблицы playlist и transfer."""

from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base


class Playlist(Base):
    __tablename__ = "playlist"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=True)
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    provider_id: Mapped[UUID] = mapped_column(
        ForeignKey("providers.id"), nullable=False
    )
    exists: Mapped[bool] = mapped_column(Boolean, default=True)
    copied: Mapped[bool] = mapped_column(Boolean, default=False)

    provider: Mapped["Provider"] = relationship()  # noqa: F821
    from_links: Mapped[list["Transfer"]] = relationship(
        foreign_keys="Transfer.from_id", back_populates="from_playlist"
    )
    to_links: Mapped[list["Transfer"]] = relationship(
        foreign_keys="Transfer.to_id", back_populates="to_playlist"
    )


class Transfer(Base):
    __tablename__ = "transfer"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    from_id: Mapped[UUID] = mapped_column(ForeignKey("playlist.id"), nullable=False)
    to_id: Mapped[UUID] = mapped_column(ForeignKey("playlist.id"), nullable=False)
    version_id: Mapped[UUID] = mapped_column(ForeignKey("versions.id"), nullable=True)
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
