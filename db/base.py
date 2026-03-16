"""db/base.py — SQLAlchemy engine, session factory, DeclarativeBase."""

from sqlalchemy import create_engine
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
    """Dependency-style генератор сессии."""
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
        s.commit()
