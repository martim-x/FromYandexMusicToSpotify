"""
services/update_service.py

Читает буфер → валидирует → пишет в БД → обновляет .env.
"""

from pathlib import Path
from uuid import UUID

from dotenv import set_key

from core.exceptions import UnknownProviderError
from core.interfaces import AbstractUpdateService
from core.models import CredentialSchema, HistoryRow, VersionSchema
from db.base import SessionLocal
from db.models import Credential, Version
from db.repository import CredentialRepository, VersionRepository
from fetchers.spotify import SpotifyFetcher
from fetchers.yandex import YandexFetcher

ENV_FILE = Path(".env")

FETCHERS = {
    "yandex": YandexFetcher,
    "spotify": SpotifyFetcher,
}

PROVIDER_IDS = {
    "yandex": UUID("00000000-0000-0000-0000-000000000001"),
    "spotify": UUID("00000000-0000-0000-0000-000000000002"),
}

ENV_KEYS = {
    "yandex": {"cookie": "YANDEX_COOKIE"},
    "spotify": {
        "access_token": "SPOTIFY_ACCESS_TOKEN",
        "refresh_token": "SPOTIFY_REFRESH_TOKEN",
    },
}


def _write_env(provider: str, data: dict) -> None:
    ENV_FILE.touch(exist_ok=True)
    mapping = ENV_KEYS.get(provider, {})
    for field, env_key in mapping.items():
        value = data.get(field)
        if value:
            set_key(str(ENV_FILE), env_key, str(value))
            print(f"[update_service] .env → {env_key} обновлён")


class UpdateService(AbstractUpdateService):

    def run(self, provider: str) -> VersionSchema:
        if provider not in FETCHERS:
            raise UnknownProviderError(f"Неизвестный провайдер: {provider}")

        fetcher = FETCHERS[provider]()
        raw_data = fetcher.load_buffer()
        provider_id = PROVIDER_IDS[provider]

        version_schema = VersionSchema()
        cred_schema = CredentialSchema(
            data=raw_data,
            provider_id=provider_id,
            version_id=version_schema.id,
        )

        with SessionLocal() as session:
            v_repo = VersionRepository(session)
            c_repo = CredentialRepository(session)

            # Помечаем старые как expired
            c_repo.mark_expired(provider_id)

            # Записываем новую версию
            version_row = Version(
                id=version_schema.id,
                version=version_schema.version,
                expired=False,
            )
            v_repo.add(version_row)

            cred_row = Credential(
                id=cred_schema.id,
                data=cred_schema.data,
                provider_id=cred_schema.provider_id,
                version_id=cred_schema.version_id,
            )
            session.add(cred_row)
            session.commit()

        _write_env(provider, raw_data)
        print(f"[update_service] {provider} обновлён — version {version_schema.id}")
        return version_schema

    def history(self, limit: int = 10) -> list[HistoryRow]:
        with SessionLocal() as session:
            return CredentialRepository(session).history(limit)
