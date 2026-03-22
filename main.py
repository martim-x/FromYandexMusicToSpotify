"""
main.py — точка входа.


  pull [yandex|spotify|all]       браузер → credentials/*.json
  push [yandex|spotify|all]       json → .env + DB


  creds [--all]                   последние креды / полная история
  playlists                       все плейлисты
  playlists add <url> <provider>  добавить плейлист


  link                            интерактив: Spotify (to) → Yandex (from)
  link --show                     таблица всех связей


  run                             перенести все pending связи
  run --link <id>                 повторить конкретную связь


  stats                           статистика всех переносов
  stats --id <id>                 детали конкретного переноса


  debug [yandex|spotify|all]      буфер + .env


  help                            эта инструкция


  lang [en|es|fr|ru]              изменить язык
"""

import json
import os
import re
import sqlite3
import sys
import traceback
from pathlib import Path
from uuid import UUID

from dotenv import load_dotenv
from sqlalchemy import select
from tabulate import tabulate

from db.base import SessionLocal

load_dotenv()

from core.exceptions import (
    BufferEmptyError,
    PullerError,
    PushError,
    UnknownProviderError,
)
from db.base import init_db
from db.models import Transfer, Version
from i18n import t
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
    "spotify": ["SPOTIFY_CLIENT_ID", "SPOTIFY_ACCESS_TOKEN", "SPOTIFY_REFRESH_TOKEN"],
}
DB_PATH = Path(__file__).resolve().parent / "archive.db"


def _err(msg: str) -> None:
    print(f"\n[!] {msg}\n")


def _warn(msg: str) -> None:
    print(f"[~] {msg}")


def _bg_sync() -> None:
    try:
        conn = sqlite3.connect(str(DB_PATH))
        count = conn.execute("SELECT COUNT(*) FROM playlists").fetchone()[0]
        conn.close()
        if count > 0:
            sync_exists_flags()
    except Exception:
        pass


def cmd_help() -> None:
    print(__doc__)


# ── pull ──────────────────────────────────────────────────────────────


def cmd_pull(args: list[str]) -> None:
    provider = args[0] if args else "all"
    if provider not in PROVIDERS + ["all"]:
        _err(t("cmd.pull.unknown", provider=provider))
        return
    svc = PullService()
    for p in PROVIDERS if provider == "all" else [provider]:
        try:
            svc.run(p)
        except PullerError as e:
            _err(t("cmd.pull.failed", provider=p, error=e))
        except Exception as e:
            _err(t("cmd.pull.unexpected", provider=p, error=e))


# ── push ──────────────────────────────────────────────────────────────


def cmd_push(args: list[str]) -> None:
    provider = args[0] if args else "all"
    if provider not in PROVIDERS + ["all"]:
        _err(t("cmd.push.unknown", provider=provider))
        return
    svc = PushService()
    for p in PROVIDERS if provider == "all" else [provider]:
        try:
            svc.run(p)
        except BufferEmptyError:
            _err(t("push.buffer_not_found", provider=p))
        except (PushError, UnknownProviderError) as e:
            _err(str(e))
        except Exception as e:
            _err(t("cmd.push.unexpected", provider=p, error=e))


# ── creds ─────────────────────────────────────────────────────────────


def cmd_creds(args: list[str]) -> None:
    show_all = "--all" in args
    remaining = [a for a in args if a != "--all"]
    provider = remaining[0] if remaining else "all"
    if provider not in PROVIDERS + ["all"]:
        _err(t("cmd.creds.unknown", provider=provider))
        return
    for prov in PROVIDERS if provider == "all" else [provider]:
        _cmd_creds_one(prov, show_all)


def _cmd_creds_one(provider: str, show_all: bool) -> None:
    try:
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row

        if show_all:
            rows = conn.execute(
                """
                SELECT substr(cast(c.id as text),1,8)||'...' as short_id,
                       p.name as provider,
                       v.timestamp,
                       c.expired,
                       substr(cast(v.version as text),1,8)||'...' as ver
                FROM credentials c
                JOIN versions v ON v.id = c.version_id
                JOIN providers p ON p.id = c.provider_id
                WHERE p.name = ?
                ORDER BY v.timestamp DESC
                """,
                (provider,),
            ).fetchall()
            conn.close()
            if not rows:
                _warn(t("cmd.creds.history_empty", provider=provider))
                return
            print(f"\n{t('cmd.creds.history_header', provider=provider)}")
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
                SELECT substr(cast(c.id as text),1,8)||'...' as short_id,
                       v.timestamp, c.data
                FROM credentials c
                JOIN versions v ON v.id = c.version_id
                JOIN providers p ON p.id = c.provider_id
                WHERE p.name = ? AND c.expired = 0
                ORDER BY v.timestamp DESC LIMIT 1
                """,
                (provider,),
            ).fetchone()
            conn.close()
            if not row:
                _warn(t("cmd.creds.empty", provider=provider))
                return
            data = json.loads(row["data"])
            kv = []
            for k, v in data.items():
                s = str(v)
                display = (
                    s[:6] + "***" + s[-4:]
                    if k in ("cookie", "access_token", "refresh_token") and len(s) > 10
                    else s
                )
                kv.append([k, display])
            print(f"\n{t('cmd.creds.active_header', provider=provider)}")
            print(
                tabulate(
                    [[row["short_id"], provider, str(row["timestamp"])[:19]]],
                    headers=["id", "provider", "timestamp"],
                    tablefmt="rounded_outline",
                )
            )
            print(tabulate(kv, headers=["field", "value"], tablefmt="rounded_outline"))
    except Exception as e:
        _err(t("cmd.creds.error", error=e))


# ── playlists ─────────────────────────────────────────────────────────


def cmd_playlists(args: list[str]) -> None:
    if args and args[0] == "add":
        if len(args) < 3:
            _err(t("cmd.playlists.usage"))
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
            _err(t("cmd.playlists.add_error", error=e))
        return

    pls = list_playlists()
    links = list_links()

    if pls:
        print(f"\n{t('cmd.playlists.header')}")
        print(
            tabulate(
                [
                    [p["id"], p["provider"], p["name"], p["exists"], p["url"]]
                    for p in pls
                ],
                headers=["id", "provider", "name", "exists", "url"],
                tablefmt="rounded_outline",
            )
        )
    else:
        _warn(t("cmd.playlists.none"))

    if links:
        print(f"\n{t('cmd.playlists.links_header')}")
        print(
            tabulate(
                [[l["id"], l["from"], l["to"], l["status"], l["total"]] for l in links],
                headers=["id", "from", "to", "status", "total"],
                tablefmt="rounded_outline",
            )
        )


# ── link ──────────────────────────────────────────────────────────────


def cmd_link(args: list[str]) -> None:
    if "--show" in args:
        links = list_links()
        if not links:
            _warn(t("cmd.link.no_links"))
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
        _err(t("cmd.link.no_spotify"))
        return
    if not yandex:
        _err(t("cmd.link.no_yandex"))
        return

    print(f"\n{t('cmd.link.step1')}\n")
    print(
        tabulate(
            [[i + 1, p["name"], p["url"]] for i, p in enumerate(spotify)],
            headers=["#", "name", "url"],
            tablefmt="rounded_outline",
        )
    )
    while True:
        try:
            idx = int(input(f"\n{t('cmd.link.prompt_spotify')} ")) - 1
            if 0 <= idx < len(spotify):
                to_pl = spotify[idx]
                break
            _warn(t("cmd.link.warn_range_spotify", n=len(spotify)))
        except ValueError:
            _warn(t("cmd.link.warn_digits"))

    print(f"\n{t('cmd.link.step2', name=to_pl['name'])}\n")
    print(
        tabulate(
            [[i + 1, p["name"], p["url"]] for i, p in enumerate(yandex)],
            headers=["#", "name", "url"],
            tablefmt="rounded_outline",
        )
    )
    while True:
        raw = input(f"\n{t('cmd.link.prompt_yandex')} ")
        parts = raw.replace(",", " ").replace(".", " ").split()
        try:
            indices = [int(x) - 1 for x in parts]
            if indices and all(0 <= i < len(yandex) for i in indices):
                from_pls = [yandex[i] for i in indices]
                break
            _warn(t("cmd.link.warn_range_yandex", n=len(yandex)))
        except ValueError:
            _warn(t("cmd.link.warn_digits"))

    created = []
    for from_pl in from_pls:
        try:
            lnk = link_playlists(from_pl["full_id"], to_pl["full_id"])
            created.append([from_pl["name"], to_pl["name"], str(lnk.id)[:8] + "..."])
        except Exception as e:
            _err(t("cmd.link.error", frm=from_pl["name"], to=to_pl["name"], error=e))
    if created:
        print(f"\n{t('cmd.link.created_header')}")
        print(
            tabulate(created, headers=["from", "to", "id"], tablefmt="rounded_outline")
        )


# ── run ───────────────────────────────────────────────────────────────


def cmd_run(args: list[str]) -> None:
    if "--link" in args:
        idx = args.index("--link") + 1
        if idx >= len(args):
            _err(t("cmd.run.no_link_id"))
            return
        _run_by_link(args[idx])
        return

    try:
        results = run_all()
    except Exception as e:
        _err(t("cmd.run.error", error=e))
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


def _resolve_link_id(prefix: str) -> str | None:
    with SessionLocal() as session:
        links = session.execute(select(Transfer)).scalars().all()
        matches = [str(lnk.id) for lnk in links if str(lnk.id).startswith(prefix)]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        _err(t("cmd.run.ambiguous", prefix=prefix, count=len(matches)))
    return None


def _run_by_link(link_id: str) -> None:
    full_id = link_id
    try:
        UUID(link_id)
    except ValueError:
        full_id = _resolve_link_id(link_id)
        if not full_id:
            _err(t("cmd.run.link_not_found", id=link_id))
            return

    with SessionLocal() as session:
        lnk = session.get(Transfer, UUID(full_id))
        if not lnk:
            _err(t("cmd.run.link_db_not_found", id=link_id[:8]))
            return
        lnk.status = "pending"
        session.commit()

    _warn(t("cmd.run.reset_pending", id=link_id[:8]))
    cmd_run([])


# ── stats ─────────────────────────────────────────────────────────────


def cmd_stats(args: list[str]) -> None:
    transfer_id = None
    if "--id" in args:
        idx = args.index("--id") + 1
        transfer_id = args[idx] if idx < len(args) else None

    stats = get_stats(transfer_id)
    if not stats:
        _warn(t("cmd.stats.none"))
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

        buf = Path(__file__).resolve().parent / "credentials" / f"{p}.json"
        print(f"\n{t('cmd.debug.buffer_header', provider=p)}")
        if buf.exists():
            rows = []
            for k, v in json.loads(buf.read_text()).items():
                s = str(v)
                display = (
                    s[:6] + "***" + s[-4:]
                    if k in ("cookie", "access_token", "refresh_token") and len(s) > 10
                    else s
                )
                rows.append([k, display])
            print(
                tabulate(rows, headers=["field", "value"], tablefmt="rounded_outline")
            )
        else:
            _warn(t("cmd.debug.buffer_missing", provider=p))

        print(f"\n{t('cmd.debug.env_header')}")
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


# ── lang ──────────────────────────────────────────────────────────────


def cmd_lang(args: list[str]) -> None:
    from i18n import _LANGS, get_lang, set_lang

    if not args:
        print(t("cmd.lang.current", lang=get_lang()))
        print(t("cmd.lang.available", langs=", ".join(sorted(_LANGS))))
        return

    lang = args[0].lower()
    if lang not in _LANGS:
        _err(t("cmd.lang.unsupported", lang=lang, langs=", ".join(sorted(_LANGS))))
        return

    set_lang(lang)

    env_path = Path(".env")
    if env_path.exists():
        content = env_path.read_text(encoding="utf-8")
        if re.search(r"^LANG=", content, re.MULTILINE):
            content = re.sub(r"^LANG=.*$", f"LANG={lang}", content, flags=re.MULTILINE)
        else:
            content += f"\nLANG={lang}"
        env_path.write_text(content, encoding="utf-8")
    else:
        env_path.write_text(f"LANG={lang}\n", encoding="utf-8")

    print(t("cmd.lang.set", lang=lang))


# ── router ────────────────────────────────────────────────────────────


COMMANDS = {
    "pull": cmd_pull,
    "push": cmd_push,
    "creds": cmd_creds,
    "playlists": cmd_playlists,
    "link": cmd_link,
    "run": cmd_run,
    "stats": cmd_stats,
    "lang": cmd_lang,
    "debug": cmd_debug,
    "help": lambda _: cmd_help(),
}


def main() -> None:
    try:
        init_db()
    except Exception as e:
        print(t("cmd.db_init_fail", error=e))
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
        _err(t("cmd.err.unknown_cmd", cmd=cmd))
        print(t("cmd.err.available"))
        print("  " + "  ".join(COMMANDS.keys()))


if __name__ == "__main__":
    main()
