"""
main.py — точка входа.

  -f  --fetch   [yandex|spotify|all]   получить сессионные данные
  -u  --update  [yandex|spotify|all]   записать буфер в БД + .env
  -fu / -uf                            fetch + update подряд
  --history [N]                        история версий
"""

import argparse
import getpass

from dotenv import load_dotenv

load_dotenv()

from db.base import init_db
from services.fetch_service import FetchService
from services.update_service import UpdateService

PROVIDERS = ["yandex", "spotify"]


def _print_history(rows) -> None:
    if not rows:
        print("История пуста.")
        return
    print(f"{'provider':<12}\t{'timestamp':<20}\t{'version_id':<36}\t{'expired'}")
    print("-" * 90)
    for r in rows:
        print(
            f"{r.provider:<12}\t{str(r.timestamp)[:19]:<20}\t{r.version_id}\t{'yes' if r.expired else 'no'}"
        )


def do_fetch(provider: str) -> None:
    svc = FetchService()
    targets = PROVIDERS if provider == "all" else [provider]
    for p in targets:
        kwargs = {}
        if p == "yandex":
            kwargs["login"] = input(f"[{p}] логин: ")
            kwargs["password"] = getpass.getpass(f"[{p}] пароль: ")
        svc.run(p, **kwargs)


def do_update(provider: str) -> None:
    svc = UpdateService()
    targets = PROVIDERS if provider == "all" else [provider]
    for p in targets:
        svc.run(p)


def main() -> None:
    init_db()

    parser = argparse.ArgumentParser(description="Yandex Music → Spotify")
    parser.add_argument("-f", "--fetch", nargs="?", const="all", metavar="PROVIDER")
    parser.add_argument("-u", "--update", nargs="?", const="all", metavar="PROVIDER")
    parser.add_argument(
        "-fu", "-uf", nargs="?", const="all", metavar="PROVIDER", dest="fetch_update"
    )
    parser.add_argument("--history", nargs="?", const=10, type=int, metavar="N")

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

    if not any([args.fetch, args.update, args.fetch_update, args.history]):
        parser.print_help()


if __name__ == "__main__":
    main()
