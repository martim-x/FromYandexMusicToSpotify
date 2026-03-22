"""
services/playlist_service.py

Управление плейлистами и связями transfer.
Вспомогательная проверка exists/copied запускается при каждой команде.
"""

import os
import re
from uuid import UUID, uuid4

import requests
from dotenv import load_dotenv
from sqlalchemy import select
from sqlalchemy.orm import joinedload, make_transient

from db.base import SessionLocal
from db.models import Log, LogLevel, Playlist, Transfer, Version
from services.log_service import write_log

PROVIDER_IDS = {
    "yandex": UUID("00000000-0000-0000-0000-000000000001"),
    "spotify": UUID("00000000-0000-0000-0000-000000000002"),
}


load_dotenv()
# ── helpers ───────────────────────────────────────────────────────────


def _extract_yandex_kind(url: str) -> str | None:
    """
    Поддерживаемые форматы:
      music.yandex.ru/users/LOGIN/playlists/123   → "123"
      music.yandex.ru/playlists/lk.uuid           → "lk.uuid"
      music.yandex.ru/playlists/uuid              → "uuid"
    """
    m = re.search(r"/playlists/([^\s?&#/]+)", url)
    return m.group(1) if m else None


def _extract_yandex_uid_from_url(url: str) -> str | None:
    """Извлекает LOGIN из /users/LOGIN/playlists/ или None для новых URL."""
    m = re.search(r"/users/([^/]+)/playlists/", url)
    return m.group(1) if m else None


def _extract_spotify_id(url: str) -> str | None:
    """Извлекает ID плейлиста, отбрасывая ?si=... и другие параметры."""
    # Убираем query string перед парсингом
    clean = url.split("?")[0].split("#")[0]
    m = re.search(r"playlist/([A-Za-z0-9]+)", clean)
    return m.group(1) if m else None


def _yandex_api_url(url: str) -> str | None:
    """Строит правильный API URL для любого формата ссылки Яндекса."""
    kind = _extract_yandex_kind(url)
    user_login = _extract_yandex_uid_from_url(url)
    uid = os.getenv("YANDEX_UID", "")
    if not kind:
        return None
    owner = user_login or uid
    if not owner:
        return None
    return (
        f"https://music.yandex.ru/api/v2.1/handlers/playlist/{owner}/{kind}"
        f"?lang=ru&external-domain=music.yandex.ru"
    )


def _check_yandex_exists(url: str) -> bool:
    try:
        api_url = _yandex_api_url(url)
        if not api_url:
            return False
        resp = requests.get(
            api_url,
            headers={
                "Cookie": os.getenv("YANDEX_COOKIE", ""),
                "User-Agent": "Mozilla/5.0",
            },
            timeout=8,
        )
        return resp.status_code == 200
    except Exception:
        return False


def _check_spotify_exists(url: str) -> bool:
    try:

        load_dotenv(override=True)  # перечитываем .env — токен мог обновиться
        pid = _extract_spotify_id(url)
        token = os.getenv("SPOTIFY_ACCESS_TOKEN", "")
        if not token:
            return False
        resp = requests.get(
            f"https://api.spotify.com/v1/playlists/{pid}",
            headers={"Authorization": f"Bearer {token}"},
            timeout=8,
        )
        return resp.status_code == 200
    except Exception:
        return False


def _resolve_name(url: str, provider: str) -> str:
    """Пробует получить название плейлиста из API."""
    try:
        if provider == "yandex":
            kind = _extract_yandex_kind(url)
            # Лайкнутые треки — фиксированное имя
            if kind and (kind == "3" or kind.startswith("lk.")):
                return "Мне нравится"
            api_url = _yandex_api_url(url)
            if not api_url:
                return url
            cookie = os.getenv("YANDEX_COOKIE", "")
            resp = requests.get(
                api_url,
                headers={"Cookie": cookie, "User-Agent": "Mozilla/5.0"},
                timeout=8,
            )
            if not resp.text.strip():
                return url
            data = resp.json()
            title = (data.get("playlist") or data).get("title") or (
                data.get("playlist") or data
            ).get("name")
            return title or url
        else:
            from dotenv import load_dotenv

            load_dotenv(override=True)
            pid = _extract_spotify_id(url)
            token = os.getenv("SPOTIFY_ACCESS_TOKEN", "")
            if not token:
                return url
            resp = requests.get(
                f"https://api.spotify.com/v1/playlists/{pid}",
                headers={"Authorization": f"Bearer {token}"},
                timeout=8,
            )
            if resp.status_code != 200:
                return url
            return resp.json().get("name", url)
    except Exception:
        return url


# ── фоновая проверка exists ───────────────────────────────────────────


def sync_exists_flags() -> None:
    """
    Вспомогательная функция.
    Запускается при каждой команде — обновляет exists флаг для всех плейлистов.
    """
    with SessionLocal() as session:
        playlists = session.query(Playlist).all()
        updated = 0
        for p in playlists:
            provider_name = p.provider.name
            check = (
                _check_yandex_exists
                if provider_name == "yandex"
                else _check_spotify_exists
            )
            new_exists = check(p.url)
            if p.exists != new_exists:
                p.exists = new_exists
                updated += 1
        session.commit()
    if updated:
        write_log(f"sync_exists_flags: обновлено {updated} плейлистов")
        print(f"[playlist] exists флаг обновлён у {updated} плейлистов")


# ── CRUD ──────────────────────────────────────────────────────────────


def add_playlist(url: str, provider: str) -> Playlist:
    provider_id = PROVIDER_IDS.get(provider)
    if not provider_id:
        write_log(
            f"add_playlist: неизвестный провайдер '{provider}'",
            level=LogLevel.error,
        )
        raise ValueError(f"Неизвестный провайдер: {provider}")

    # Валидация URL
    if provider == "yandex":
        kind = _extract_yandex_kind(url)
        if not kind:
            write_log(
                f"add_playlist: неверный Яндекс URL='{url}'",
                level=LogLevel.error,
            )
            raise ValueError(
                "Неверный формат Яндекс URL. Ожидается: https://music.yandex.ru/users/LOGIN/playlists/3 или /playlists/uuid"
                f"  Получено:  {url}"
            )
        if not os.getenv("YANDEX_UID"):
            write_log(
                "add_playlist: YANDEX_UID не задан в .env",
                level=LogLevel.warn,
            )
            raise ValueError(
                "YANDEX_UID не задан в .env — запусти: pull yandex && push yandex"
            )
    else:
        if not _extract_spotify_id(url):
            write_log(
                f"add_playlist: неверный Spotify URL='{url}'",
                level=LogLevel.error,
            )
            raise ValueError(
                "Неверный формат Spotify URL. Ожидается: https://open.spotify.com/playlist/ID"
                f"  Получено:  {url}"
            )

    # Проверка дубля по URL
    with SessionLocal() as check_session:
        existing = check_session.execute(
            select(Playlist).where(Playlist.url == url)
        ).scalar_one_or_none()
        if existing:
            write_log(
                f"add_playlist: дубль — '{existing.name or url}' уже существует",
                level=LogLevel.warn,
            )
            raise ValueError(f"Плейлист уже добавлен: {existing.name or url}")

    name = _resolve_name(url, provider)
    exists = (
        _check_yandex_exists(url)
        if provider == "yandex"
        else _check_spotify_exists(url)
    )

    pl = Playlist(
        id=uuid4(),
        name=name,
        url=url,
        provider_id=provider_id,
        exists=exists,
    )
    with SessionLocal() as session:
        session.add(pl)
        session.commit()
        pl = session.execute(
            select(Playlist)
            .options(joinedload(Playlist.provider))
            .where(Playlist.id == pl.id)
        ).scalar_one()
        session.expunge(pl)

    write_log(
        f"add_playlist: добавлен '{name}' provider={provider} exists={exists}",
        level=LogLevel.info,
    )
    print(f"[playlist] добавлен: {name} ({provider}) exists={exists}")
    return pl


def link_playlists(from_id: str, to_id: str) -> Transfer:
    with SessionLocal() as session:
        from_pl = session.get(Playlist, UUID(from_id))
        to_pl = session.get(Playlist, UUID(to_id))

        if not from_pl:
            write_log(
                f"link_playlists: плейлист не найден id={from_id[:8]}",
                level=LogLevel.error,
            )
            raise ValueError(f"Плейлист не найден: {from_id}")
        if not to_pl:
            write_log(
                f"link_playlists: плейлист не найден id={to_id[:8]}",
                level=LogLevel.error,
            )
            raise ValueError(f"Плейлист не найден: {to_id}")

        existing = session.execute(
            select(Transfer).where(
                Transfer.from_id == UUID(from_id),
                Transfer.to_id == UUID(to_id),
                Transfer.status != "done",
            )
        ).scalar_one_or_none()
        if existing:
            write_log(
                f"link_playlists: дубль связи '{from_pl.name}' → '{to_pl.name}' "
                f"status={existing.status}",
                level=LogLevel.warn,
            )
            raise ValueError(
                f"Связь уже существует: {from_pl.name} → {to_pl.name} "
                f"(status={existing.status})"
            )

        link_version = Version(id=uuid4(), version=uuid4())
        session.add(link_version)
        session.flush()

        link = Transfer(
            id=uuid4(),
            from_id=UUID(from_id),
            to_id=UUID(to_id),
            status="pending",
            version_id=link_version.id,
        )
        session.add(link)
        session.commit()
        link = session.execute(
            select(Transfer)
            .options(
                joinedload(Transfer.from_playlist),
                joinedload(Transfer.to_playlist),
            )
            .where(Transfer.id == link.id)
        ).scalar_one()
        session.expunge(link)

    write_log(
        f"link_playlists: '{link.from_playlist.name}' → '{link.to_playlist.name}' "
        f"id={str(link.id)[:8]}",
        level=LogLevel.info,
        version_id=link.version_id,
    )
    print(f"[playlist] связано: {link.from_playlist.name} → {link.to_playlist.name}")
    return link


def list_playlists() -> list[dict]:
    with SessionLocal() as session:
        rows = session.query(Playlist).all()
        return [
            {
                "id": str(r.id)[:8] + "...",
                "full_id": str(r.id),
                "provider": r.provider.name,
                "name": r.name or "-",
                "exists": "yes" if r.exists else "no",
                "url": r.url[:50] + "..." if len(r.url) > 50 else r.url,
            }
            for r in rows
        ]


def list_links() -> list[dict]:
    with SessionLocal() as session:
        rows = session.query(Transfer).all()
        return [
            {
                "id": str(r.id)[:8] + "...",
                "full_id": str(r.id),
                "from": r.from_playlist.name or str(r.from_id)[:8],
                "to": r.to_playlist.name or str(r.to_id)[:8],
                "status": r.status,
                "total": r.total,
            }
            for r in rows
        ]


def get_pending_links() -> list[Transfer]:
    """Возвращает все pending связи для run."""
    with SessionLocal() as session:
        return session.query(Transfer).filter(Transfer.status == "pending").all()
