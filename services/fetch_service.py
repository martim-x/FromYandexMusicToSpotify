"""services/fetch_service.py — оркестрирует fetcher → buffer."""

from core.exceptions import UnknownProviderError
from core.interfaces import AbstractFetchService
from fetchers.spotify import SpotifyFetcher
from fetchers.yandex import YandexFetcher

FETCHERS = {
    "yandex": YandexFetcher,
    "spotify": SpotifyFetcher,
}


class FetchService(AbstractFetchService):
    def run(self, provider: str, **kwargs) -> dict:
        cls = FETCHERS.get(provider)
        if not cls:
            raise UnknownProviderError(f"Неизвестный провайдер: {provider}")

        fetcher = cls()
        print(f"[fetch_service] запускаем {provider}...")
        data = fetcher.fetch(**kwargs)
        print(f"[fetch_service] {provider} — данные в буфере")
        return data
