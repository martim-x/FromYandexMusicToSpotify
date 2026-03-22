"""
services/transfer_service.py

- Загружает треки из Яндекса, пишет в таблицу tracks (status=pending).
- Ищет треки в Spotify параллельно (ThreadPoolExecutor).
- Watchdog-поток: если прогресс не меняется 10 сек — прерывает поиск.
- Всё что найдено — сохраняет в БД и добавляет в плейлист Spotify.
- Добавленные треки записывает в verified_tracks.
"""

import os
import re
import threading
import time as _time
from concurrent.futures import ThreadPoolExecutor, as_completed
from uuid import UUID, uuid4

from dotenv import load_dotenv

from core.spinner import Spinner
from db.base import SessionLocal
from db.models import LogLevel, Track, TrackStatus, Transfer, VerifiedTrack
from i18n import t
from services.log_service import write_log
from services.spotify_api import (
    add_tracks_to_playlist,
    extract_playlist_id,
    search_track,
)
from services.yandex_api import get_tracks

MAX_WORKERS = 4
WATCHDOG_TIMEOUT = 10.0

load_dotenv()


def _kind_from_url(url: str) -> str:
    m = re.search(r"/playlists/([^\s?/]+)", url)
    return m.group(1) if m else url.strip()


# ── Watchdog ──────────────────────────────────────────────────────────────


class _Watchdog:
    """Прерывает поиск если прогресс не двигался WATCHDOG_TIMEOUT секунд."""

    def __init__(self, timeout: float) -> None:
        self.timeout = timeout
        self._last_tick = _time.monotonic()
        self._stop = threading.Event()
        self.triggered = False
        self._thread = threading.Thread(target=self._run, daemon=True)

    def tick(self) -> None:
        self._last_tick = _time.monotonic()

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=1)

    def _run(self) -> None:
        while not self._stop.is_set():
            if _time.monotonic() - self._last_tick > self.timeout:
                self.triggered = True
                self._stop.set()
                print(f"\n{t('watchdog.triggered', timeout=int(self.timeout))}")
                return
            self._stop.wait(1.0)


# ── Вспомогательные функции БД ────────────────────────────────────────────


def _save_tracks(session, transfer_id, raw_tracks: list[dict]) -> list[Track]:
    """Записывает треки из Яндекса в таблицу tracks со статусом pending."""
    rows = []
    for item in raw_tracks:
        row = Track(
            id=uuid4(),
            transfer_id=transfer_id,
            status=TrackStatus.pending,
            yandex_id=item.get("yandex_id"),
            yandex_title=item["title"],
            yandex_artist=item["artist"],
            yandex_album=item.get("album"),
            yandex_year=item.get("year"),
            yandex_duration_ms=item.get("duration_ms"),
        )
        session.add(row)
        rows.append(row)
    session.flush()
    return rows


def _update_track(session, track: Track, result: dict | None) -> None:
    """Проставляет результат поиска на трек."""
    if result is None:
        track.status = TrackStatus.not_found
    elif result["status"] in ("matched", "partial"):
        track.status = (
            TrackStatus.matched
            if result["status"] == "matched"
            else TrackStatus.partial
        )
        track.spotify_id = result["id"]
        track.spotify_title = result["title"]
        track.spotify_artist = result["artist"]
    else:
        track.status = TrackStatus.not_found


def _save_verified(session, transfer_id, track: Track) -> None:
    """Записывает трек в verified_tracks после добавления в Spotify."""
    session.add(VerifiedTrack(id=uuid4(), track_id=track.id, transfer_id=transfer_id))


# ── Основной запуск ───────────────────────────────────────────────────────


def _run_one(link: Transfer, session) -> None:
    uid = os.getenv("YANDEX_UID", "")
    kind = _kind_from_url(link.from_playlist.url)
    spotify_id = extract_playlist_id(link.to_playlist.url)

    print(
        f"\n{t('transfer_service.start', **{'from': link.from_playlist.name, 'to': link.to_playlist.name})}"
    )

    # 1. Загружаем треки из Яндекса
    raw_tracks = get_tracks(uid, kind)
    link.total = len(raw_tracks)
    link.status = "running"
    session.commit()
    write_log(
        f"transfer start: '{link.from_playlist.name}' → '{link.to_playlist.name}' "
        f"total={link.total}",
        version_id=link.version_id,
    )

    # 2. Записываем треки в БД (status=pending)
    track_rows = _save_tracks(session, link.id, raw_tracks)
    session.commit()
    print(t("transfer_service.saved_tracks", count=len(track_rows)))

    # 3. Поиск в Spotify с watchdog
    done_count = 0
    results: dict[UUID, dict | None] = {}
    _stop_event = threading.Event()

    def _do_search(track: Track):
        if _stop_event.is_set():
            return track, None
        return track, search_track(track.yandex_title, track.yandex_artist)

    watchdog = _Watchdog(WATCHDOG_TIMEOUT)
    watchdog.start()

    ex = ThreadPoolExecutor(max_workers=MAX_WORKERS)
    try:
        with Spinner("поиск в Spotify", total=len(track_rows)) as sp:
            futures = {ex.submit(_do_search, tr): tr for tr in track_rows}

            try:
                for fut in as_completed(futures):
                    if watchdog.triggered:
                        _stop_event.set()
                        ex.shutdown(wait=False, cancel_futures=True)
                        break

                    try:
                        track, result = fut.result(timeout=30)
                        results[track.id] = result
                    except Exception as e:
                        track = futures[fut]
                        results[track.id] = None
                        print(f"\n[run] search error '{track.yandex_title}': {e}")
                        write_log(
                            f"search error: '{track.yandex_title}' — '{track.yandex_artist}' | {e}",
                            level=LogLevel.error,
                            version_id=link.version_id,
                        )

                    done_count += 1
                    watchdog.tick()
                    sp.update(done_count)

            except KeyboardInterrupt:
                print(f"\n{t('transfer_service.interrupted')}")
                _stop_event.set()
                ex.shutdown(wait=False, cancel_futures=True)
                write_log(
                    f"transfer interrupted: '{link.from_playlist.name}' — user interrupted",
                    level=LogLevel.warn,
                    version_id=link.version_id,
                )
                raise

    finally:
        _stop_event.set()
        ex.shutdown(wait=False, cancel_futures=True)
        watchdog.stop()

    if watchdog.triggered:
        link.status = "partial_done"
        write_log(
            f"watchdog triggered: '{link.from_playlist.name}' → '{link.to_playlist.name}' "
            f"processed {done_count}/{len(track_rows)} tracks",
            level=LogLevel.warn,
            version_id=link.version_id,
        )

    # 4. Сохраняем результаты поиска в БД
    matched = partial = not_found = 0
    spotify_ids: list[str] = []

    for track in track_rows:
        result = results.get(track.id)
        _update_track(session, track, result)

        if track.status == TrackStatus.matched:
            matched += 1
            spotify_ids.append(track.spotify_id)
            print(f"  [+] {track.yandex_artist} — {track.yandex_title}")
        elif track.status == TrackStatus.partial:
            partial += 1
            spotify_ids.append(track.spotify_id)
            print(
                f"  [~] {track.yandex_artist} — {track.yandex_title} → {track.spotify_artist} — {track.spotify_title}"
            )
        else:
            not_found += 1
            print(f"  [-] {track.yandex_artist} — {track.yandex_title}")

    session.commit()

    # 5. Добавляем найденные треки в плейлист Spotify
    if spotify_ids:
        print(t("transfer_service.adding_spotify", count=len(spotify_ids)))
        write_log(
            f"spotify add tracks: {len(spotify_ids)} tracks → playlist {spotify_id[:8]}",
            version_id=link.version_id,
        )
        add_tracks_to_playlist(spotify_id, spotify_ids)

        # 6. Помечаем как verified
        for track in track_rows:
            if track.spotify_id and track.spotify_id in spotify_ids:
                _save_verified(session, link.id, track)
        session.commit()

    link.matched = matched
    link.partial = partial
    link.not_found = not_found

    if not watchdog.triggered:
        link.status = "done"
        link.from_playlist.copied = True
        write_log(
            f"playlist copied: '{link.from_playlist.name}' marked as copied",
            level=LogLevel.info,
            version_id=link.version_id,
        )

    session.commit()
    write_log(
        f"transfer done: '{link.from_playlist.name}' → '{link.to_playlist.name}' "
        f"matched={link.matched} partial={link.partial} not_found={link.not_found} "
        f"status={link.status}",
        level=LogLevel.info if link.status == "done" else LogLevel.warn,
        version_id=link.version_id,
    )
    print(
        t(
            "transfer_service.result",
            matched=matched,
            partial=partial,
            not_found=not_found,
        )
    )


def run_all() -> list[dict]:
    results = []
    with SessionLocal() as session:
        links = session.query(Transfer).filter(Transfer.status == "pending").all()
        if not links:
            print(t("transfer_service.no_pending"))
            return []
        print(t("transfer_service.found_pairs", count=len(links)))
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
                print(t("transfer_service.error", error=e))
                write_log(
                    f"transfer error: '{link.from_playlist.name}' → '{link.to_playlist.name}' | {e}",
                    level=LogLevel.error,
                    version_id=link.version_id,
                )
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

        write_log(
            f"get_stats: {'transfer=' + str(transfer_id)[:8] if transfer_id else 'all'} "
            f"rows={len(rows)}",
            level=LogLevel.info,
        )

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
