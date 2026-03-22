"""services/log_service.py — централизованная запись в таблицу logs."""

from uuid import UUID, uuid4

from db.base import SessionLocal
from db.models import Log, LogLevel


def write_log(
    detail: str,
    level: LogLevel = LogLevel.info,
    version_id: UUID | None = None,
) -> None:
    """
    Пишет лог. Если version_id не передан — создаёт черновую Version автоматически.
    Безопасен — глотает свои ошибки.
    """
    try:
        with SessionLocal() as session:
            if version_id is None:
                from db.models import Version

                v = Version(id=uuid4(), version=uuid4())
                session.add(v)
                session.flush()
                version_id = v.id

            session.add(
                Log(
                    id=uuid4(),
                    status=level,
                    detail=detail,
                    version_id=version_id,
                )
            )
            session.commit()
    except Exception as e:
        print(f"[error] ошибка записи лога: {e}")
