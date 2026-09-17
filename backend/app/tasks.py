import json
import datetime as dt
from sqlalchemy.ext.asyncio import AsyncSession
from .llm import _call_gemini, _call_groq
from .models import Task, ReminderType

EXTRACT_PROMPT = """You extract reminder/task requests from a message.
Current UTC datetime is {now}.

Respond ONLY with strict JSON, no markdown:
{{"is_task": true/false, "title": "<short task title>", "due_at": "<ISO 8601 UTC datetime, or empty if not a task>", "reminder_type": "message" | "call" | "both"}}

If the user asks to be called/rung about something, use "call". If they just want a text/message, use "message".
If unclear or they want both, use "both" only if explicitly asked for both.

Message: "{message}"
"""


async def extract_task(message: str) -> dict:
    now = dt.datetime.utcnow().isoformat()
    prompt = EXTRACT_PROMPT.format(now=now, message=message)
    raw = await _call_gemini([{"role": "user", "content": prompt}])
    if raw is None:
        raw = await _call_groq([{"role": "user", "content": prompt}])
    if not raw:
        return {"is_task": False}
    try:
        cleaned = raw.strip().strip("`").replace("json\n", "").strip()
        return json.loads(cleaned)
    except Exception:
        return {"is_task": False}


async def maybe_create_task(session: AsyncSession, message: str) -> Task | None:
    data = await extract_task(message)
    if not data.get("is_task") or not data.get("due_at"):
        return None
    try:
        due_at = dt.datetime.fromisoformat(data["due_at"].replace("Z", ""))
    except Exception:
        return None
    reminder_type = ReminderType(data.get("reminder_type", "message"))
    task = Task(title=data.get("title", message)[:255], due_at=due_at, reminder_type=reminder_type)
    session.add(task)
    await session.commit()
    await session.refresh(task)
    return task
