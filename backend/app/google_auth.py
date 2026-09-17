"""
Shared OAuth2 access-token refresh for Google Calendar + Google Sheets.
One refresh token (from an OAuth "installed app" / desktop flow, generated
once by hand) is reused everywhere so we don't pull in the full
google-api-python-client dependency for two REST calls.
"""
import time
import httpx
from .config import GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REFRESH_TOKEN

_TOKEN_URL = "https://oauth2.googleapis.com/token"
_cached_token: str | None = None
_cached_until: float = 0.0


async def get_access_token() -> str | None:
    global _cached_token, _cached_until
    if not (GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET and GOOGLE_REFRESH_TOKEN):
        return None
    if _cached_token and time.monotonic() < _cached_until:
        return _cached_token

    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(_TOKEN_URL, data={
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "refresh_token": GOOGLE_REFRESH_TOKEN,
            "grant_type": "refresh_token",
        })
        if r.status_code != 200:
            return None
        data = r.json()

    _cached_token = data.get("access_token")
    _cached_until = time.monotonic() + int(data.get("expires_in", 3000)) - 60
    return _cached_token
