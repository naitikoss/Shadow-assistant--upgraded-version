"""
Single source of truth for date/time handling.

Uses only the Python standard library (datetime + zoneinfo) — no pytz,
no arrow, nothing extra. Everything is pinned to India (Asia/Kolkata via
config.LOCAL_TIMEZONE) since that's the only timezone this assistant
needs to reason in. Every other module should go through here instead of
calling datetime.now()/utcnow() directly, so the "India" assumption lives
in exactly one place.
"""
import datetime as dt
from zoneinfo import ZoneInfo
from .config import LOCAL_TIMEZONE

TZ = ZoneInfo(LOCAL_TIMEZONE)
UTC = dt.timezone.utc

# Hindi/English weekday + month names, handy for voice replies
_WEEKDAYS_HI = ["Somvaar", "Mangalvaar", "Budhvaar", "Guruvaar", "Shukravaar", "Shanivaar", "Ravivaar"]


def now_local() -> dt.datetime:
    """Current wall-clock time in India."""
    return dt.datetime.now(TZ)


def now_utc() -> dt.datetime:
    return dt.datetime.now(UTC)


def today_str() -> str:
    """YYYY-MM-DD for the current day in India — used as the report-date key."""
    return now_local().strftime("%Y-%m-%d")


def to_utc_naive(local_dt: dt.datetime) -> dt.datetime:
    """A naive-or-aware local datetime -> naive UTC datetime, for DB storage."""
    if local_dt.tzinfo is None:
        local_dt = local_dt.replace(tzinfo=TZ)
    return local_dt.astimezone(UTC).replace(tzinfo=None)


def utc_naive_to_local(utc_dt: dt.datetime) -> dt.datetime:
    """A naive UTC datetime (as read back from a DB) -> aware local datetime."""
    if utc_dt.tzinfo is None:
        utc_dt = utc_dt.replace(tzinfo=UTC)
    return utc_dt.astimezone(TZ)


def parse_local_iso(iso_str: str) -> dt.datetime:
    """Parse an ISO string (no offset) as a local (India) datetime."""
    parsed = dt.datetime.fromisoformat(iso_str)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=TZ)
    return parsed


def parse_hhmm_today_or_tomorrow(hhmm: str, only_future: bool = False) -> dt.datetime:
    """'07:00' -> today's (or tomorrow's, if already past and only_future) local datetime."""
    h, m = [int(x) for x in hhmm.split(":")]
    candidate = now_local().replace(hour=h, minute=m, second=0, microsecond=0)
    if only_future and candidate <= now_local():
        candidate += dt.timedelta(days=1)
    return candidate


def human(local_dt: dt.datetime) -> str:
    """'17 Sep, 07:00 AM' style formatting for calls/messages."""
    return local_dt.strftime("%d %b, %I:%M %p")


def weekday_hi(local_dt: dt.datetime | None = None) -> str:
    local_dt = local_dt or now_local()
    return _WEEKDAYS_HI[local_dt.weekday()]


def day_bounds_utc(day_local: dt.date | None = None) -> tuple[dt.datetime, dt.datetime]:
    """UTC-naive (start, end) bounds of one local calendar day — for 'today's tasks' queries."""
    day_local = day_local or now_local().date()
    start_local = dt.datetime.combine(day_local, dt.time.min, tzinfo=TZ)
    end_local = start_local + dt.timedelta(days=1)
    return to_utc_naive(start_local), to_utc_naive(end_local)
