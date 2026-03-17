"""
services/yandex_api.py — получает треки через yandex-music.

Авторизация:
  1. YANDEX_TOKEN в .env  (OAuth токен — предпочтительно)
  2. Если нет — инструкция как получить вручную
"""

import os

from dotenv import load_dotenv

load_dotenv()


def _is_liked_kind(kind: str) -> bool:
    return kind == "3" or kind.startswith("lk.")


def _get_client():
    try:
        from yandex_music import Client
    except ImportError:
        raise ImportError("pip install yandex-music")

    token = os.getenv("YANDEX_TOKEN", "").strip()

    if not token:
        raise ValueError(
            "YANDEX_TOKEN не задан в .env\n\n"
            "Как получить токен:\n"
            "  1. Открой music.yandex.ru в браузере\n"
            "  2. DevTools (F12) → Network → выбери любой XHR запрос\n"
            "  3. Headers → Request Headers → Authorization: OAuth xxxxxxxx\n"
            "  4. Скопируй значение после 'OAuth ' и добавь в .env:\n"
            "     YANDEX_TOKEN=xxxxxxxx\n"
        )

    return Client(token).init()


def get_tracks(uid: str, kind: str) -> list[dict]:
    """Возвращает список { title, artist } из плейлиста."""
    client = _get_client()

    if _is_liked_kind(kind):
        return _get_liked(client, uid)
    else:
        return _get_playlist(client, uid, kind)


def _get_liked(client, uid: str) -> list[dict]:
    liked = client.users_likes_tracks(uid)
    if not liked:
        return []
    ids = [f"{t.id}:{t.album_id}" for t in liked if t.id and t.album_id]
    if not ids:
        return []
    tracks = client.tracks(ids)
    return _parse(tracks)


def _get_playlist(client, uid: str, kind: str) -> list[dict]:
    pl = client.users_playlists(kind=kind, user_id=uid)
    if not pl or not pl.tracks:
        return []
    ids = [f"{t.id}:{t.album_id}" for t in pl.tracks if t.id and t.album_id]
    if not ids:
        return []
    tracks = client.tracks(ids)
    return _parse(tracks)


def _parse(tracks) -> list[dict]:
    result = []
    for t in tracks or []:
        if not t or not t.title:
            continue
        artists = ", ".join(a.name for a in (t.artists or []))
        result.append({"title": t.title, "artist": artists})
    print(f"[yandex_api] треков: {len(result)}")
    return result
