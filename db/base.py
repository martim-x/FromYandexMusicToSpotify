"""db/base.py - SQLAlchemy engine, session factory, DeclarativeBase."""

import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy import create_engine, text
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


def init_db() -> None:
    from db.models import Credential, Provider, Version  # noqa: F401

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


def log_auth_event(provider: str, method: str, note: str = "") -> None:
    """
    Записывает событие успешной авторизации.

    provider : yandex | spotify
    method   : cookie | oauth | push_notification | phone
    note     : доп. пометка (например 'phone+push OK')
    """
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
    print(f"[auth_log] {provider} | {method} | {note}")
