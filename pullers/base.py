"""pullers/base.py - базовый puller с буферной логикой."""

import json
from pathlib import Path

from core.exceptions import BufferEmptyError
from core.interfaces import AbstractPuller

CREDS_DIR = Path("credentials")


class BasePuller(AbstractPuller):
    provider: str = ""

    @property
    def buffer_path(self) -> Path:
        CREDS_DIR.mkdir(exist_ok=True)
        return CREDS_DIR / f"{self.provider}.json"

    def save_buffer(self, data: dict) -> None:
        self.buffer_path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
        print(f"[{self.provider}_puller] буфер → {self.buffer_path}")

    def load_buffer(self) -> dict:
        if not self.buffer_path.exists():
            raise BufferEmptyError(f"буфер не найден: {self.buffer_path} — запусти -f")
        return json.loads(self.buffer_path.read_text())
