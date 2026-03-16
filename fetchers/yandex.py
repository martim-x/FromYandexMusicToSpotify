"""fetchers/yandex.py — получает куки с music.yandex.ru."""

import time

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from core.exceptions import FetcherError
from core.models import YandexCredentials
from fetchers.base import BaseFetcher


class YandexFetcher(BaseFetcher):
    provider = "yandex"

    def _build_driver(self) -> uc.Chrome:
        opts = uc.ChromeOptions()
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        return uc.Chrome(options=opts)

    def _cookies_as_str(self, cookies: list[dict]) -> str:
        return "; ".join(f"{c['name']}={c['value']}" for c in cookies)

    def fetch(self, login: str, password: str, **_) -> dict:
        """
        Логинится на Яндекс, переходит на music.yandex.ru,
        возвращает только строку куков. Пароль не сохраняется.
        """
        driver = self._build_driver()
        wait = WebDriverWait(driver, 20)

        try:
            print("[yandex_fetcher] логин...")
            driver.get("https://passport.yandex.ru/auth")

            wait.until(EC.presence_of_element_located((By.NAME, "login")))
            driver.find_element(By.NAME, "login").send_keys(login)
            driver.find_element(By.XPATH, "//button[@type='submit']").click()

            wait.until(EC.presence_of_element_located((By.NAME, "passwd")))
            driver.find_element(By.NAME, "passwd").send_keys(password)
            driver.find_element(By.XPATH, "//button[@type='submit']").click()

            wait.until(EC.url_contains("yandex.ru"))
            time.sleep(2)

            driver.get("https://music.yandex.ru")
            time.sleep(3)

            cookie_str = self._cookies_as_str(driver.get_cookies())

            creds = YandexCredentials(cookie=cookie_str)
            data = creds.model_dump()

            self.save_buffer(data)
            print(f"[yandex_fetcher] готово — куки получены")
            return data

        except Exception as e:
            raise FetcherError(f"Yandex fetch failed: {e}") from e
        finally:
            driver.quit()
