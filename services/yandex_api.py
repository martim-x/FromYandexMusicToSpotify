"""
services/yandex_api.py — треки из Яндекс Музыки.

GET api.music.yandex.ru/users/{uid}/likes/tracks → ids
POST api.music.yandex.ru/tracks → детали
"""

import os
import re as _re
import time

import requests
from dotenv import load_dotenv

from i18n import t

load_dotenv(override=True)

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
    "Referer": "https://music.yandex.ru/",
    "Accept-Language": "ru,en;q=0.9",
}

_BATCH_SIZE = 200
_BATCH_DELAY = 1.0
_RETRY_DELAYS = [1.0, 3.0, 5.0]


def _h() -> dict:
    load_dotenv(override=True)
    return {**_HEADERS, "Cookie": os.getenv("YANDEX_COOKIE", "")}


def _is_json(resp) -> bool:
    ct = resp.headers.get("Content-Type", "")
    return "application/json" in ct or (
        resp.text.strip().startswith("{") or resp.text.strip().startswith("[")
    )


def _is_liked(kind: str) -> bool:
    return kind == "3" or kind.startswith("lk.")


def get_tracks(uid: str, kind: str) -> list[dict]:
    if _is_liked(kind):
        owner_uid = uid
        if kind.startswith("lk."):
            m = _re.match(r"lk\.(\d+)", kind)
            if m:
                owner_uid = m.group(1)
        return _liked_tracks(owner_uid)
    return _playlist_tracks(uid, kind)


def _liked_tracks(uid: str) -> list[dict]:
    track_ids = _get_liked_ids(uid)
    if not track_ids:
        raise ValueError(t("error.yandex_likes_empty"))
    # debug print — не локализуется (внутренний вывод)
    print(f"[yandex_api] likes: {len(track_ids)}, fetching details...")
    return _fetch_by_ids(track_ids)


def _get_liked_ids(uid: str) -> list[str]:
    url = f"https://api.music.yandex.ru/users/{uid}/likes/tracks"
    resp = requests.get(url, headers=_h(), timeout=30)
    print(f"[yandex_api] likes/tracks: {resp.status_code} len={len(resp.text)}")

    if resp.status_code != 200 or not resp.text.strip():
        return []

    if not _is_json(resp):
        print("[yandex_api] cookies expired — got HTML instead of JSON")
        raise ValueError(t("error.yandex_cookie_expired"))

    data = resp.json()
    result = data.get("result", data)
    tracks = (
        result.get("library", {}).get("tracks")
        or result.get("tracks")
        or (result if isinstance(result, list) else [])
    )
    print(f"[yandex_api] ids: {len(tracks)}")

    ids: list[str] = []
    for item in tracks:
        if isinstance(item, dict):
            tid = item.get("id") or item.get("trackId")
            aid = item.get("albumId") or ""
            if tid:
                ids.append(f"{tid}:{aid}")
        elif isinstance(item, (int, str)):
            ids.append(str(item))
    return ids


def _fetch_by_ids(track_ids: list[str]) -> list[dict]:
    """Батчевый POST с паузой и retry при HTML (rate limit?)."""
    result: list[dict] = []
    total = len(track_ids)

    for i in range(0, total, _BATCH_SIZE):
        batch = track_ids[i : i + _BATCH_SIZE]
        print(
            f"[yandex_api] batch {i}: size={len(batch)} "
            f"({i + 1}-{min(i + _BATCH_SIZE, total)}/{total})"
        )

        success = False

        for attempt, delay in enumerate(_RETRY_DELAYS, start=1):
            try:
                resp = requests.post(
                    "https://api.music.yandex.ru/tracks",
                    headers={
                        **_h(),
                        "Content-Type": "application/x-www-form-urlencoded",
                    },
                    data={
                        "trackIds": ",".join(batch),
                        "removeDuplicates": "false",
                        "withProgress": "true",
                    },
                    timeout=30,
                )
                print(
                    f"[yandex_api] /tracks {i + 1}-{min(i + _BATCH_SIZE, total)}/{total}: "
                    f"{resp.status_code}, attempt {attempt}"
                )

                if resp.status_code == 200 and resp.text.strip() and _is_json(resp):
                    data = resp.json()
                    raw = data.get("result", data)
                    if isinstance(raw, list):
                        result.extend(_parse(raw))
                    success = True
                    break

                if not _is_json(resp):
                    print(
                        f"[yandex_api] batch {i}: HTML (rate limit?), "
                        f"retrying in {delay:.1f}s..."
                    )
                    time.sleep(delay)
                    continue

            except Exception as e:
                print(f"[yandex_api] batch {i} error: {e}")
                print(f"[yandex_api] batch {i}: retrying in {delay:.1f}s...")
                time.sleep(delay)
                continue

        if not success:
            print(f"[yandex_api] batch {i} failed after {len(_RETRY_DELAYS)} attempts")

        time.sleep(_BATCH_DELAY)

    return result


def _playlist_tracks(uid: str, kind: str) -> list[dict]:
    url = (
        f"https://music.yandex.ru/api/v2.1/handlers/playlist/{uid}/{kind}"
        f"?what=tracks&lang=ru&external-domain=music.yandex.ru"
    )
    resp = requests.get(url, headers=_h(), timeout=30)
    resp.raise_for_status()
    if not resp.text.strip():
        raise ValueError(t("error.yandex_empty_response", kind=kind))
    return _parse(resp.json().get("tracks", []))


def _parse(raw: list) -> list[dict]:
    result: list[dict] = []
    for item in raw:
        title = item.get("title", "")
        artists_list = item.get("artists", [])
        artists = ", ".join(a["name"] for a in artists_list if "name" in a)
        if title:
            result.append(
                {
                    "title": title,
                    "artist": artists or "Unknown",
                    "yandex_id": str(item.get("id", "")),
                    "album": (item.get("albums") or [{}])[0].get("title"),
                    "year": (item.get("albums") or [{}])[0].get("year"),
                    "duration_ms": item.get("durationMs"),
                }
            )
    return result
