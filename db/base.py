"""db/base.py - SQLAlchemy engine, session, init, triggers."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

DATABASE_URL = "sqlite:///history.db"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=False,
)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


class Base(DeclarativeBase):
    pass


def get_session():
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# ── Триггеры: блокировка DELETE ───────────────────────────────────────

_PROTECTED_TABLES = [
    "providers",
    "versions",
    "credentials",
    "auth_log",
    "transfer_log",
    "transfer_tracks",
    "playlist",
    "transfer",
]

_DELETE_TRIGGER_SQL = """
CREATE TRIGGER IF NOT EXISTS block_delete_{table}
BEFORE DELETE ON {table}
BEGIN
    SELECT RAISE(ABORT, 'DELETE запрещён на таблице {table}');
END;
"""


def _create_triggers(conn) -> None:
    for table in _PROTECTED_TABLES:
        conn.execute(text(_DELETE_TRIGGER_SQL.format(table=table)))
    conn.commit()


# ── init ──────────────────────────────────────────────────────────────


def init_db() -> None:
    from db.models import Credential, Provider, Version  # noqa: F401
    from db.playlist_models import Playlist, Transfer  # noqa: F401
    from db.transfer_models import TransferLog, TransferTrack  # noqa: F401

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
    print("[db] инициализирована → history.db")


def _seed_providers() -> None:
    from uuid import UUID

    from db.models import Provider

    seeds = [
        ("00000000-0000-0000-0000-000000000001", "yandex"),
        ("00000000-0000-0000-0000-000000000002", "spotify"),
    ]
    with SessionLocal() as s:
        for pid, name in seeds:
            if not s.get(Provider, UUID(pid)):
                s.add(Provider(id=UUID(pid), name=name))
        s.commit()


# ── auth_log helper ───────────────────────────────────────────────────


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
