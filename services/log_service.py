"""services/log_service.py — централизованная запись в таблицу logs."""

from uuid import UUID, uuid4

from db.base import SessionLocal
from db.models import Log, LogLevel
from i18n import t


def write_log(
    detail: str,
    level: LogLevel = LogLevel.info,
    version_id: UUID | None = None,
) -> None:
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
        print(t("log_service.error", error=e))
