"""
services/spotify_api.py - поиск треков и добавление в плейлист Spotify.
Использует SPOTIFY_ACCESS_TOKEN из .env.
"""

import os
import re

import requests
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "https://api.spotify.com/v1"


def _headers() -> dict:
    token = os.getenv("SPOTIFY_ACCESS_TOKEN", "")
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def get_playlist_info(playlist_id: str) -> dict:
    """Получает название и url плейлиста Spotify."""
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


def extract_playlist_id(url_or_id: str) -> str:
    """Принимает URL или голый ID плейлиста Spotify."""
    match = re.search(r"playlist/([A-Za-z0-9]+)", url_or_id)
    return match.group(1) if match else url_or_id.strip()


def search_track(title: str, artist: str) -> dict | None:
    """
    Ищет трек по названию и исполнителю.
    Возвращает { id, title, artist, status } или None.

    status:
      matched  — точное совпадение artist+title
      partial  — совпало только название
      not_found
    """

    def _search(q: str) -> list:
        resp = requests.get(
            f"{BASE_URL}/search",
            headers=_headers(),
            params={"q": q, "type": "track", "limit": 1},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json().get("tracks", {}).get("items", [])

    # Точный поиск
    items = _search(f"track:{title} artist:{artist}")
    if items:
        t = items[0]
        return {
            "id": t["id"],
            "title": t["name"],
            "artist": t["artists"][0]["name"],
            "status": "matched",
        }

    # Частичный — только по названию
    items = _search(f"track:{title}")
    if items:
        t = items[0]
        return {
            "id": t["id"],
            "title": t["name"],
            "artist": t["artists"][0]["name"],
            "status": "partial",
        }

    return None


def add_tracks_to_playlist(playlist_id: str, track_ids: list[str]) -> None:
    """Добавляет треки в плейлист батчами по 100 (лимит Spotify)."""
    for i in range(0, len(track_ids), 100):
        batch = [f"spotify:track:{tid}" for tid in track_ids[i : i + 100]]
        resp = requests.post(
            f"{BASE_URL}/playlists/{playlist_id}/tracks",
            headers=_headers(),
            json={"uris": batch},
            timeout=15,
        )
        resp.raise_for_status()
        print(f"[spotify_api] добавлено {i + len(batch)} / {len(track_ids)}")
