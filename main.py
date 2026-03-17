"""
main.py — точка входа.

  pull  [yandex|spotify|all]      браузер → credentials/*.json
  push  [yandex|spotify|all]      json → .env + DB

  creds <provider> [--all]        последние креды / полная история
  playlists                       все плейлисты
  playlists add <url> <provider>  добавить плейлист

  link                            интерактив: Spotify (to) → Yandex (from)
  link --show                     таблица всех связей

  run                             перенести все pending связи
  run --version <id>              повторить конкретную версию
  run --link <id>                 повторить конкретную связь

  stats                           статистика всех переносов
  stats --version <id>            детали конкретного переноса

  debug [yandex|spotify|all]      буфер + .env + auth_log

  help                            эта инструкция
"""

import json
import os
import sqlite3
import sys
import traceback
from pathlib import Path
from uuid import UUID

from dotenv import load_dotenv
from tabulate import tabulate

load_dotenv()

from core.exceptions import (
    BufferEmptyError,
    PullerError,
    PushError,
    TransferError,
    UnknownProviderError,
)
from db.base import init_db
from services.playlist_service import (
    add_playlist,
    link_playlists,
    list_links,
    list_playlists,
    sync_exists_flags,
)
from services.pull_service import PullService
from services.push_service import PushService
from services.transfer_service import get_stats, run_all

PROVIDERS = ["yandex", "spotify"]
SENSITIVE = {
    "SPOTIFY_CLIENT_ID",
    "SPOTIFY_CLIENT_SECRET",
    "YANDEX_COOKIE",
    "SPOTIFY_ACCESS_TOKEN",
    "SPOTIFY_REFRESH_TOKEN",
}
ENV_FIELDS = {
    "yandex": ["YANDEX_COOKIE", "YANDEX_UID", "YANDEX_PLAYLIST_KIND"],
    "spotify": [
        "SPOTIFY_CLIENT_ID",
        "SPOTIFY_CLIENT_SECRET",
        "SPOTIFY_ACCESS_TOKEN",
        "SPOTIFY_REFRESH_TOKEN",
    ],
}
DB_PATH = Path(__file__).resolve().parent / "history.db"


# ── error helpers ─────────────────────────────────────────────────────


def _err(msg: str) -> None:
    """Красивый вывод ошибки."""
    print(f"\n[!] {msg}\n")


def _warn(msg: str) -> None:
    print(f"[~] {msg}")


# ── background sync ───────────────────────────────────────────────────


def _bg_sync() -> None:
    """Тихая фоновая проверка exists флагов — только если есть плейлисты."""
    try:
        conn = sqlite3.connect(str(DB_PATH))
        count = conn.execute("SELECT COUNT(*) FROM playlist").fetchone()[0]
        conn.close()
        if count > 0:
            sync_exists_flags()
    except Exception:
        pass


# ── help ─────────────────────────────────────────────────────────────


def cmd_help() -> None:
    print(__doc__)


# ── pull ─────────────────────────────────────────────────────────────


def cmd_pull(args: list[str]) -> None:
    provider = args[0] if args else "all"
    if provider not in PROVIDERS + ["all"]:
        _err(f"неизвестный провайдер: {provider}\nДоступные: yandex, spotify, all")
        return

    svc = PullService()
    targets = PROVIDERS if provider == "all" else [provider]

    for p in targets:
        try:
            svc.run(p)
        except PullerError as e:
            _err(f"pull {p} не удался:\n  {e}")
        except Exception as e:
            _err(f"неожиданная ошибка при pull {p}:\n  {e}")


# ── push ─────────────────────────────────────────────────────────────


def cmd_push(args: list[str]) -> None:
    provider = args[0] if args else "all"
    if provider not in PROVIDERS + ["all"]:
        _err(f"неизвестный провайдер: {provider}\nДоступные: yandex, spotify, all")
        return

    svc = PushService()
    targets = PROVIDERS if provider == "all" else [provider]

    for p in targets:
        try:
            svc.run(p)
        except BufferEmptyError:
            _err(f"буфер для {p} не найден.\n" f"  Сначала запусти: pull {p}")
        except PushError as e:
            _err(str(e))
        except UnknownProviderError as e:
            _err(str(e))
        except Exception as e:
            _err(f"неожиданная ошибка при push {p}:\n  {e}")


# ── creds ─────────────────────────────────────────────────────────────


def cmd_creds(args: list[str]) -> None:
    # creds           → все провайдеры, последние активные
    # creds --all     → все провайдеры, полная история
    # creds yandex    → yandex, последние активные
    # creds yandex --all → yandex, полная история
    show_all = "--all" in args
    remaining = [a for a in args if a != "--all"]
    provider = remaining[0] if remaining else "all"

    if provider not in PROVIDERS + ["all"]:
        _err(f"неизвестный провайдер: {provider}\nДоступные: yandex, spotify, all")
        return

    targets = PROVIDERS if provider == "all" else [provider]
    for prov in targets:
        _cmd_creds_one(prov, show_all)


def _cmd_creds_one(provider: str, show_all: bool) -> None:

    try:
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row

        if show_all:
            rows = conn.execute(
                """
                SELECT substr(cast(v.id as text),1,8)||'...' as short_id,
                       p.name as provider,
                       v.timestamp, v.expired,
                       substr(cast(v.version as text),1,8)||'...' as ver
                FROM versions v
                JOIN credentials c ON c.version_id = v.id
                JOIN providers p   ON p.id = c.provider_id
                WHERE p.name = ?
                ORDER BY v.timestamp DESC
            """,
                (provider,),
            ).fetchall()
            conn.close()

            if not rows:
                _warn(f"история кредов пуста для {provider}")
                return

            print(f"\nистория кредов — {provider}")
            print(
                tabulate(
                    [
                        [
                            r["short_id"],
                            r["provider"],
                            str(r["timestamp"])[:19],
                            "yes" if r["expired"] else "no",
                            r["ver"],
                        ]
                        for r in rows
                    ],
                    headers=["id", "provider", "timestamp", "expired", "version"],
                    tablefmt="rounded_outline",
                )
            )

        else:
            row = conn.execute(
                """
                SELECT substr(cast(v.id as text),1,8)||'...' as short_id,
                       v.timestamp, c.data
                FROM versions v
                JOIN credentials c ON c.version_id = v.id
                JOIN providers p   ON p.id = c.provider_id
                WHERE p.name = ? AND v.expired = 0
                ORDER BY v.timestamp DESC LIMIT 1
            """,
                (provider,),
            ).fetchone()
            conn.close()

            if not row:
                _warn(f"нет активных кредов для {provider}\n  Запусти: pull {provider}")
                return

            data = json.loads(row["data"])
            kv = []
            for k, v in data.items():
                s = str(v)
                if k in ("cookie", "access_token", "refresh_token") and len(s) > 10:
                    display = s[:6] + "***" + s[-4:]
                else:
                    display = s
                kv.append([k, display])

            print(f"\nактивные креды — {provider}")
            print(
                tabulate(
                    [[row["short_id"], provider, str(row["timestamp"])[:19]]],
                    headers=["id", "provider", "timestamp"],
                    tablefmt="rounded_outline",
                )
            )
            print(tabulate(kv, headers=["field", "value"], tablefmt="rounded_outline"))

    except Exception as e:
        _err(f"ошибка чтения кредов: {e}")


# ── playlists ─────────────────────────────────────────────────────────


def cmd_playlists(args: list[str]) -> None:
    if args and args[0] == "add":
        if len(args) < 3:
            _err("Использование: playlists add <url> <yandex|spotify>")
            return
        try:
            pl = add_playlist(args[1], args[2])
            print(
                tabulate(
                    [
                        [
                            str(pl.id),
                            pl.provider.name,
                            pl.name or "-",
                            "yes" if pl.exists else "no",
                            pl.url,
                        ]
                    ],
                    headers=["id", "provider", "name", "exists", "url"],
                    tablefmt="rounded_outline",
                )
            )
        except ValueError as e:
            _err(str(e))
        except Exception as e:
            _err(f"не удалось добавить плейлист: {e}")
        return

    pls = list_playlists()
    links = list_links()

    if pls:
        print("\nплейлисты:")
        print(
            tabulate(
                [
                    [
                        p["id"],
                        p["provider"],
                        p["name"],
                        p["exists"],
                        p["copied"],
                        p["url"],
                    ]
                    for p in pls
                ],
                headers=["id", "provider", "name", "exists", "copied", "url"],
                tablefmt="rounded_outline",
            )
        )
    else:
        _warn("плейлистов нет. Добавь: playlists add <url> <provider>")

    if links:
        print("\nсвязи:")
        print(
            tabulate(
                [[l["id"], l["from"], l["to"], l["status"], l["total"]] for l in links],
                headers=["id", "from", "to", "status", "total"],
                tablefmt="rounded_outline",
            )
        )


# ── link ─────────────────────────────────────────────────────────────


def cmd_link(args: list[str]) -> None:
    if "--show" in args:
        links = list_links()
        if not links:
            _warn("связей нет. Создай: link")
            return
        print(
            tabulate(
                [
                    [i + 1, l["id"], l["from"], l["to"], l["status"], l["total"]]
                    for i, l in enumerate(links)
                ],
                headers=["#", "id", "from", "to", "status", "total"],
                tablefmt="rounded_outline",
            )
        )
        return

    all_pls = list_playlists()
    spotify = [p for p in all_pls if p["provider"] == "spotify"]
    yandex = [p for p in all_pls if p["provider"] == "yandex"]

    if not spotify:
        _err("нет Spotify плейлистов.\n  Добавь: playlists add <url> spotify")
        return
    if not yandex:
        _err("нет Yandex плейлистов.\n  Добавь: playlists add <url> yandex")
        return

    # Шаг 1: Spotify (to)
    print("\nШаг 1 — выбери Spotify плейлист (to):\n")
    print(
        tabulate(
            [[i + 1, p["name"], p["url"]] for i, p in enumerate(spotify)],
            headers=["#", "name", "url"],
            tablefmt="rounded_outline",
        )
    )
    while True:
        try:
            idx = int(input("\nНомер Spotify плейлиста: ")) - 1
            if 0 <= idx < len(spotify):
                to_pl = spotify[idx]
                break
            _warn(f"введи число от 1 до {len(spotify)}")
        except ValueError:
            _warn("только цифра")

    # Шаг 2: Yandex (from) — несколько
    print(f"\nШаг 2 — выбери Yandex плейлисты → {to_pl['name']}:\n")
    print(
        tabulate(
            [[i + 1, p["name"], p["url"]] for i, p in enumerate(yandex)],
            headers=["#", "name", "url"],
            tablefmt="rounded_outline",
        )
    )
    while True:
        raw = input("\nНомера через пробел, запятую или точку: ")
        parts = raw.replace(",", " ").replace(".", " ").split()
        try:
            indices = [int(x) - 1 for x in parts]
            if indices and all(0 <= i < len(yandex) for i in indices):
                from_pls = [yandex[i] for i in indices]
                break
            _warn(f"числа от 1 до {len(yandex)}")
        except ValueError:
            _warn("только цифры")

    created = []
    for from_pl in from_pls:
        try:
            lnk = link_playlists(from_pl["full_id"], to_pl["full_id"])
            created.append([from_pl["name"], to_pl["name"], str(lnk.id)[:8] + "..."])
        except Exception as e:
            _err(f"не удалось создать связь {from_pl['name']} → {to_pl['name']}: {e}")

    if created:
        print("\nсозданные связи:")
        print(
            tabulate(created, headers=["from", "to", "id"], tablefmt="rounded_outline")
        )


# ── run ───────────────────────────────────────────────────────────────


def cmd_run(args: list[str]) -> None:
    if "--version" in args:
        idx = args.index("--version") + 1
        if idx >= len(args):
            _err("Укажи id версии: run --version <id>")
            return
        _run_by_version(args[idx])
        return

    if "--link" in args:
        idx = args.index("--link") + 1
        if idx >= len(args):
            _err("Укажи id связи: run --link <id>")
            return
        _run_by_link(args[idx])
        return

    try:
        results = run_all()
    except Exception as e:
        _err(f"ошибка при переносе: {e}")
        traceback.print_exc()
        return

    if results:
        print()
        print(
            tabulate(
                [
                    [
                        r["from"],
                        r["to"],
                        r["status"],
                        r["total"],
                        r["matched"],
                        r["partial"],
                        r["not_found"],
                    ]
                    for r in results
                ],
                headers=[
                    "from",
                    "to",
                    "status",
                    "total",
                    "matched",
                    "partial",
                    "not_found",
                ],
                tablefmt="rounded_outline",
            )
        )


def _run_by_version(version_id: str) -> None:
    from db.base import SessionLocal
    from db.playlist_models import Transfer

    with SessionLocal() as session:
        links = session.query(Transfer).filter(Transfer.version_id == version_id).all()
        if not links:
            _err(f"связей с version_id {version_id[:8]}... не найдено")
            return
        for lnk in links:
            lnk.status = "pending"
            lnk.from_playlist.copied = False
        session.commit()

    _warn(f"{len(links)} связей сброшено в pending, запускаем...")
    cmd_run([])


def _run_by_link(link_id: str) -> None:
    from db.base import SessionLocal
    from db.playlist_models import Transfer

    try:
        uid = UUID(link_id)
    except ValueError:
        _err(f"невалидный UUID: {link_id}")
        return

    with SessionLocal() as session:
        lnk = session.get(Transfer, uid)
        if not lnk:
            _err(f"связь {link_id[:8]}... не найдена")
            return
        lnk.status = "pending"
        lnk.from_playlist.copied = False
        session.commit()

    _warn(f"связь {link_id[:8]}... сброшена в pending, запускаем...")
    cmd_run([])


# ── stats ─────────────────────────────────────────────────────────────


def cmd_stats(args: list[str]) -> None:
    version_id = None
    if "--version" in args:
        idx = args.index("--version") + 1
        version_id = args[idx] if idx < len(args) else None

    stats = get_stats(version_id)
    if not stats:
        _warn("переносов не найдено")
        return

    print()
    print(
        tabulate(
            [
                [
                    s["id"],
                    s["date"],
                    s["status"],
                    s["from"],
                    s["to"],
                    s["total"],
                    s["matched"],
                    s["partial"],
                    s["not_found"],
                ]
                for s in stats
            ],
            headers=[
                "id",
                "date",
                "status",
                "from",
                "to",
                "total",
                "matched",
                "partial",
                "not_found",
            ],
            tablefmt="rounded_outline",
        )
    )


# ── debug ─────────────────────────────────────────────────────────────


def cmd_debug(args: list[str]) -> None:
    provider = args[0] if args else "all"
    targets = PROVIDERS if provider == "all" else [provider]

    for p in targets:
        print(f"\n── {p.upper()} ──")

        # buffer
        buf = Path(__file__).resolve().parent / "credentials" / f"{p}.json"
        print(f"\nbuffer → credentials/{p}.json")
        if buf.exists():
            rows = []
            for k, v in json.loads(buf.read_text()).items():
                s = str(v)
                if k in ("cookie", "access_token", "refresh_token") and len(s) > 10:
                    display = s[:6] + "***" + s[-4:]
                else:
                    display = s
                rows.append([k, display])
            print(
                tabulate(rows, headers=["field", "value"], tablefmt="rounded_outline")
            )
        else:
            _warn(f"буфер не найден — запусти: pull {p}")

        # .env
        print("\n.env")
        env_rows = []
        for key in ENV_FIELDS.get(p, []):
            val = os.getenv(key, "")
            env_rows.append(
                [
                    key,
                    "OK" if val else "MISSING",
                    "xxx" if val and key in SENSITIVE else (val or "не задан"),
                ]
            )
        print(
            tabulate(
                env_rows, headers=["key", "status", "value"], tablefmt="rounded_outline"
            )
        )

        # auth_log
        print("\nauth_log")
        try:
            conn = sqlite3.connect(str(DB_PATH))
            db_rows = conn.execute(
                "SELECT timestamp, method, note FROM auth_log "
                "WHERE provider=? ORDER BY timestamp DESC LIMIT 5",
                (p,),
            ).fetchall()
            conn.close()
            if db_rows:
                print(
                    tabulate(
                        db_rows,
                        headers=["timestamp", "method", "note"],
                        tablefmt="rounded_outline",
                    )
                )
            else:
                _warn("записей нет")
        except Exception as e:
            _err(f"ошибка чтения auth_log: {e}")


# ── router ────────────────────────────────────────────────────────────

COMMANDS = {
    "pull": cmd_pull,
    "push": cmd_push,
    "creds": cmd_creds,
    "playlists": cmd_playlists,
    "link": cmd_link,
    "run": cmd_run,
    "stats": cmd_stats,
    "debug": cmd_debug,
    "help": lambda _: cmd_help(),
}


def main() -> None:
    try:
        init_db()
    except Exception as e:
        print(f"[!] не удалось инициализировать БД: {e}")
        sys.exit(1)

    _bg_sync()

    if len(sys.argv) < 2:
        cmd_help()
        return

    cmd = sys.argv[1].lower()
    args = sys.argv[2:]

    handler = COMMANDS.get(cmd)
    if handler:
        handler(args)
    else:
        _err(f"неизвестная команда: '{cmd}'")
        print("Доступные команды:")
        print("  " + "  ".join(COMMANDS.keys()))


if __name__ == "__main__":
    main()
