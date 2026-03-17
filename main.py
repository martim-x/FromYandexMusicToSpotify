"""
main.py - точка входа.

  -f  --fetch    [yandex|spotify|all]  получить сессионные данные
  -u  --update   [yandex|spotify|all]  записать буфер в БД + .env
  -fu / -uf                            fetch + update подряд
  -t  --transfer                       перенести треки из плейлиста
  -s  --stats    [transfer_id]         статистика переносов
  -h  --history  [N]                   история сессий
  -d  --debug    [yandex|spotify|all]  дебаг буфера и .env
"""

import argparse
import json
import os
import sqlite3
from pathlib import Path

from dotenv import load_dotenv
from tabulate import tabulate

load_dotenv()

from db.base import init_db
from services.fetch_service import FetchService
from services.transfer_service import get_stats, get_transfer_tracks, run_transfer
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
            if val:
                display = "xxx" if key in SENSITIVE else val
                status = "OK"
            else:
                display = "не задан"
                status = "MISSING"
            env_rows.append([key, status, display])
        print(
            tabulate(
                env_rows, headers=["key", "status", "value"], tablefmt="rounded_outline"
            )
        )

        print(f"\nauth_log")
        try:
            conn = sqlite3.connect("history.db")
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
                print("  записей нет")
        except Exception as e:
            print(f"  ошибка: {e}")


# ── transfer ──────────────────────────────────────────────────────────


def do_transfer(spotify_target: str) -> None:
    uid = os.getenv("YANDEX_UID")
    kind = os.getenv("YANDEX_PLAYLIST_KIND", "3")

    if not uid:
        print("YANDEX_UID не задан в .env")
        return
    if not spotify_target:
        spotify_target = input("Spotify playlist URL или ID: ").strip()

    log = run_transfer(uid, kind, spotify_target)

    # Итоговая таблица
    table = [
        ["всего", log.total],
        ["matched", log.matched],
        ["partial", log.partial],
        ["not_found", log.not_found],
    ]
    print()
    print(tabulate(table, headers=["статус", "треков"], tablefmt="rounded_outline"))
    print(f"\nid переноса: {log.id}")


# ── stats ─────────────────────────────────────────────────────────────


def do_stats(transfer_id: str | None) -> None:
    stats = get_stats(transfer_id)
    if not stats:
        print("Переносов не найдено.")
        return

    # Сводная таблица
    summary = [
        [
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
    ]
    print()
    print(
        tabulate(
            summary,
            headers=[
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

    # Детали по конкретному переносу
    if transfer_id:
        tracks = get_transfer_tracks(transfer_id)
        if tracks:
            print(f"\nтреки переноса {transfer_id[:8]}...")
            track_table = [
                [
                    t["status"],
                    t["yandex_artist"],
                    t["yandex_title"],
                    t["spotify_artist"],
                    t["spotify_title"],
                ]
                for t in tracks
            ]
            print(
                tabulate(
                    track_table,
                    headers=[
                        "status",
                        "yandex artist",
                        "yandex title",
                        "spotify artist",
                        "spotify title",
                    ],
                    tablefmt="rounded_outline",
                )
            )


# ── fetch / update ────────────────────────────────────────────────────


def do_fetch(provider: str) -> None:
    svc = FetchService()
    targets = PROVIDERS if provider == "all" else [provider]
    for p in targets:
        svc.run(p)


def do_update(provider: str) -> None:
    svc = UpdateService()
    targets = PROVIDERS if provider == "all" else [provider]
    for p in targets:
        svc.run(p)


# ── CLI ───────────────────────────────────────────────────────────────


def main() -> None:
    init_db()

    parser = argparse.ArgumentParser(
        description="Yandex Music -> Spotify", add_help=False
    )
    parser.add_argument(
        "--help", action="help", default=argparse.SUPPRESS, help="показать справку"
    )
    parser.add_argument(
        "-f",
        "--fetch",
        nargs="?",
        const="all",
        metavar="PROVIDER",
        help="получить сессионные данные",
    )
    parser.add_argument(
        "-u",
        "--update",
        nargs="?",
        const="all",
        metavar="PROVIDER",
        help="записать в бд и .env",
    )
    parser.add_argument(
        "-fu",
        "-uf",
        nargs="?",
        const="all",
        metavar="PROVIDER",
        help="fetch + update подряд",
        dest="fetch_update",
    )
    parser.add_argument(
        "-t",
        "--transfer",
        nargs="?",
        const="",
        metavar="SPOTIFY_ID",
        help="перенести треки (передай ID или URL плейлиста Spotify)",
    )
    parser.add_argument(
        "-s",
        "--stats",
        nargs="?",
        const="all",
        metavar="TRANSFER_ID",
        help="статистика переносов",
    )
    parser.add_argument(
        "-h",
        "--history",
        nargs="?",
        const=10,
        type=int,
        metavar="N",
        help="история сессий",
        dest="history",
    )
    parser.add_argument(
        "-d",
        "--debug",
        nargs="?",
        const="all",
        metavar="PROVIDER",
        help="дебаг буфера и .env",
    )

    args = parser.parse_args()

    if args.fetch_update is not None:
        do_fetch(args.fetch_update)
        do_update(args.fetch_update)
        return

    if args.fetch is not None:
        do_fetch(args.fetch)
    if args.update is not None:
        do_update(args.update)
    if args.transfer is not None:
        do_transfer(args.transfer)
    if args.stats is not None:
        do_stats(None if args.stats == "all" else args.stats)
    if args.history is not None:
        _print_history(UpdateService().history(args.history))
    if args.debug is not None:
        _print_debug(args.debug)

    ran = any(
        [
            args.fetch,
            args.update,
            args.fetch_update,
            args.transfer,
            args.history,
            args.debug,
            args.stats is not None,
        ]
    )
    if not ran:
        parser.print_help()


if __name__ == "__main__":
    main()
