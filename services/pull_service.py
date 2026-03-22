"""services/pull_service.py - оркестрирует puller → buffer."""

from core.exceptions import UnknownProviderError
from core.interfaces import AbstractPullService
from db.models import LogLevel
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
                f"[pull_service] неизвестный провайдер '{provider}'",
                level=LogLevel.error,
            )
            raise UnknownProviderError(f"неизвестный провайдер: {provider}")

        print(f"[pull_service] запускаем {provider}...")
        try:
            data = cls().pull(**kwargs)
            write_log(f"[pull_service] '{provider}' завершён успешно")
            print(f"[pull_service] ok — {provider} → буфер готов")
            return data
        except Exception as e:
            write_log(
                f"[pull_service] '{provider}' завершился с ошибкой | {e}",
                level=LogLevel.error,
            )
            raise
