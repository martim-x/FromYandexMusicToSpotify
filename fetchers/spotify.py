"""fetchers/spotify.py - OAuth 2.0 токен для Spotify."""

import os
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlencode, urlparse

import requests
from dotenv import load_dotenv

load_dotenv()

from core.exceptions import FetcherError
from core.models import SpotifyCredentials
from fetchers.base import BaseFetcher

SPOTIFY_AUTH_URL = "https://accounts.spotify.com/authorize"
SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"
REDIRECT_URI = "http://127.0.0.1:8888/callback"
SCOPE = "user-library-modify user-library-read"

webbrowser.register(
    "chrome",
    None,
    webbrowser.BackgroundBrowser(
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    ),
)


class _CallbackHandler(BaseHTTPRequestHandler):
    code: str | None = None

    def do_GET(self):
        params = parse_qs(urlparse(self.path).query)
        _CallbackHandler.code = params.get("code", [None])[0]
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK - you can close this tab")

    def log_message(self, *_):
        pass


class SpotifyFetcher(BaseFetcher):
    provider = "spotify"

    def fetch(self, **_) -> dict:
        client_id = os.getenv("SPOTIFY_CLIENT_ID")
        client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")

        if not client_id or not client_secret:
            raise FetcherError(
                "\nSPOTIFY_CLIENT_ID / SPOTIFY_CLIENT_SECRET не найдены в .env\n"
                "1. Зайди на https://developer.spotify.com/dashboard\n"
                "2. Создай приложение, скопируй Client ID и Client Secret\n"
                "3. Добавь в .env:\n"
                "   SPOTIFY_CLIENT_ID=xxx\n"
                "   SPOTIFY_CLIENT_SECRET=xxx\n"
                "   SPOTIFY_REDIRECT_URI=http://localhost:8888/callback"
            )

        params = urlencode(
            {
                "client_id": client_id,
                "response_type": "code",
                "redirect_uri": REDIRECT_URI,
                "scope": SCOPE,
            }
        )
        url = f"{SPOTIFY_AUTH_URL}?{params}"
        try:
            chrome = webbrowser.get("chrome")
            chrome.open(url)
        except Exception:
            webbrowser.open(url)
        print("[spotify_fetcher] браузер открыт — жди авторизации...")

        server = HTTPServer(("localhost", 8888), _CallbackHandler)
        server.handle_request()

        code = _CallbackHandler.code
        if not code:
            raise FetcherError("Spotify: не получен code от callback")

        resp = requests.post(
            SPOTIFY_TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": REDIRECT_URI,
            },
            auth=(client_id, client_secret),
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
        self.save_buffer(data)
        print("[spotify_fetcher] токен получен")
        return data
