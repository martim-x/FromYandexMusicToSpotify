"""
test_apis.py — быстрая проверка что оба API работают.
Запускать: py test_apis.py
"""

import os

import requests
from dotenv import load_dotenv

load_dotenv(override=True)


def sep(title):
    print(f"\n{'─'*40}")
    print(f"  {title}")
    print("─" * 40)


# ── Яндекс ──────────────────────────────────
sep("ЯНДЕКС API")

cookie = os.getenv("YANDEX_COOKIE", "")
uid = os.getenv("YANDEX_UID", "")

print(f"YANDEX_COOKIE : {'OK ' + cookie[:12] + '...' if cookie else 'MISSING'}")
print(f"YANDEX_UID    : {uid or 'MISSING'}")

if cookie and uid:
    url = f"https://api.music.yandex.ru/users/{uid}/likes/tracks"
    resp = requests.get(
        url,
        headers={
            "Cookie": cookie,
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json",
        },
        timeout=10,
    )
    print(f"likes/tracks  : status={resp.status_code} len={len(resp.text)}")
    if resp.status_code == 200:
        data = resp.json()
        result = data.get("result", {})
        tracks = result.get("library", {}).get("tracks", [])
        print(f"треков в лайках: {len(tracks)}")
        print("✓ Яндекс работает")
    else:
        print(f"✗ ответ: {resp.text[:200]}")

# ── Spotify ──────────────────────────────────
sep("SPOTIFY API")

token = os.getenv("SPOTIFY_ACCESS_TOKEN", "")
print(f"ACCESS_TOKEN  : {'OK ' + token[:12] + '...' if token else 'MISSING'}")

if token:
    # Тест 1: профиль
    r1 = requests.get(
        "https://api.spotify.com/v1/me",
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
    )
    print(f"GET /me        : status={r1.status_code}")
    if r1.status_code == 200:
        me = r1.json()
        print(f"  пользователь : {me.get('display_name')} ({me.get('id')})")
    else:
        print(f"  ответ: {r1.text[:200]}")

    # Тест 2: поиск одного трека
    r2 = requests.get(
        "https://api.spotify.com/v1/search",
        headers={"Authorization": f"Bearer {token}"},
        params={"q": "track:Sandstorm artist:Darude", "type": "track", "limit": 1},
        timeout=10,
    )
    print(f"GET /search    : status={r2.status_code}")
    if r2.status_code == 200:
        items = r2.json().get("tracks", {}).get("items", [])
        print(f"  найдено      : {items[0]['name'] if items else 'ничего'}")
        print("✓ Spotify работает")
    elif r2.status_code == 429:
        retry = r2.headers.get("Retry-After", "не указан")
        print(f"✗ Rate limit — Retry-After: {retry} секунд")
    else:
        print(f"✗ ответ: {r2.text[:200]}")

print("\n")





# FromYandexMusicToSpotify
# App description
# A personal utility that transfers music libraries between Yandex Music and Spotify. Reads playlists from Yandex Music and recreates them in Spotify using the Web API.
# Website
# Redirect URIs
# http://127.0.0.1:8888/callback