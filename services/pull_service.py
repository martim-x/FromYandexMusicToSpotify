"""services/pull_service.py - оркестрирует puller → buffer."""

from core.exceptions import UnknownProviderError
from core.interfaces import AbstractPullService
from pullers.spotify import SpotifyPuller
from pullers.yandex import YandexPuller

PULLERS = {
    "yandex": YandexPuller,
    "spotify": SpotifyPuller,
}


class PullService(AbstractPullService):
    def run(self, provider: str, **kwargs) -> dict:
        cls = PULLERS.get(provider)
        if not cls:
            raise UnknownProviderError(f"неизвестный провайдер: {provider}")
        print(f"[pull_service] запускаем {provider}...")
        data = cls().pull(**kwargs)
        print(f"[pull_service] ok — {provider} → буфер готов")
        return data
