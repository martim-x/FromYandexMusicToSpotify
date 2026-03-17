"""pullers/yandex.py — получает куки с music.yandex.ru."""

import time

import undetected_chromedriver as uc
from tabulate import tabulate

from core.exceptions import PullerError
from core.models import YandexCredentials
from pullers.base import BasePuller

MUSIC_URL = "https://music.yandex.ru"
POLL_SECS = 2
SESSION_KEYS = {"Session_id", "yandex_login", "L"}


class YandexPuller(BasePuller):
    provider = "yandex"

    def _build_driver(self) -> uc.Chrome:
        import platform

        opts = uc.ChromeOptions()
        if platform.system() != "Windows":
            opts.add_argument("--no-sandbox")
            opts.add_argument("--disable-dev-shm-usage")
        return uc.Chrome(options=opts)

    def _cookies_as_str(self, cookies: list[dict]) -> str:
        return "; ".join(f"{c['name']}={c['value']}" for c in cookies)

    def _is_logged_in(self, driver: uc.Chrome) -> bool:
        names = {c["name"] for c in driver.get_cookies()}
        return bool(names & SESSION_KEYS)

    def _detect_auth_method(self, driver: uc.Chrome) -> str:
        try:
            src = driver.page_source.lower()
            if "push" in src or "уведомлени" in src:
                return "push_notification"
            if "phone" in src or "телефон" in src or "смс" in src:
                return "phone"
        except Exception:
            pass
        return "cookie"

    def pull(self, **_) -> dict:
        from db.base import log_auth_event

        driver = self._build_driver()
        try:
            driver.get(MUSIC_URL)
            print("[yandex_puller] браузер открыт — войди в аккаунт, скрипт ждёт...")

            while True:
                try:
                    if self._is_logged_in(driver):
                        break
                except Exception:
                    pass
                time.sleep(POLL_SECS)

            method = self._detect_auth_method(driver)
            cookies = driver.get_cookies()

            import re as _re

            # 1. Ищем в объектах куков (music.yandex.ru домен)
            _UID_NAMES = {"yandex_uid", "yandexuid", "uid"}
            uid = next(
                (ck["value"] for ck in cookies if ck["name"] in _UID_NAMES),
                None,
            )

            # 2. Парсим из строки куков — yandexuid живёт на .yandex.ru
            #    и не попадает в driver.get_cookies() для music.yandex.ru
            if not uid:
                m = _re.search(r"yandexuid=(\d+)", cookie_str)
                if m:
                    uid = m.group(1)

            # 3. Запасной вариант — из Session_id=3:UID:...
            if not uid:
                m = _re.search(r"Session_id=3:(\d+)[.:]", cookie_str)
                if m:
                    uid = m.group(1)

            if uid:
                print(f"[yandex_puller] uid найден: {uid}")
            else:
                print(
                    "[yandex_puller] uid не найден автоматически.\n"
                    "  Добавь вручную в .env: YANDEX_UID=твой_uid\n"
                    "  Uid виден в URL плейлиста: music.yandex.ru/users/LOGIN/playlists/..."
                )

            cookie_str = self._cookies_as_str(cookies)

            # Пробуем получить OAuth токен из localStorage
            token = None
            try:
                token = driver.execute_script(
                    "return window.__ym && window.__ym.config && window.__ym.config.token || null"
                )
            except Exception:
                pass

            # Если не нашли через JS — ищем в куках
            if not token:
                token = next(
                    (
                        ck["value"]
                        for ck in cookies
                        if ck["name"] in {"yx_token", "yandex_token"}
                    ),
                    None,
                )

            if token:
                print(f"[yandex_puller] OAuth токен найден")
            else:
                print(
                    "[yandex_puller] OAuth токен не найден автоматически\n"
                    "  Добудь вручную:\n"
                    "  1. DevTools → Network → любой запрос к music.yandex.ru\n"
                    "  2. Headers → Authorization: OAuth xxxxx\n"
                    "  3. Добавь в .env: YANDEX_TOKEN=xxxxx"
                )

            creds = YandexCredentials(cookie=cookie_str, uid=uid, token=token)
            data = creds.model_dump()

            self.save_buffer(data)
            log_auth_event("yandex", method, "session cookies captured")

            print(
                tabulate(
                    [
                        ("status", "ok"),
                        ("method", method),
                        ("cookies", f"{len(cookies)} шт."),
                        ("uid", uid or "не найден"),
                    ],
                    headers=["field", "value"],
                    tablefmt="rounded_outline",
                )
            )
            return data

        except Exception as e:
            raise PullerError(f"Yandex pull failed: {e}") from e
        finally:
            try:
                driver.quit()
            except Exception:
                pass  # WinError 6 на Windows — игнорируем
