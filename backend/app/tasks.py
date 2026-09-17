import datetime as dt
from . import llm, db_turso, db_d1, weather, calendar_api, timeutils
from .config import LONG_TERM_MARKER, FEATURES


def strip_long_term_marker(text: str) -> tuple[str, bool]:
    """requirement 5: '\\longtermtask <text>' anywhere in the message forces
    long-term (D1) storage with no confirmation question asked."""
    if LONG_TERM_MARKER in text:
        return text.replace(LONG_TERM_MARKER, "").strip(), True
    return text, False


async def extract_task(message: str) -> dict:
    now_local = timeutils.now_local().replace(microsecond=0).isoformat()
    return await llm.extract_task(message, now_local, str(timeutils.TZ))


async def _schedule_weather_aware(title: str, section: str, category: str, notes: str) -> dict:
    """requirement 6: read the week's forecast, pick the best slot, create a
    calendar event, and schedule exactly one reminder (call+message) for it."""
    plan = await weather.plan_weather_task(title)
    chosen_local = plan["chosen_local_dt"]
    if FEATURES.get("google_calendar"):
        await calendar_api.create_event(
            title=title, start_local=chosen_local,
            description=f"Auto-scheduled by Shadow based on weather.\n{plan['reason']}",
        )
    due_utc = timeutils.to_utc_naive(chosen_local)
    task_id = await db_turso.create_short_task(
        title=title, section="both", category=category,
        due_at_utc=due_utc, weather_dependent=True, notes=notes,
    )
    return {"task_id": task_id, "due_utc": due_utc, "due_local": chosen_local, "reason": plan["reason"]}


async def maybe_create_task(message: str, forced_long_term: bool = False) -> dict | None:
    """
    Returns a dict describing what was created/queued, or None if the message
    wasn't a task at all. Shapes:
      {"kind": "short_task", "task": {...}}
      {"kind": "long_task"}
      {"kind": "needs_long_term_confirmation", "payload": {...}}
      {"kind": "weather_task", "due_local": ..., "reason": ...}
    """
    data = await extract_task(message)
    if not data.get("is_task"):
        return None

    title = data.get("title", message)[:255]
    section = data.get("section", "message")
    category = data.get("category", "task")
    weather_dependent = bool(data.get("weather_dependent")) and FEATURES.get("weather_aware_tasks")
    likely_long_term = bool(data.get("likely_long_term")) or forced_long_term

    # --- weather-dependent tasks get their own scheduling path (requirement 6) ---
    if weather_dependent:
        result = await _schedule_weather_aware(title, section, category, notes=message)
        return {"kind": "weather_task", **result, "title": title}

    due_at_local = data.get("due_at_local")
    if not due_at_local:
        return None
    try:
        local_dt = timeutils.parse_local_iso(due_at_local)
        due_at_utc = timeutils.to_utc_naive(local_dt)
    except Exception:
        return None

    # --- forced long-term via \longtermtask marker: write straight to D1 ---
    if forced_long_term:
        await db_d1.create_long_task(
            title=title, section=section, category=category,
            due_at_utc=due_at_utc, weather_dependent=weather_dependent, notes=message,
        )
        return {"kind": "long_task", "title": title, "due_local": local_dt}

    # --- looks long-term but wasn't explicitly marked: ask first (requirement 5) ---
    if likely_long_term:
        payload = {
            "title": title, "section": section, "category": category,
            "due_at_utc": due_at_utc.isoformat(), "weather_dependent": weather_dependent,
            "notes": message,
        }
        await db_turso.queue_confirmation("confirm_long_term", payload)
        return {"kind": "needs_long_term_confirmation", "payload": payload, "title": title, "due_local": local_dt}

    # --- default: short-term task in Turso ---
    task_id = await db_turso.create_short_task(
        title=title, section=section, category=category,
        due_at_utc=due_at_utc, weather_dependent=weather_dependent, notes=message,
    )
    return {"kind": "short_task", "task": {"id": task_id, "title": title, "section": section,
                                            "category": category, "due_local": local_dt}}


async def resolve_long_term_confirmation(accepted: bool, payload: dict):
    if not accepted:
        # user said no -> keep it, but only as a short-term task
        await db_turso.create_short_task(
            title=payload["title"], section=payload["section"], category=payload["category"],
            due_at_utc=dt.datetime.fromisoformat(payload["due_at_utc"]),
            weather_dependent=payload["weather_dependent"], notes=payload["notes"],
        )
        return
    await db_d1.create_long_task(
        title=payload["title"], section=payload["section"], category=payload["category"],
        due_at_utc=dt.datetime.fromisoformat(payload["due_at_utc"]),
        weather_dependent=payload["weather_dependent"], notes=payload["notes"],
    )
