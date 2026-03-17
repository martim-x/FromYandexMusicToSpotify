"""services/push_service.py — буфер → БД + .env."""

import hashlib
import json
from pathlib import Path
from uuid import UUID

from dotenv import set_key
from tabulate import tabulate

from core.exceptions import PushError, UnknownProviderError
from core.interfaces import AbstractPushService
from core.models import ArchiveRow, CredentialSchema, VersionSchema
from db.base import SessionLocal
from db.models import Credential, Version
from db.repository import CredentialRepository, VersionRepository
from pullers.spotify import SpotifyPuller
from pullers.yandex import YandexPuller

ENV_FILE = Path(__file__).resolve().parent.parent / ".env"

PULLERS = {
    "yandex": YandexPuller,
    "spotify": SpotifyPuller,
}

PROVIDER_IDS = {
    "yandex": UUID("00000000-0000-0000-0000-000000000001"),
    "spotify": UUID("00000000-0000-0000-0000-000000000002"),
}

ENV_KEYS = {
    "yandex": {"cookie": "YANDEX_COOKIE", "uid": "YANDEX_UID"},
    "spotify": {
        "access_token": "SPOTIFY_ACCESS_TOKEN",
        "refresh_token": "SPOTIFY_REFRESH_TOKEN",
    },
}


def _write_env(provider: str, data: dict) -> None:
    ENV_FILE.touch(exist_ok=True)
    written = []
    for field, env_key in ENV_KEYS.get(provider, {}).items():
        value = data.get(field)
        if value:
            set_key(str(ENV_FILE), env_key, str(value))
            written.append((env_key, "updated"))
    if written:
        print(tabulate(written, headers=["key", "status"], tablefmt="rounded_outline"))


class PushService(AbstractPushService):

    def run(self, provider: str) -> VersionSchema:
        if provider not in PULLERS:
            raise UnknownProviderError(f"неизвестный провайдер: {provider}")

        try:
            puller = PULLERS[provider]()
            raw_data = puller.load_buffer()
        except FileNotFoundError as e:
            raise PushError(
                f"[push] буфер не найден для {provider} — сначала запусти: pull {provider}"
            ) from e

        provider_id = PROVIDER_IDS[provider]

        # Хешируем данные для проверки дублей
        data_hash = hashlib.sha256(
            json.dumps(raw_data, sort_keys=True).encode()
        ).hexdigest()

        # Проверяем: если активная запись с таким хешем уже есть — пропускаем
        with SessionLocal() as check_session:
            c_repo_check = CredentialRepository(check_session)
            if c_repo_check.is_duplicate(provider_id, data_hash):
                print(f"[push] {provider} — данные не изменились, push пропущен")
                return VersionSchema()  # возвращаем пустую схему без записи

        version_schema = VersionSchema()
        cred_schema = CredentialSchema(
            data=raw_data,
            data_hash=data_hash,
            provider_id=provider_id,
            version_id=version_schema.id,
        )

        with SessionLocal() as session:
            c_repo = CredentialRepository(session)
            v_repo = VersionRepository(session)

            c_repo.mark_expired(provider_id)
            v_repo.add(
                Version(
                    id=version_schema.id,
                    version=version_schema.version,
                    expired=False,
                )
            )
            c_repo.add(cred_schema)
            session.commit()

        _write_env(provider, raw_data)

        print(
            tabulate(
                [
                    ("provider", provider),
                    ("version_id", str(version_schema.id)),
                    ("status", "saved"),
                ],
                headers=["field", "value"],
                tablefmt="rounded_outline",
            )
        )
        return version_schema

    def get_archive(self, limit: int = 10) -> list[ArchiveRow]:
        with SessionLocal() as session:
            return CredentialRepository(session).get_archive(limit)
