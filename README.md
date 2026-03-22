# YandexMusic → Spotify Transfer

CLI tool to transfer playlists and liked tracks from Yandex Music to Spotify.
Runs fully locally — no third-party servers, no cloud, all data stays in your SQLite database.

## User Guide

### Requirements

- Python 3.11+
- Google Chrome
- Spotify account + app on [developer.spotify.com](https://developer.spotify.com/dashboard)
- Yandex Music account

```bash
git clone https://github.com/yourname/FromYandexMusicToSpotify
cd FromYandexMusicToSpotify
pip install -r requirements.txt
```

### Spotify App Setup

1. Go to https://developer.spotify.com/dashboard → **Create app**
2. Add Redirect URI: `http://127.0.0.1:8888/callback`
3. Copy **Client ID** and **Client Secret**
4. Add to `.env`:

```env
SPOTIFY_CLIENT_ID=your_client_id
SPOTIFY_CLIENT_SECRET=your_client_secret
LANG=en
```

---

### Quick Start

```bash
# 1. Grab Yandex cookies via browser
python main.py pull yandex

# 2. Authorize Spotify via browser
python main.py pull spotify

# 3. Save credentials to DB
python main.py push yandex
python main.py push spotify

# 4. Add playlists
python main.py playlists add https://music.yandex.ru/users/login/playlists/3 yandex
python main.py playlists add https://open.spotify.com/playlist/ID spotify

# 5. Link Yandex → Spotify (interactive)
python main.py link

# 6. Run transfer
python main.py run
```

---

### Playlist Linking

The tool supports flexible **many-to-one** and **many-to-many** linking:

```
# Many Yandex playlists → one Spotify playlist
Yandex: "Rock 2020"  ──┐
Yandex: "Rock 2021"  ──┼──► Spotify: "My Rock"
Yandex: "Rock 2022"  ──┘

# Each Yandex playlist → its own Spotify playlist
Yandex: "Chill"  ──► Spotify: "Chill Mix"
Yandex: "Hype"   ──► Spotify: "Hype Mix"
```

During `link` you choose one Spotify playlist as destination, then select
one or more Yandex playlists to link to it — separated by space, comma or dot.
Repeat `link` to create as many pairs as needed.

---

### Transfer Results

Each track gets one of three statuses:

| Status          | Meaning                                |
| --------------- | -------------------------------------- |
| `[+] matched`   | Exact match — title + artist           |
| `[~] partial`   | Found by title only, artist may differ |
| `[-] not_found` | Not found in Spotify                   |

---

### All Commands

| Command                           | Description                                  |
| --------------------------------- | -------------------------------------------- |
| `pull yandex\|spotify\|all`       | Authorize and save credentials to buffer     |
| `push yandex\|spotify\|all`       | Write buffer to DB + `.env`                  |
| `creds [yandex\|spotify] [--all]` | Show active credentials or full history      |
| `playlists`                       | List all playlists and links                 |
| `playlists add <url> <provider>`  | Add a playlist                               |
| `link`                            | Interactively link Yandex → Spotify playlist |
| `link --show`                     | Show all existing links                      |
| `run`                             | Transfer all pending links                   |
| `run --link <id>`                 | Re-run a specific link by id (prefix ok)     |
| `stats`                           | Show transfer history                        |
| `stats --id <id>`                 | Details of a specific transfer               |
| `debug [yandex\|spotify\|all]`    | Show buffer + `.env` status                  |
| `lang <code>`                     | Change language                              |
| `help`                            | Show this help                               |

---

### Language

```bash
python main.py lang ru
```

Supported: `en` `ru` `de` `es` `fr` `pl` `ro` `bg` `tr` `hi` `zh`

---

##  Developer Guide

### Project Structure

```
├── core/
│   ├── exceptions.py        # PullerError, PushError, BufferEmptyError, UnknownProviderError
│   ├── interfaces.py        # AbstractPuller, AbstractPushService
│   ├── models.py            # Pydantic schemas: SpotifyCredentials, YandexCredentials,
│   │                        #   VersionSchema, CredentialSchema, ArchiveRow
│   └── spinner.py           # CLI progress spinner
│
├── db/
│   ├── base.py              # SessionLocal, engine, init_db()
│   ├── models.py            # ORM: Provider, Version, Credential, Playlist,
│   │                        #   Transfer, Track, VerifiedTrack, Log
│   └── repository.py        # CredentialRepository, VersionRepository
│
├── i18n/
│   ├── __init__.py          # t(), set_lang(), get_lang(), _load()
│   └── *.json               # en ru de es fr pl ro bg tr hi zh
│
├── pullers/
│   ├── base.py              # BasePuller — save_buffer() / load_buffer()
│   ├── spotify.py           # OAuth 2.0 flow → credentials/spotify.json
│   └── yandex.py            # undetected-chromedriver cookie grab → credentials/yandex.json
│
├── services/
│   ├── log_service.py       # write_log() → logs table
│   ├── playlist_service.py  # add_playlist(), link_playlists(), list_*(), sync_exists_flags()
│   ├── pull_service.py      # PullService.run(provider)
│   ├── push_service.py      # PushService.run(provider) — dedup + versioning
│   ├── spotify_api.py       # search_track(), add_tracks_to_playlist(), get_playlist_info()
│   ├── transfer_service.py  # run_all(), _run_one(), get_stats()
│   └── yandex_api.py        # get_tracks(), _liked_tracks(), _fetch_by_ids(), _parse()
│
├── credentials/             # gitignored — raw JSON buffers after pull
├── archive.db               # SQLite — all data
├── main.py                  # CLI router
└── .env
```

---

### Data Flow

```
pull
  └─► BasePuller.pull()
        └─► credentials/{provider}.json   (raw buffer)

push
  └─► PushService.run(provider)
        ├─► SHA-256 hash → skip if duplicate   (dedup)
        ├─► Version(id, version, timestamp)    (versioning)
        ├─► Credential(data, hash, expired=False)
        ├─► mark previous credentials expired
        └─► _write_env() → .env

run
  └─► transfer_service._run_one()
        ├─► yandex_api.get_tracks()
        ├─► Track rows → DB  (status=pending)
        ├─► ThreadPoolExecutor(MAX_WORKERS=4)
        │     └─► spotify_api.search_track()  ← global Lock, 150ms between requests
        ├─► _Watchdog — cancels executor if no progress for 10s
        ├─► _update_track() → matched / partial / not_found
        ├─► spotify_api.add_tracks_to_playlist()  ← batches of 100
        └─► VerifiedTrack rows → DB
```

---

### Versioning

Every `push` creates a new `Version` row with a UUID and timestamp.
All subsequent records — `Credential`, `Transfer`, `Log` — reference a `version_id`.
Previous credentials for the same provider are marked `expired=True`, the new one is active.

This gives a full audit trail: you can always see which credentials were active
during any transfer and replay the history with `creds --all`.

```
versions
  └── credentials  (expired flag, data_hash for dedup)
  └── transfers
        └── tracks
              └── verified_tracks
  └── logs
```

---

### Playlist Linking Model

`Playlist` has two relationship lists on `Transfer`:

```python
from_links: list[Transfer]   # all transfers where this playlist is source
to_links:   list[Transfer]   # all transfers where this playlist is destination
```

This allows **n-to-1** and **n-to-n** linking without schema changes:

```
# n-to-1
Transfer(from=YandexA, to=SpotifyX)
Transfer(from=YandexB, to=SpotifyX)
Transfer(from=YandexC, to=SpotifyX)

# n-to-n
Transfer(from=YandexA, to=SpotifyX)
Transfer(from=YandexA, to=SpotifyY)
```

Each `Transfer` is independent — has its own status, counters and track rows.
Re-running a specific link resets its status to `pending` without affecting others.

---

### Rate Limiting

`spotify_api._rate_limited_get()` uses a global `threading.Lock` shared across
all worker threads. Minimum interval between requests is **150ms (~6 req/s)**.
On HTTP 429 the thread sleeps for `Retry-After` seconds and retries up to 3 times.

---

### Watchdog

`_Watchdog` is a daemon thread started before `ThreadPoolExecutor`.
It calls `tick()` after every completed future. If no tick arrives within
`WATCHDOG_TIMEOUT=10s`, it sets `triggered=True`, cancels the executor and
saves partial results. Transfer status becomes `partial_done` instead of `done`.

---

### Credential Dedup

Before writing to DB, `PushService` computes `SHA-256` of the sorted JSON buffer.
If a credential with the same hash already exists for the provider — the write is skipped entirely.
No new `Version`, no new `Credential`, `.env` is not touched.

---

### i18n

All user-visible strings go through `t(key, **kwargs)`.
Language is read from `LANG` in `.env` at import time.
If the requested locale file is missing — falls back to `en.json`.

**Adding a new language:**

1. Copy `i18n/en.json` → `i18n/xx.json`, translate all values
2. Add `"xx"` to `_LANGS` in `i18n/__init__.py`

---

### Environment Variables

| Variable                | Required | Set by         |
| ----------------------- | -------- | -------------- |
| `SPOTIFY_CLIENT_ID`     | manual   | `.env`         |
| `SPOTIFY_CLIENT_SECRET` | manual   | `.env`         |
| `SPOTIFY_ACCESS_TOKEN`  | auto     | `push spotify` |
| `SPOTIFY_REFRESH_TOKEN` | auto     | `push spotify` |
| `YANDEX_UID`            | auto     | `push yandex`  |
| `YANDEX_COOKIE`         | auto     | `push yandex`  |
| `LANG`                  | auto     | `lang <code>`  |
