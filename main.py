"""
main.py - точка входа.

  -f  --fetch   [yandex|spotify|all]   получить сессионные данные
  -u  --update  [yandex|spotify|all]   записать буфер в БД + .env
  -fu / -uf                            fetch + update подряд
  -h  --history [N]                    история версий
  -d  --debug   [yandex|spotify|all]   показать текущие сессионные данные в .env
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
from services.update_service import UpdateService

PROVIDERS = ["yandex", "spotify"]

ENV_FIELDS = {
    "yandex": ["YANDEX_COOKIE"],
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


def _print_debug(provider: str) -> None:
    targets = PROVIDERS if provider == "all" else [provider]

    for p in targets:
        print(f"\n── {p.upper()} ──")

        # 1. Буферный файл
        buf = Path(f"credentials/{p}.json")
        print(f"\nbuffer → {buf}")
        if buf.exists():
            data = json.loads(buf.read_text())
            rows = []
            for k, v in data.items():
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

        # 2. .env переменные
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

        # 3. auth_log
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
            print(f"  ошибка чтения: {e}")


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
        dest="fetch_update",
        help="fetch + update подряд",
    )
    parser.add_argument(
        "-h",
        "--history",
        nargs="?",
        const=10,
        type=int,
        metavar="N",
        dest="history",
        help="история версий",
    )
    parser.add_argument(
        "-d",
        "--debug",
        nargs="?",
        const="all",
        metavar="PROVIDER",
        help="показать данные в .env и буфере",
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
    if args.history is not None:
        _print_history(UpdateService().history(args.history))
    if args.debug is not None:
        _print_debug(args.debug)

    if not any([args.fetch, args.update, args.fetch_update, args.history, args.debug]):
        parser.print_help()


if __name__ == "__main__":
    main()
