"""core/spinner.py — консольный спиннер."""

import sys
import threading
import time

_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]


class Spinner:
    def __init__(self, label: str = "", total: int = 0) -> None:
        self.label = label
        self.total = total
        self._count = 0
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._spin, daemon=True)

    def _spin(self) -> None:
        i = 0
        while not self._stop.is_set():
            frame = _FRAMES[i % len(_FRAMES)]
            if self.total:
                pct = int(self._count / self.total * 100)
                done = pct // 5
                bar = "█" * done + "░" * (20 - done)
                line = f"\r  {frame}  {self.label}  {bar} {self._count}/{self.total} ({pct}%)"
            else:
                line = f"\r  {frame}  {self.label}"
            sys.stdout.write(line)
            sys.stdout.flush()
            self._stop.wait(0.1)
            i += 1

    def update(self, count: int) -> None:
        self._count = count

    def __enter__(self) -> "Spinner":
        self._thread.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self._stop.set()
        self._thread.join(timeout=1)
        sys.stdout.write("\r" + " " * 80 + "\r")
        sys.stdout.flush()
        # Не глотаем KeyboardInterrupt — пробрасываем наверх
        return False
