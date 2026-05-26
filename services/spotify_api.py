"""
services/spotify_api.py - поиск треков и добавление в плейлист Spotify.

Изменения:
- TRACK_LIMIT = 10  — временное ограничение треков на трансфер
- _MIN_INTERVAL = 0.5  — было 0.15, снижаем давление на API (≈2 req/s вместо 6-7)
- search_track() принимает stop_event: threading.Event | None
  └─ все потоки немедленно прекращают работу когда watchdog сигналит
- _search() проверяет stop_event перед каждой попыткой и перед sleep(retry_after)
  └─ это решает проблему когда поток висит в sleep и не реагирует на отмену
"""

import os
import re
import threading
import time

import requests
from dotenv import load_dotenv

from db.models import LogLevel
from i18n import t
from services.log_service import write_log

load_dotenv()

BASE_URL = "https://api.spotify.com/v1"

# ── Константы ─────────────────────────────────────────────────────────────

# Временное ограничение: обрабатывать не более N треков за один трансфер.
# Убрать или увеличить когда будешь готов к полному прогону.
TRACK_LIMIT = 500

# Минимальный интервал между запросами к Spotify Search.
# 0.5s = ~2 req/s в одном потоке.
# При MAX_WORKERS=4 это даёт ~8 req/s суммарно — всё ещё в пределах dev mode.
# Spotify официально не публикует точный лимит, но rolling 30s window:
# безопасная зона для dev mode — не более ~180 req/30s.
_MIN_INTERVAL = 0.5

_search_lock = threading.Lock()
_last_request_time = 0.0


def _headers() -> dict:
    load_dotenv(override=True)
    token = os.getenv("SPOTIFY_ACCESS_TOKEN", "")
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _rate_limited_get(
    url: str,
    stop_event: threading.Event | None = None,
    **kwargs,
) -> requests.Response:
    """
    GET с глобальным rate limit — не чаще 1 запроса в _MIN_INTERVAL секунд.
    Если stop_event выставлен во время ожидания — поднимает RuntimeError
    чтобы прервать поток без лишних запросов.
    """
    global _last_request_time
    with _search_lock:
        now = time.time()
        wait = _MIN_INTERVAL - (now - _last_request_time)
        if wait > 0:
            # Ждём маленькими шагами чтобы stop_event мог прервать ожидание
            deadline = now + wait
            while time.time() < deadline:
                if stop_event and stop_event.is_set():
                    raise RuntimeError("stop_event: search cancelled")
                time.sleep(0.05)
        _last_request_time = time.time()
    return requests.get(url, **kwargs)


def get_playlist_info(playlist_id: str) -> dict:
    resp = requests.get(
        f"{BASE_URL}/playlists/{playlist_id}", headers=_headers(), timeout=15
    )
    resp.raise_for_status()
    data = resp.json()
    return {
        "id": playlist_id,
        "name": data.get("name", ""),
        "url": data.get("external_urls", {}).get("spotify", ""),
    }


def _artist_name(track: dict) -> str:
    """Безопасно достаёт имя первого артиста."""
    artists = track.get("artists") or []
    return artists[0]["name"] if artists else "Unknown"


def extract_playlist_id(url_or_id: str) -> str:
    clean = url_or_id.split("?")[0].split("#")[0]
    match = re.search(r"playlist/([A-Za-z0-9]+)", clean)
    return match.group(1) if match else clean.strip()


def search_track(
    title: str,
    artist: str,
    stop_event: threading.Event | None = None,
) -> dict | None:
    """
    Ищет трек по названию и исполнителю.

    stop_event — threading.Event из transfer_service.
    Если выставлен, поток немедленно прекращает попытки и возвращает None.

    Возвращает dict со статусом matched | partial, или None если не найдено.
    """

    def _search(q: str) -> list:
        for attempt in range(3):
            # Проверяем stop_event ПЕРЕД каждой попыткой
            if stop_event and stop_event.is_set():
                write_log(
                    f"spotify search: cancelled by stop_event | q='{q}'",
                    level=LogLevel.warn,
                )
                return []

            try:
                resp = _rate_limited_get(
                    f"{BASE_URL}/search",
                    stop_event=stop_event,
                    headers=_headers(),
                    params={"q": q, "type": "track", "limit": 1},
                    timeout=15,
                )
            except RuntimeError:
                # stop_event сработал во время ожидания rate limit
                return []

            if resp.status_code == 429:
                retry_after = int(resp.headers.get("Retry-After", 5))
                write_log(
                    f"spotify search: rate limit, retry after {retry_after}s "
                    f"| attempt={attempt + 1} q='{q}'",
                    level=LogLevel.warn,
                )
                # Ждём retry_after маленькими шагами — stop_event может прервать
                deadline = time.time() + retry_after
                while time.time() < deadline:
                    if stop_event and stop_event.is_set():
                        write_log(
                            f"spotify search: cancelled during retry sleep | q='{q}'",
                            level=LogLevel.warn,
                        )
                        return []
                    time.sleep(0.1)
                continue

            if resp.status_code != 200:
                write_log(
                    f"spotify search: HTTP {resp.status_code} "
                    f"| attempt={attempt + 1} q='{q}'",
                    level=LogLevel.error,
                )
                return []

            return resp.json().get("tracks", {}).get("items", [])

        write_log(
            f"spotify search: all attempts exhausted | q='{q}'", level=LogLevel.error
        )
        return []

    # Попытка 1: точный поиск по треку и артисту
    items = _search(f"track:{title} artist:{artist}")
    if items:
        item = items[0]
        return {
            "id": item["id"],
            "title": item["name"],
            "artist": _artist_name(item),
            "status": "matched",
        }

    # Попытка 2: поиск только по названию (partial match)
    if stop_event and stop_event.is_set():
        return None

    items = _search(f"track:{title}")
    if items:
        item = items[0]
        return {
            "id": item["id"],
            "title": item["name"],
            "artist": _artist_name(item),
            "status": "partial",
        }

    return None


def debug_search(title: str, artist: str) -> None:
    load_dotenv(override=True)
    token = os.getenv("SPOTIFY_ACCESS_TOKEN", "")
    token_display = f"{token[:10]}...{token[-6:]}" if len(token) > 16 else "(empty)"
    print(t("spotify_api.debug_token", token=token_display))
    q = f"track:{title} artist:{artist}"
    resp = requests.get(
        f"{BASE_URL}/search",
        headers=_headers(),
        params={"q": q, "type": "track", "limit": 1},
        timeout=15,
    )
    print(f"[debug] status: {resp.status_code}")
    print(f"[debug] response: {resp.text[:500]}")


def _mask_auth(headers: dict) -> dict:
    masked = dict(headers)
    auth = masked.get("Authorization")
    if auth and auth.startswith("Bearer "):
        token = auth[7:]
        if len(token) > 20:
            masked["Authorization"] = f"Bearer {token[:10]}...{token[-6:]}"
        else:
            masked["Authorization"] = "Bearer ***"
    return masked


def _print_prepared_request(
    method: str, url: str, headers: dict, json_body=None, params=None
) -> None:
    req = requests.Request(
        method=method,
        url=url,
        headers=headers,
        json=json_body,
        params=params,
    )
    prepared = req.prepare()

    safe_headers = _mask_auth(dict(prepared.headers))

    body = prepared.body
    if isinstance(body, bytes):
        body = body.decode("utf-8", errors="replace")

    print("\n[spotify_api] ===== OUTGOING REQUEST =====")
    print(f"{prepared.method} {prepared.url}")
    for k, v in safe_headers.items():
        print(f"{k}: {v}")
    print()
    print(body if body is not None else "(no body)")
    print("[spotify_api] ============================\n")


def add_tracks_to_playlist(playlist_id: str, track_ids: list[str]) -> None:
    total = len(track_ids)
    for i in range(0, total, 100):
        batch = [f"spotify:track:{tid}" for tid in track_ids[i : i + 100]]
        url = f"{BASE_URL}/playlists/{playlist_id}/items"
        headers = _headers()
        body = {"uris": batch}

        _print_prepared_request(
            method="POST",
            url=url,
            headers=headers,
            json_body=body,
        )

        resp = requests.post(
            url,
            headers=headers,
            json=body,
            timeout=15,
        )

        print("[spotify_api] add status:", resp.status_code)
        print("[spotify_api] add body:", resp.text[:1000])

        resp.raise_for_status()
        added = i + len(batch)
        write_log(
            f"spotify add tracks: batch {i // 100 + 1} — "
            f"{added}/{total} tracks → playlist {playlist_id[:8]}",
        )
        print(t("spotify_api.added_batch", done=added, total=total))
