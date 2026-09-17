import datetime as dt
import httpx
from sqlalchemy import select
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from .config import (
    TELEGRAM_BOT_TOKEN, TELEGRAM_OWNER_ID,
    TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM_NUMBER,
    TWILIO_CALL_TO_NUMBER, PUBLIC_BASE_URL,
)
from .models import Task, ReminderType
from .database import SessionLocal


async def send_telegram_message(text: str):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_OWNER_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    async with httpx.AsyncClient(timeout=15) as client:
        await client.post(url, json={"chat_id": TELEGRAM_OWNER_ID, "text": text})


async def make_reminder_call(text: str):
    if not (TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN and TWILIO_FROM_NUMBER and TWILIO_CALL_TO_NUMBER):
        return
    # Twilio hits this URL to fetch what to say — a tiny inline TwiML endpoint,
    # registered separately as GET/POST /twilio/say (see main.py)
    twiml_url = f"{PUBLIC_BASE_URL}/twilio/say?text={httpx.QueryParams({'t': text})['t']}"
    url = f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_ACCOUNT_SID}/Calls.json"
    auth = (TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
    data = {"To": TWILIO_CALL_TO_NUMBER, "From": TWILIO_FROM_NUMBER, "Url": twiml_url}
    async with httpx.AsyncClient(timeout=20) as client:
        await client.post(url, data=data, auth=auth)


async def _check_due_tasks():
    async with SessionLocal() as session:
        now = dt.datetime.utcnow()
        result = await session.execute(
            select(Task).where(Task.done == False, Task.reminded == False, Task.due_at <= now)  # noqa: E712
        )
        due_tasks = result.scalars().all()
        for task in due_tasks:
            text = f"Reminder: {task.title}"
            if task.reminder_type in (ReminderType.message, ReminderType.both):
                await send_telegram_message(text)
            if task.reminder_type in (ReminderType.call, ReminderType.both):
                await make_reminder_call(text)
            task.reminded = True
        if due_tasks:
            await session.commit()


def start_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    scheduler.add_job(_check_due_tasks, "interval", seconds=60, id="check_due_tasks")
    scheduler.start()
    return scheduler
