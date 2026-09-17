"""
Google Calendar integration (requirement 4).

Plain REST calls to Calendar v3 using the shared OAuth token from
google_auth.py — keeps dependencies light (no google-api-python-client).
"""
import datetime as dt
import httpx
from .config import GOOGLE_CALENDAR_ID, FEATURES
from .google_auth import get_access_token
from . import timeutils

_API = "https://www.googleapis.com/calendar/v3"


async def create_event(title: str, start_local: dt.datetime, end_local: dt.datetime | None = None,
                        description: str = "") -> str | None:
    """Creates a calendar event; returns the event id, or None if not configured / failed."""
    if not FEATURES.get("google_calendar"):
        return None
    token = await get_access_token()
    if not token:
        return None
    end_local = end_local or (start_local + dt.timedelta(minutes=30))

    body = {
        "summary": title,
        "description": description,
        "start": {"dateTime": start_local.isoformat(), "timeZone": str(timeutils.TZ)},
        "end": {"dateTime": end_local.isoformat(), "timeZone": str(timeutils.TZ)},
    }
    url = f"{_API}/calendars/{GOOGLE_CALENDAR_ID}/events"
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(url, headers=headers, json=body)
        if r.status_code >= 300:
            return None
        return r.json().get("id")


async def list_events_today() -> list[dict]:
    token = await get_access_token()
    if not token:
        return []
    start_utc, end_utc = timeutils.day_bounds_utc()
    params = {
        "timeMin": start_utc.replace(tzinfo=dt.timezone.utc).isoformat(),
        "timeMax": end_utc.replace(tzinfo=dt.timezone.utc).isoformat(),
        "singleEvents": "true",
        "orderBy": "startTime",
    }
    url = f"{_API}/calendars/{GOOGLE_CALENDAR_ID}/events"
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(url, headers=headers, params=params)
        if r.status_code >= 300:
            return []
        return r.json().get("items", [])
