"""
services/transfer_service.py

Оркестрирует перенос треков из плейлиста Яндекс → Spotify.
Пишет подробную историю в transfer_log + transfer_tracks.
"""

import os
from uuid import uuid4

from dotenv import load_dotenv

load_dotenv()

from db.base import SessionLocal, init_db
from db.transfer_models import TransferLog, TransferTrack
from services.spotify_api import add_tracks_to_playlist, extract_playlist_id
from services.spotify_api import get_playlist_info as sp_playlist_info
from services.spotify_api import search_track
from services.yandex_api import get_playlist_info as ym_playlist_info
from services.yandex_api import get_tracks


def run_transfer(
    yandex_uid: str,
    yandex_kind: str,
    spotify_target: str,
) -> TransferLog:
    """
    Основная функция переноса.

    yandex_uid     — uid пользователя Яндекса (из .env YANDEX_UID)
    yandex_kind    — kind плейлиста (из .env YANDEX_PLAYLIST_KIND)
    spotify_target — URL или ID плейлиста Spotify
    """
    spotify_playlist_id = extract_playlist_id(spotify_target)

    # Мета-данные плейлистов
    print("[transfer] получаем информацию о плейлистах...")
    ym_info = ym_playlist_info(yandex_uid, yandex_kind)
    sp_info = sp_playlist_info(spotify_playlist_id)

    print(f"[transfer] Яндекс  : {ym_info['name']} ({ym_info['url']})")
    print(f"[transfer] Spotify : {sp_info['name']} ({sp_info['url']})")

    # Получаем треки
    tracks = get_tracks(yandex_uid, yandex_kind)

    # Создаём запись в transfer_log
    log = TransferLog(
        id=uuid4(),
        status="running",
        yandex_playlist_id=yandex_kind,
        yandex_playlist_name=ym_info["name"],
        yandex_playlist_url=ym_info["url"],
        spotify_playlist_id=spotify_playlist_id,
        spotify_playlist_name=sp_info["name"],
        spotify_playlist_url=sp_info["url"],
        total=len(tracks),
    )

    track_rows = []
    spotify_ids = []
    matched = partial = not_found = 0

    print(f"\n[transfer] ищем {len(tracks)} треков в Spotify...\n")

    for t in tracks:
        result = search_track(t["title"], t["artist"])

        if result and result["status"] == "matched":
            matched += 1
            spotify_ids.append(result["id"])
            status_mark = "matched"
            print(f"  [+] {t['artist']} — {t['title']}")
        elif result and result["status"] == "partial":
            partial += 1
            spotify_ids.append(result["id"])
            status_mark = "partial"
            print(
                f"  [~] {t['artist']} — {t['title']}  →  {result['artist']} — {result['title']}"
            )
        else:
            not_found += 1
            result = None
            status_mark = "not_found"
            print(f"  [-] {t['artist']} — {t['title']}")

        track_rows.append(
            TransferTrack(
                id=uuid4(),
                transfer_id=log.id,
                yandex_title=t["title"],
                yandex_artist=t["artist"],
                spotify_id=result["id"] if result else None,
                spotify_title=result["title"] if result else None,
                spotify_artist=result["artist"] if result else None,
                status=status_mark,
            )
        )

    # Добавляем найденные треки в плейлист
    if spotify_ids:
        print(f"\n[transfer] добавляем {len(spotify_ids)} треков в Spotify...")
        add_tracks_to_playlist(spotify_playlist_id, spotify_ids)

    # Обновляем статистику в лог
    log.matched = matched
    log.partial = partial
    log.not_found = not_found
    log.status = "done"

    # Сохраняем в БД
    with SessionLocal() as session:
        session.add(log)
        session.add_all(track_rows)
        session.commit()
        session.refresh(log)

    print(f"\n[transfer] завершено:")
    print(f"\t всего      : {log.total}")
    print(f"\t matched    : {log.matched}")
    print(f"\t partial    : {log.partial}")
    print(f"\t not_found  : {log.not_found}")

    return log


def get_stats(transfer_id: str | None = None) -> list[dict]:
    """
    Возвращает статистику по переносам.
    Если transfer_id указан — только по нему.
    """
    with SessionLocal() as session:
        q = session.query(TransferLog)
        if transfer_id:
            q = q.filter(TransferLog.id == transfer_id)
        logs = q.order_by(TransferLog.date.desc()).all()

    return [
        {
            "id": str(l.id),
            "date": str(l.date)[:19],
            "status": l.status,
            "from": f"{l.yandex_playlist_name or l.yandex_playlist_id}",
            "to": f"{l.spotify_playlist_name or l.spotify_playlist_id}",
            "total": l.total,
            "matched": l.matched,
            "partial": l.partial,
            "not_found": l.not_found,
        }
        for l in logs
    ]


def get_transfer_tracks(transfer_id: str) -> list[dict]:
    """Возвращает детальный список треков по конкретному переносу."""
    with SessionLocal() as session:
        rows = (
            session.query(TransferTrack)
            .filter(TransferTrack.transfer_id == transfer_id)
            .order_by(TransferTrack.status)
            .all()
        )
    return [
        {
            "status": r.status,
            "yandex_artist": r.yandex_artist,
            "yandex_title": r.yandex_title,
            "spotify_artist": r.spotify_artist or "-",
            "spotify_title": r.spotify_title or "-",
        }
        for r in rows
    ]
