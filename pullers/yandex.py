"""pullers/yandex.py — получает куки с music.yandex.ru."""

import re as _re
import time

import undetected_chromedriver as uc
from tabulate import tabulate

from core.exceptions import PullerError
from core.models import YandexCredentials
from db.models import LogLevel
from pullers.base import BasePuller
from services.log_service import write_log

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
        driver = uc.Chrome(options=opts)
        # Патчим __del__ чтобы подавить WinError 6 на Windows
        driver.__class__.__del__ = lambda self: None
        return driver

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

            # uid из куки yandexuid (живёт на .yandex.ru, парсим из строки)
            _UID_NAMES = {"yandex_uid", "yandexuid", "uid"}
            uid = next(
                (ck["value"] for ck in cookies if ck["name"] in _UID_NAMES),
                None,
            )
            cookie_str = self._cookies_as_str(cookies)

            if not uid:
                m = _re.search(r"yandexuid=(\d+)", cookie_str)
                uid = m.group(1) if m else None
            if not uid:
                m = _re.search(r"Session_id=3:(\d+)[.:]", cookie_str)
                uid = m.group(1) if m else None

            if uid:
                print(f"[yandex_puller] uid: {uid}")
            else:
                print(
                    "[yandex_puller] uid не найден — добавь YANDEX_UID в .env вручную"
                )

            creds = YandexCredentials(cookie=cookie_str, uid=uid)
            data = creds.model_dump()

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
            write_log(
                f"[yandex_puller] куки получены, uid={uid}, cookies={len(cookies)} шт."
            )

            self.save_buffer(data)
            write_log("[yandex_puller] буфер сохранён → credentials/yandex.json")

            return data

        except Exception as e:
            write_log(f"[yandex_puller] failed: {e}", LogLevel.error)
            raise PullerError(f"[yandex_puller] failed: {e}") from e
        finally:
            try:
                driver.quit()
            except Exception:
                pass
