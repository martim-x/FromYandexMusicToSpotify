"""fetchers/yandex.py - получает куки с music.yandex.ru."""

import time

import undetected_chromedriver as uc

from core.exceptions import FetcherError
from core.models import YandexCredentials
from fetchers.base import BaseFetcher

MUSIC_URL = "https://music.yandex.ru"
POLL_SECS = 2
SESSION_KEYS = {"Session_id", "yandex_login", "L"}


class YandexFetcher(BaseFetcher):
    provider = "yandex"

    def _build_driver(self) -> uc.Chrome:
        opts = uc.ChromeOptions()
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        return uc.Chrome(options=opts)

    def _cookies_as_str(self, cookies: list[dict]) -> str:
        return "; ".join(f"{c['name']}={c['value']}" for c in cookies)

    def _is_logged_in(self, driver: uc.Chrome) -> bool:
        names = {c["name"] for c in driver.get_cookies()}
        return bool(names & SESSION_KEYS)

    def _detect_auth_method(self, driver: uc.Chrome) -> str:
        """
        Пытается определить каким способом прошла авторизация.
        Возвращает строку для auth_log.
        """
        try:
            src = driver.page_source.lower()
            if "push" in src or "уведомлени" in src:
                return "push_notification"
            if "phone" in src or "телефон" in src or "смс" in src:
                return "phone"
        except Exception:
            pass
        return "cookie"

    def fetch(self, **_) -> dict:
        """
        Открывает браузер на music.yandex.ru.
        Ждёт бесконечно пока пользователь не залогинится.
        Записывает событие в auth_log.
        """
        from db.base import log_auth_event

        driver = self._build_driver()

        try:
            driver.get(MUSIC_URL)
            print("[yandex_fetcher] браузер открыт")
            print("[yandex_fetcher] войди в аккаунт — скрипт ждёт...")

            while True:
                try:
                    if self._is_logged_in(driver):
                        break
                except Exception:
                    pass
                time.sleep(POLL_SECS)

            method = self._detect_auth_method(driver)
            cookie_str = self._cookies_as_str(driver.get_cookies())

            creds = YandexCredentials(cookie=cookie_str)
            data = creds.model_dump()

            self.save_buffer(data)

            # Пишем в auth_log
            log_auth_event(
                provider="yandex",
                method=method,
                note="login successful — session cookies captured",
            )

            print(f"[yandex_fetcher] готово — метод: {method}")
            return data

        except Exception as e:
            raise FetcherError(f"Yandex fetch failed: {e}") from e
        finally:
            driver.quit()
