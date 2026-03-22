"""services/pull_service.py - оркестрирует puller → buffer."""

from core.exceptions import UnknownProviderError
from core.interfaces import AbstractPullService
from db.models import LogLevel
from i18n import t
from pullers.spotify import SpotifyPuller
from pullers.yandex import YandexPuller
from services.log_service import write_log

PULLERS = {
    "yandex": YandexPuller,
    "spotify": SpotifyPuller,
}


class PullService(AbstractPullService):
    def run(self, provider: str, **kwargs) -> dict:
        cls = PULLERS.get(provider)
        if not cls:
            write_log(
                f"pull_service: unknown provider '{provider}'", level=LogLevel.error
            )
            raise UnknownProviderError(t("error.unknown_provider", provider=provider))

        print(t("pull_service.start", provider=provider))
        try:
            data = cls().pull(**kwargs)
            write_log(f"pull_service: '{provider}' completed successfully")
            print(t("pull_service.ok", provider=provider))
            return data
        except Exception as e:
            write_log(f"pull_service: '{provider}' failed | {e}", level=LogLevel.error)
            raise
