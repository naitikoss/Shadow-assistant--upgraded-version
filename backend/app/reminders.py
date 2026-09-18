import datetime as dt
import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from .config import (
    TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM_NUMBER,
    TWILIO_CALL_TO_NUMBER, PUBLIC_BASE_URL, WAKE_TIME, EOD_REPORT_TIME, FEATURES,
)
from . import db_turso, db_d1, llm, sheets, timeutils, telegram_client, ntfy_client
from .tts import synthesize

TZ = timeutils.TZ


# --------------------------------------------------------------------
# Low-level senders
# --------------------------------------------------------------------
async def send_telegram_message(text: str):
    await telegram_client.send_text(text)


async def _twilio_call(text: str):
    """Legacy path — only used if FEATURES['use_ntfy_calls'] is False and
    the TWILIO_* env vars are set. Kept for anyone who'd rather pay for a
    real ringing phone call than use the free ntfy + voice-note flow."""
    if not (TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN and TWILIO_FROM_NUMBER and TWILIO_CALL_TO_NUMBER):
        return
    twiml_url = f"{PUBLIC_BASE_URL}/twilio/say?text={httpx.QueryParams({'t': text})['t']}"
    url = f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_ACCOUNT_SID}/Calls.json"
    auth = (TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
    data = {"To": TWILIO_CALL_TO_NUMBER, "From": TWILIO_FROM_NUMBER, "Url": twiml_url}
    async with httpx.AsyncClient(timeout=20) as client:
        await client.post(url, data=data, auth=auth)


async def speak(text: str, ring_title: str = "Shadow"):
    """
    The "call section" channel. Default (free) path:
      1. ntfy urgent push -> phone rings/vibrates/screen-wakes, tap deep-links
         into the Telegram bot chat.
      2. A TTS voice note with the full text is sent to that same chat, so
         it's already waiting the moment the chat opens.
    Falls back to a real Twilio call only if use_ntfy_calls is turned off.
    """
    if FEATURES.get("use_ntfy_calls", True):
        rang = await ntfy_client.ring(ring_title, text, urgent=True)
        audio = await synthesize(text)
        await telegram_client.send_voice(audio, caption=text if not rang else None)
    else:
        await _twilio_call(text)


async def dispatch(text: str, section: str):
    """section: 'call' | 'message' | 'both' — routes to the right channel(s)."""
    if section in ("call", "both"):
        await speak(text)
    if section in ("message", "both"):
        await send_telegram_message(text)


# --------------------------------------------------------------------
# requirement 7 — one call the moment a task is created, telling Nai
# what it is and when it's due. Independent of the later due-time reminder.
# --------------------------------------------------------------------
async def announce_task(title: str, due_local: dt.datetime, section: str):
    text = f"Naya task set ho gaya: \"{title}\", {timeutils.human(due_local)} ke liye."
    await dispatch(text, "call" if section in ("call", "both") else "message")


# --------------------------------------------------------------------
# Interval job: fire reminders for whatever's due right now, both stores
# --------------------------------------------------------------------
async def _check_due_tasks():
    now_utc = dt.datetime.utcnow()

    for task in await db_turso.due_tasks(now_utc):
        local_time = timeutils.utc_naive_to_local(dt.datetime.fromisoformat(task["due_at_utc"]))
        text = f"Reminder: {task['title']} ({timeutils.human(local_time)})"
        await dispatch(text, task["section"])
        await db_turso.mark_reminded(task["id"])

    for task in await db_d1.due_long_tasks(now_utc):
        due_raw = task.get("due_at_utc")
        local_time = timeutils.utc_naive_to_local(dt.datetime.fromisoformat(due_raw)) if due_raw else timeutils.now_local()
        text = f"Reminder (long-term): {task['title']} ({timeutils.human(local_time)})"
        await dispatch(text, task["section"])
        await db_d1.set_long_task_status(task["id"], "reminded", task.get("notes", ""))


# --------------------------------------------------------------------
# requirement 9 — morning greeting, fresh quote every day, then today's plan
# --------------------------------------------------------------------
async def _morning_greeting():
    if not FEATURES.get("morning_greeting"):
        return
    used = await db_turso.recent_quotes(days=60)
    quote = await llm.generate_daily_quote(used)
    await db_turso.record_quote_used(quote, timeutils.today_str())

    weekday = timeutils.weekday_hi()
    greeting = f"Good morning Nai! {weekday} hai aaj. {quote}"
    await speak(greeting, ring_title="Good morning!")

    start_utc, end_utc = timeutils.day_bounds_utc()
    today_tasks = await db_turso.tasks_for_day(start_utc, end_utc)
    if today_tasks:
        lines = "\n".join(
            f"- {t['title']} @ {timeutils.human(timeutils.utc_naive_to_local(dt.datetime.fromisoformat(t['due_at_utc'])))}"
            for t in today_tasks
        )
        plan_text = f"{greeting}\n\nAaj ka plan:\n{lines}"
    else:
        plan_text = f"{greeting}\n\nAaj koi task schedule nahi hai abhi tak — jo bhi karna hai bata dena."
    await send_telegram_message(plan_text)


# --------------------------------------------------------------------
# requirement 10 — end of day report: done / not done / tomorrow's plan
# --------------------------------------------------------------------
async def _end_of_day_report():
    if not FEATURES.get("eod_report"):
        return
    today = timeutils.today_str()
    lines = await db_turso.report_lines_for(today)

    # anything due today that never got a status update counts as "not done"
    start_utc, end_utc = timeutils.day_bounds_utc()
    for task in await db_turso.tasks_for_day(start_utc, end_utc):
        if task["status"] == "pending":
            lines.append({"task_title": task["title"], "status": "skipped",
                          "notes": "Koi update nahi mila.", "retention": "short"})

    report = await llm.build_eod_report(lines)
    text = (f"Aaj ka wrap-up:\n\n✅ Done: {report['done_summary']}\n"
            f"⏳ Pending: {report['not_done_summary']}\n"
            f"📌 Kal ka plan: {report['tomorrow_plan']}")
    await send_telegram_message(text)
    await speak(f"Aaj ka summary: {report['done_summary']}. Kal ka plan: {report['tomorrow_plan']}",
                ring_title="Aaj ka wrap-up")

    for line in lines:
        await sheets.log_task_report(today, line["task_title"], line["status"],
                                      line.get("notes", ""), line.get("retention", "short"))
        await db_d1.archive_task(today, line["task_title"], line["status"],
                                  line.get("retention", "short"), line.get("notes", ""))

    await db_turso.clear_report(today)


# --------------------------------------------------------------------
# Scheduler wiring — everything runs on India time (config.LOCAL_TIMEZONE)
# --------------------------------------------------------------------
def start_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=TZ)
    scheduler.add_job(_check_due_tasks, "interval", seconds=60, id="check_due_tasks")

    wake_h, wake_m = [int(x) for x in WAKE_TIME.split(":")]
    scheduler.add_job(_morning_greeting, CronTrigger(hour=wake_h, minute=wake_m, timezone=TZ), id="morning_greeting")

    eod_h, eod_m = [int(x) for x in EOD_REPORT_TIME.split(":")]
    scheduler.add_job(_end_of_day_report, CronTrigger(hour=eod_h, minute=eod_m, timezone=TZ), id="eod_report")

    scheduler.start()
    return scheduler
