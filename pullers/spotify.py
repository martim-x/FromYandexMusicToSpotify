"""
pullers/spotify.py — OAuth 2.0 PKCE флоу для Spotify.

PKCE не требует CLIENT_SECRET.
Нужен только CLIENT_ID (публичный, можно хранить в .env открыто).

Создай приложение: https://developer.spotify.com/dashboard
Redirect URI: http://127.0.0.1:8888/callback
"""

import base64
import hashlib
import os
import platform as _platform
import secrets
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlencode, urlparse

import requests
from dotenv import load_dotenv
from tabulate import tabulate

from core.exceptions import PullerError
from core.models import SpotifyCredentials
from i18n import t
from pullers.base import BasePuller
from services.log_service import write_log

AUTH_URL = "https://accounts.spotify.com/authorize"
TOKEN_URL = "https://accounts.spotify.com/api/token"
REDIRECT_URI = "http://127.0.0.1:8888/callback"
SCOPE = (
    "playlist-read-private "
    "playlist-read-collaborative "
    "playlist-modify-public "
    "playlist-modify-private "
    "user-library-read "
    "user-library-modify "
    "user-read-private "
    "user-read-email"
)

load_dotenv()


def _register_chrome() -> None:
    _os = _platform.system()
    if _os == "Darwin":
        path = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    elif _os == "Windows":
        import winreg

        try:
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe",
            )
            path = winreg.QueryValue(key, None)
        except Exception:
            path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    else:
        path = "google-chrome"
    try:
        webbrowser.register("chrome", None, webbrowser.BackgroundBrowser(path))
    except Exception:
        pass


_register_chrome()


class _CallbackHandler(BaseHTTPRequestHandler):
    code: str | None = None
    error: str | None = None

    def do_GET(self):
        params = parse_qs(urlparse(self.path).query)
        _CallbackHandler.code = params.get("code", [None])[0]
        _CallbackHandler.error = params.get("error", [None])[0]
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK - you can close this tab")

    def log_message(self, *_):
        pass


def _pkce_pair() -> tuple[str, str]:
    """Генерирует code_verifier и code_challenge для PKCE."""
    verifier = secrets.token_urlsafe(64)
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .rstrip(b"=")
        .decode()
    )
    return verifier, challenge


class SpotifyPuller(BasePuller):
    provider = "spotify"

    def pull(self, **_) -> dict:
        try:
            client_id = os.getenv("SPOTIFY_CLIENT_ID", "").strip()

            if not client_id:
                raise PullerError(t("error.spotify_client_id_missing"))

            verifier, challenge = _pkce_pair()

            params = urlencode(
                {
                    "client_id": client_id,
                    "response_type": "code",
                    "redirect_uri": REDIRECT_URI,
                    "scope": SCOPE,
                    "code_challenge_method": "S256",
                    "code_challenge": challenge,
                }
            )

            url = f"{AUTH_URL}?{params}"
            try:
                webbrowser.get("chrome").open(url)
            except Exception:
                webbrowser.open(url)

            print(t("spotify_puller.browser_opened"))

            server = HTTPServer(("127.0.0.1", 8888), _CallbackHandler)
            server.handle_request()

            if _CallbackHandler.error:
                raise PullerError(
                    t("error.spotify_denied", reason=_CallbackHandler.error)
                )
            if not _CallbackHandler.code:
                raise PullerError(t("error.spotify_no_code"))

            resp = requests.post(
                TOKEN_URL,
                data={
                    "grant_type": "authorization_code",
                    "code": _CallbackHandler.code,
                    "redirect_uri": REDIRECT_URI,
                    "client_id": client_id,
                    "code_verifier": verifier,
                },
            )
            resp.raise_for_status()
            token_data = resp.json()

            creds = SpotifyCredentials(
                access_token=token_data["access_token"],
                token_type=token_data.get("token_type", "Bearer"),
                expires_in=token_data.get("expires_in", 3600),
                refresh_token=token_data.get("refresh_token"),
            )
            data = creds.model_dump()

            print(
                tabulate(
                    [
                        ("status", "ok"),
                        ("flow", "PKCE — no CLIENT_SECRET"),
                        ("token_type", creds.token_type),
                        ("expires_in", f"{creds.expires_in}s"),
                        ("refresh_token", "yes" if creds.refresh_token else "no"),
                    ],
                    headers=["field", "value"],
                    tablefmt="rounded_outline",
                )
            )
            write_log(
                f"spotify_puller: tokens received, expires_in={creds.expires_in}s, "
                f"refresh_token={'yes' if creds.refresh_token else 'no'}"
            )

            self.save_buffer(data)
            write_log("spotify_puller: buffer saved → credentials/spotify.json")

            return data

        except Exception as e:
            write_log(f"spotify_puller: failed | {e}")
            raise PullerError(str(e)) from e
