"""
services/transfer_service.py

Запускает все pending пары из таблицы transfer.
Пишет статистику в transfer.matched/partial/not_found.
Обновляет playlist.copied.
"""

import os
import re
from datetime import datetime, timezone
from uuid import uuid4

from dotenv import load_dotenv

load_dotenv()

from db.base import SessionLocal
from db.playlist_models import Playlist, Transfer
from services.spotify_api import (
    add_tracks_to_playlist,
    extract_playlist_id,
    search_track,
)
from services.yandex_api import get_tracks


def _kind_from_url(url: str) -> str:
    m = re.search(r"/playlists/(\d+)", url)
    return m.group(1) if m else url.strip()


def _run_one(link: Transfer, session) -> None:
    uid = os.getenv("YANDEX_UID", "")
    kind = _kind_from_url(link.from_playlist.url)
    spotify_id = extract_playlist_id(link.to_playlist.url)

    print(f"\n[run] {link.from_playlist.name} → {link.to_playlist.name}")

    tracks = get_tracks(uid, kind)
    link.total = len(tracks)
    link.status = "running"
    session.commit()

    spotify_ids = []
    matched = partial = not_found = 0

    for t in tracks:
        result = search_track(t["title"], t["artist"])
        if result and result["status"] == "matched":
            matched += 1
            spotify_ids.append(result["id"])
            print(f"  [+] {t['artist']} — {t['title']}")
        elif result and result["status"] == "partial":
            partial += 1
            spotify_ids.append(result["id"])
            print(
                f"  [~] {t['artist']} — {t['title']}  →  {result['artist']} — {result['title']}"
            )
        else:
            not_found += 1
            print(f"  [-] {t['artist']} — {t['title']}")

    if spotify_ids:
        add_tracks_to_playlist(spotify_id, spotify_ids)

    link.matched = matched
    link.partial = partial
    link.not_found = not_found
    link.status = "done"
    link.from_playlist.copied = True
    session.commit()

    print(f"[run] итог — matched:{matched} partial:{partial} not_found:{not_found}")


def run_all() -> list[dict]:
    """Запускает все pending пары. Возвращает итоговую статистику."""
    results = []

    with SessionLocal() as session:
        links = session.query(Transfer).filter(Transfer.status == "pending").all()

        if not links:
            print("[run] нет pending связей — добавь через playlist link")
            return []

        print(f"[run] найдено {len(links)} пар для переноса")

        for link in links:
            try:
                _run_one(link, session)
                results.append(
                    {
                        "from": link.from_playlist.name,
                        "to": link.to_playlist.name,
                        "status": link.status,
                        "total": link.total,
                        "matched": link.matched,
                        "partial": link.partial,
                        "not_found": link.not_found,
                    }
                )
            except Exception as e:
                link.status = "error"
                session.commit()
                print(f"[run] ошибка: {e}")
                results.append(
                    {
                        "from": link.from_playlist.name,
                        "to": link.to_playlist.name,
                        "status": f"error: {e}",
                        "total": 0,
                        "matched": 0,
                        "partial": 0,
                        "not_found": 0,
                    }
                )

    return results


def get_stats(transfer_id: str | None = None) -> list[dict]:
    with SessionLocal() as session:
        q = session.query(Transfer)
        if transfer_id:
            q = q.filter(Transfer.id == transfer_id)
        rows = q.order_by(Transfer.timestamp.desc()).all()
        return [
            {
                "id": str(r.id)[:8] + "...",
                "date": str(r.timestamp)[:19],
                "status": r.status,
                "from": r.from_playlist.name or "-",
                "to": r.to_playlist.name or "-",
                "total": r.total,
                "matched": r.matched,
                "partial": r.partial,
                "not_found": r.not_found,
            }
            for r in rows
        ]
