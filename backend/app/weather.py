"""
Weather via Open-Meteo (requirement 4) — free, no API key.
Also implements the "weather-aware task" planning logic from requirement 6:
read the week's forecast, pick the best day/time for a weather-sensitive
task, and hand back a plan that brain.py turns into a scheduled reminder
+ calendar event + one call/message at that time.
"""
import httpx
from .config import HOME_LAT, HOME_LON, WEATHER_TIMEZONE
from . import timeutils

_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

# WMO weather codes -> short human description
_WCODE = {
    0: "clear sky", 1: "mostly clear", 2: "partly cloudy", 3: "overcast",
    45: "fog", 48: "fog", 51: "light drizzle", 53: "drizzle", 55: "heavy drizzle",
    61: "light rain", 63: "rain", 65: "heavy rain", 66: "freezing rain", 67: "freezing rain",
    71: "light snow", 73: "snow", 75: "heavy snow", 80: "rain showers", 81: "rain showers",
    82: "violent rain showers", 95: "thunderstorm", 96: "thunderstorm with hail", 99: "thunderstorm with hail",
}


def _describe(code: int) -> str:
    return _WCODE.get(code, "unsettled weather")


async def get_week_forecast() -> list[dict]:
    """Returns up to 7 days of {date, code, description, temp_max, temp_min, rain_chance}."""
    params = {
        "latitude": HOME_LAT,
        "longitude": HOME_LON,
        "daily": "weathercode,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
        "timezone": WEATHER_TIMEZONE,
        "forecast_days": 7,
    }
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(_FORECAST_URL, params=params)
        r.raise_for_status()
        data = r.json()

    daily = data.get("daily", {})
    days = []
    for i, date_str in enumerate(daily.get("time", [])):
        code = daily["weathercode"][i]
        days.append({
            "date": date_str,
            "code": code,
            "description": _describe(code),
            "temp_max": daily["temperature_2m_max"][i],
            "temp_min": daily["temperature_2m_min"][i],
            "rain_chance": daily.get("precipitation_probability_max", [None] * 7)[i],
        })
    return days


def best_day_for_outdoor_task(forecast: list[dict]) -> dict | None:
    """Heuristic fallback (no LLM call needed): lowest rain chance, no thunderstorm/heavy rain."""
    bad_codes = {65, 66, 67, 75, 82, 95, 96, 99}
    candidates = [d for d in forecast if d["code"] not in bad_codes]
    pool = candidates or forecast
    if not pool:
        return None
    return min(pool, key=lambda d: (d["rain_chance"] if d["rain_chance"] is not None else 100))


async def plan_weather_task(task_title: str, preferred_hour: int = 17) -> dict:
    """
    Full requirement-6 flow: look at the week, pick the best slot, and return
    a plan brain.py can act on directly.
    """
    forecast = await get_week_forecast()
    pick = best_day_for_outdoor_task(forecast)
    if not pick:
        # fall back to "today, later" if Open-Meteo is unreachable
        fallback = timeutils.now_local() + __import__("datetime").timedelta(hours=3)
        return {
            "chosen_date": fallback.date().isoformat(),
            "chosen_local_dt": fallback,
            "reason": "Weather data abhi nahi mil paaya, isliye kareeb ke time pe rakh diya.",
            "forecast_summary": [],
        }

    y, m, d = [int(x) for x in pick["date"].split("-")]
    chosen_dt = timeutils.now_local().replace(
        year=y, month=m, day=d, hour=preferred_hour, minute=0, second=0, microsecond=0
    )
    reason = (
        f"{pick['date']} ko {pick['description']} rehne ki ummeed hai "
        f"(baarish ka chance {pick['rain_chance']}%), isliye '{task_title}' ke liye "
        f"yahi din best lag raha hai."
    )
    return {
        "chosen_date": pick["date"],
        "chosen_local_dt": chosen_dt,
        "reason": reason,
        "forecast_summary": forecast,
    }
