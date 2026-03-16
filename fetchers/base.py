"""fetchers/base.py — базовый fetcher с буферной логикой."""

import json
from pathlib import Path

from core.exceptions import BufferEmptyError
from core.interfaces import AbstractFetcher

CREDS_DIR = Path("credentials")


class BaseFetcher(AbstractFetcher):
    """
    Общая логика буфера. Подклассы реализуют только fetch().
    """

    provider: str = ""

    @property
    def buffer_path(self) -> Path:
        CREDS_DIR.mkdir(exist_ok=True)
        return CREDS_DIR / f"{self.provider}.json"

    def save_buffer(self, data: dict) -> None:
        self.buffer_path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
        print(f"[{self.provider}_fetcher] буфер сохранён → {self.buffer_path}")

    def load_buffer(self) -> dict:
        if not self.buffer_path.exists():
            raise BufferEmptyError(
                f"Буфер не найден: {self.buffer_path}. Сначала запусти -f."
            )
        return json.loads(self.buffer_path.read_text())
