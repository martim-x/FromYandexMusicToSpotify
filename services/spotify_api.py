"""
services/spotify_api.py - поиск треков и добавление в плейлист Spotify.
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
MAX_WORKERS = 2
_MIN_INTERVAL = 0.15

_search_lock = threading.Lock()
_last_request_time = 0.0


def _headers() -> dict:
    load_dotenv(override=True)
    token = os.getenv("SPOTIFY_ACCESS_TOKEN", "")
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _rate_limited_get(url: str, **kwargs) -> requests.Response:
    """GET с глобальным rate limit — не чаще 1 запроса в 150ms."""
    global _last_request_time
    with _search_lock:
        now = time.time()
        wait = _MIN_INTERVAL - (now - _last_request_time)
        if wait > 0:
            time.sleep(wait)
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


def search_track(title: str, artist: str) -> dict | None:
    """
    Ищет трек по названию и исполнителю.
    status: matched | partial
    Возвращает None если не найдено.
    """

    def _search(q: str) -> list:
        for attempt in range(3):
            resp = _rate_limited_get(
                f"{BASE_URL}/search",
                headers=_headers(),
                params={"q": q, "type": "track", "limit": 1},
                timeout=15,
            )
            if resp.status_code == 429:
                retry_after = int(resp.headers.get("Retry-After", 5))
                write_log(
                    f"spotify search: rate limit, retry after {retry_after}s "
                    f"| attempt={attempt + 1} q='{q}'",
                    level=LogLevel.warn,
                )
                time.sleep(retry_after)
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

    items = _search(f"track:{title} artist:{artist}")
    if items:
        item = items[0]
        return {
            "id": item["id"],
            "title": item["name"],
            "artist": _artist_name(item),
            "status": "matched",
        }

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


def add_tracks_to_playlist(playlist_id: str, track_ids: list[str]) -> None:
    """Добавляет треки в плейлист батчами по 100 (лимит Spotify API)."""
    total = len(track_ids)
    for i in range(0, total, 100):
        batch = [f"spotify:track:{tid}" for tid in track_ids[i : i + 100]]
        resp = requests.post(
            f"{BASE_URL}/playlists/{playlist_id}/tracks",
            headers=_headers(),
            json={"uris": batch},
            timeout=15,
        )
        resp.raise_for_status()
        added = i + len(batch)
        write_log(
            f"spotify add tracks: batch {i // 100 + 1} — "
            f"{added}/{total} tracks → playlist {playlist_id[:8]}",
        )
        print(t("spotify_api.added_batch", done=added, total=total))
