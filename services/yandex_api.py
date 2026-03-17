"""
services/yandex_api.py - получает треки из плейлиста Яндекс Музыки.
Использует YANDEX_COOKIE из .env.
"""

import os

import requests
from dotenv import load_dotenv

load_dotenv()

_BASE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Referer": "https://music.yandex.ru/",
    "X-Requested-With": "XMLHttpRequest",
}


def _headers() -> dict:
    return {**_BASE_HEADERS, "Cookie": os.getenv("YANDEX_COOKIE", "")}


def get_playlist_info(uid: str, kind: str) -> dict:
    url = (
        f"https://music.yandex.ru/api/v2.1/handlers/playlist/{uid}/{kind}"
        f"?lang=ru&external-domain=music.yandex.ru&overembed=false"
    )
    resp = requests.get(url, headers=_headers(), timeout=15)
    resp.raise_for_status()
    playlist = resp.json().get("playlist", resp.json())
    return {
        "id": str(kind),
        "name": playlist.get("title", ""),
        "url": f"https://music.yandex.ru/users/{uid}/playlists/{kind}",
    }


def get_tracks(uid: str, kind: str) -> list[dict]:
    """Возвращает список { title, artist } из плейлиста."""
    url = (
        f"https://music.yandex.ru/api/v2.1/handlers/playlist/{uid}/{kind}"
        f"?what=tracks&lang=ru&external-domain=music.yandex.ru"
    )
    resp = requests.get(url, headers=_headers(), timeout=15)
    resp.raise_for_status()
    raw = resp.json().get("tracks", [])
    tracks = [
        {
            "title": t.get("title", ""),
            "artist": ", ".join(a["name"] for a in t.get("artists", [])),
        }
        for t in raw
        if t.get("title")
    ]
    print(f"[yandex_api] треков получено: {len(tracks)}")
    return tracks
