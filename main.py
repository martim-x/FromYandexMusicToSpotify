"""
main.py - точка входа.

Сессионные данные:
  -f  --pull    [yandex|spotify|all]  получить сессионные данные
  -u  --push    [yandex|spotify|all]  записать буфер в БД + .env
  -fu / -uf                           pull + push подряд

Плейлисты:
  playlist add   <url> <provider>     добавить плейлист (yandex|spotify)
  playlist link  <from_id> <to_id>    связать пару from→to
  playlist list                       показать все плейлисты и связи

Перенос:
  run                                 запустить все pending пары
  -s  --stats                         статистика переносов

Утилиты:
  -h  --history  [N]                  история сессий
  -d  --debug    [yandex|spotify]     дебаг буфера и .env
"""

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

from dotenv import load_dotenv
from tabulate import tabulate

load_dotenv()

from db.base import init_db
from services.fetch_service import FetchService
from services.playlist_service import (
    add_playlist,
    link_playlists,
    list_links,
    list_playlists,
    sync_exists_flags,
)
from services.transfer_service import get_stats, run_all
from services.update_service import UpdateService

PROVIDERS = ["yandex", "spotify"]
ENV_FIELDS = {
    "yandex": ["YANDEX_COOKIE", "YANDEX_UID", "YANDEX_PLAYLIST_KIND"],
    "spotify": [
        "SPOTIFY_CLIENT_ID",
        "SPOTIFY_CLIENT_SECRET",
        "SPOTIFY_ACCESS_TOKEN",
        "SPOTIFY_REFRESH_TOKEN",
    ],
}
SENSITIVE = {
    "SPOTIFY_CLIENT_ID",
    "SPOTIFY_CLIENT_SECRET",
    "YANDEX_COOKIE",
    "SPOTIFY_ACCESS_TOKEN",
    "SPOTIFY_REFRESH_TOKEN",
}


# ── фоновая проверка ──────────────────────────────────────────────────


def _background_sync():
    """Запускается при каждой команде тихо."""
    try:
        sync_exists_flags()
    except Exception:
        pass


# ── history ───────────────────────────────────────────────────────────


def _print_history(rows) -> None:
    if not rows:
        print("История пуста.")
        return
    table = [
        [
            r.provider,
            str(r.timestamp)[:19],
            "yes" if r.expired else "no",
            str(r.version_id),
        ]
        for r in rows
    ]
    print()
    print(
        tabulate(
            table,
            headers=["provider", "timestamp", "expired", "version_id"],
            tablefmt="rounded_outline",
        )
    )


# ── debug ─────────────────────────────────────────────────────────────


def _print_debug(provider: str) -> None:
    targets = PROVIDERS if provider == "all" else [provider]
    for p in targets:
        print(f"\n── {p.upper()} ──")
        buf = Path(f"credentials/{p}.json")
        print(f"\nbuffer → {buf}")
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
            print("  файл не найден — запусти -f сначала")

        print(f"\n.env")
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

        print(f"\nauth_log")
        try:
            conn = sqlite3.connect("history.db")
            db_rows = conn.execute(
                "SELECT timestamp, method, note FROM auth_log WHERE provider=? ORDER BY timestamp DESC LIMIT 5",
                (p,),
            ).fetchall()
            conn.close()
            print(
                tabulate(
                    db_rows,
                    headers=["timestamp", "method", "note"],
                    tablefmt="rounded_outline",
                )
                if db_rows
                else "  записей нет"
            )
        except Exception as e:
            print(f"  ошибка: {e}")


# ── playlist ──────────────────────────────────────────────────────────


def do_playlist(sub: str, args_rest: list[str]) -> None:
    if sub == "add":
        if len(args_rest) < 2:
            print("Использование: playlist add <url> <yandex|spotify>")
            return
        pl = add_playlist(args_rest[0], args_rest[1])
        print(
            tabulate(
                [[str(pl.id), pl.provider.name, pl.name, pl.url, pl.exists, pl.copied]],
                headers=["id", "provider", "name", "url", "exists", "copied"],
                tablefmt="rounded_outline",
            )
        )

    elif sub == "link":
        if len(args_rest) < 2:
            print("Использование: playlist link <from_id> <to_id>")
            return
        link = link_playlists(args_rest[0], args_rest[1])
        print(f"Связь создана: {link.from_id} → {link.to_id}")

    elif sub == "list":
        playlists = list_playlists()
        links = list_links()
        if playlists:
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
                        for p in playlists
                    ],
                    headers=["id", "provider", "name", "exists", "copied", "url"],
                    tablefmt="rounded_outline",
                )
            )
        if links:
            print("\nсвязи:")
            print(
                tabulate(
                    [
                        [l["id"], l["from"], l["to"], l["status"], l["total"]]
                        for l in links
                    ],
                    headers=["id", "from", "to", "status", "total"],
                    tablefmt="rounded_outline",
                )
            )
    else:
        print("Команды: playlist add | playlist link | playlist list")


# ── run ───────────────────────────────────────────────────────────────


def do_run() -> None:
    results = run_all()
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


# ── stats ─────────────────────────────────────────────────────────────


def do_stats() -> None:
    stats = get_stats()
    if not stats:
        print("Переносов не найдено.")
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


# ── pull / push ───────────────────────────────────────────────────────


def do_pull(provider: str) -> None:
    svc = FetchService()
    targets = PROVIDERS if provider == "all" else [provider]
    for p in targets:
        svc.run(p)


def do_push(provider: str) -> None:
    svc = UpdateService()
    targets = PROVIDERS if provider == "all" else [provider]
    for p in targets:
        svc.run(p)


# ── CLI ───────────────────────────────────────────────────────────────


def main() -> None:
    init_db()
    _background_sync()

    # Перехватываем субкоманду playlist / run
    if len(sys.argv) > 1 and sys.argv[1] == "playlist":
        sub = sys.argv[2] if len(sys.argv) > 2 else "list"
        rest = sys.argv[3:]
        do_playlist(sub, rest)
        return

    if len(sys.argv) > 1 and sys.argv[1] == "run":
        do_run()
        return

    parser = argparse.ArgumentParser(
        description="Yandex Music -> Spotify", add_help=False
    )
    parser.add_argument("--help", action="help", default=argparse.SUPPRESS)
    parser.add_argument("-f", "--pull", nargs="?", const="all", metavar="PROVIDER")
    parser.add_argument("-u", "--push", nargs="?", const="all", metavar="PROVIDER")
    parser.add_argument(
        "-fu", "-uf", nargs="?", const="all", metavar="PROVIDER", dest="pull_push"
    )
    parser.add_argument("-s", "--stats", action="store_true")
    parser.add_argument(
        "-h", "--history", nargs="?", const=10, type=int, metavar="N", dest="history"
    )
    parser.add_argument("-d", "--debug", nargs="?", const="all", metavar="PROVIDER")

    args = parser.parse_args()

    if args.pull_push is not None:
        do_pull(args.pull_push)
        do_push(args.pull_push)
        return

    if args.pull is not None:
        do_pull(args.pull)
    if args.push is not None:
        do_push(args.push)
    if args.stats:
        do_stats()
    if args.history is not None:
        _print_history(UpdateService().history(args.history))
    if args.debug is not None:
        _print_debug(args.debug)

    if not any(
        [args.pull, args.push, args.pull_push, args.stats, args.history, args.debug]
    ):
        parser.print_help()


if __name__ == "__main__":
    main()
