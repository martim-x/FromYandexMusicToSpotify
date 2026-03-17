"""db/base.py — SQLAlchemy engine, session, init, triggers."""

import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

_DB_FILE = Path(__file__).resolve().parent.parent / "archive.db"
DATABASE_URL = f"sqlite:///{_DB_FILE}"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=False,
)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


class Base(DeclarativeBase):
    pass


# ── Триггеры: блокировка DELETE ───────────────────────────────────────

_PROTECTED = [
    "providers",
    "versions",
    "credentials",
    "auth_log",
    "playlist",
    "transfer",
    "transfer_log",
    "transfer_tracks",
]

_TRIGGER_SQL = """
CREATE TRIGGER IF NOT EXISTS block_delete_{t}
BEFORE DELETE ON {t}
BEGIN
    SELECT RAISE(ABORT, 'DELETE запрещён: {t}');
END;
"""


def _create_triggers(conn) -> None:
    for t in _PROTECTED:
        conn.execute(text(_TRIGGER_SQL.format(t=t)))
    conn.commit()


# ── init ──────────────────────────────────────────────────────────────


def init_db() -> None:
    from db.models import (  # noqa: F401
        Credential,
        Provider,
        TransferLog,
        TransferTrack,
        Version,
    )
    from db.playlist_models import Playlist, Transfer  # noqa: F401

    Base.metadata.create_all(bind=engine)

    with engine.connect() as conn:
        conn.execute(
            text(
                """
            CREATE TABLE IF NOT EXISTS auth_log (
                id        TEXT PRIMARY KEY,
                provider  TEXT NOT NULL,
                method    TEXT NOT NULL,
                note      TEXT,
                timestamp TEXT NOT NULL
            )
        """
            )
        )
        _create_triggers(conn)
        conn.commit()

    _seed_providers()
    print(f"[db] инициализирована → {_DB_FILE.name}")


def _seed_providers() -> None:
    from db.models import Provider

    seeds = [
        ("00000000-0000-0000-0000-000000000001", "yandex"),
        ("00000000-0000-0000-0000-000000000002", "spotify"),
    ]
    with SessionLocal() as s:
        for pid, name in seeds:
            if not s.get(Provider, uuid.UUID(pid)):
                s.add(Provider(id=uuid.UUID(pid), name=name))
        s.commit()


# ── auth_log ──────────────────────────────────────────────────────────


def log_auth_event(provider: str, method: str, note: str = "") -> None:
    with SessionLocal() as s:
        s.execute(
            text(
                "INSERT INTO auth_log (id, provider, method, note, timestamp) "
                "VALUES (:id, :provider, :method, :note, :ts)"
            ),
            {
                "id": str(uuid.uuid4()),
                "provider": provider,
                "method": method,
                "note": note,
                "ts": datetime.now(timezone.utc).isoformat(),
            },
        )
        s.commit()
    print(f"[auth_log] {provider} | {method} | {note}")
