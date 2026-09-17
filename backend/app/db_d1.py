"""
Cloudflare D1 — LONG-TERM store.

Holds anything meant for durable retention:
- long_term_memory: standing facts about Nai
- long_term_tasks: recurring / standing tasks (things marked with the
  \\longtermtask marker, or confirmed "yes" when Shadow asks)
- task_history: archive of every completed task (short or long-term),
  used for growth analysis over time
- feedback_log: every piece of feedback + Shadow's analysis of it
  (requirement 8 — "future improvement ready")

D1 has no official async Python driver, so this talks to Cloudflare's
REST query API directly over httpx: one POST per query, same shape as
Workers' `env.DB.prepare(sql).bind(...args).all()`.
"""
import json
import datetime as dt
import httpx
from .config import CF_ACCOUNT_ID, CF_D1_DATABASE_ID, CF_API_TOKEN

_BASE_URL = "https://api.cloudflare.com/client/v4"

SCHEMA_STATEMENTS = [
    """CREATE TABLE IF NOT EXISTS long_term_memory (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fact TEXT NOT NULL,
        category TEXT NOT NULL DEFAULT 'general',
        created_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS long_term_tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        section TEXT NOT NULL,          -- 'call' | 'message'
        category TEXT NOT NULL,
        due_at_utc TEXT,                 -- nullable: recurring tasks may not have one fixed date
        recurrence TEXT,                 -- e.g. 'daily' | 'weekly:mon' | NULL for one-off long-term
        status TEXT NOT NULL DEFAULT 'pending',
        weather_dependent INTEGER NOT NULL DEFAULT 0,
        notes TEXT,
        created_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS task_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        report_date TEXT NOT NULL,
        task_title TEXT NOT NULL,
        status TEXT NOT NULL,
        retention TEXT NOT NULL,          -- 'short' | 'long'
        notes TEXT,
        created_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS feedback_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        feedback_text TEXT NOT NULL,
        analysis TEXT,
        improvement_action TEXT,
        applied INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL
    )""",
]


async def _query(sql: str, params: list | tuple = ()) -> list[dict]:
    if not (CF_ACCOUNT_ID and CF_D1_DATABASE_ID and CF_API_TOKEN):
        return []  # not configured yet — fail soft, same pattern as Telegram/Twilio elsewhere
    url = f"{_BASE_URL}/accounts/{CF_ACCOUNT_ID}/d1/database/{CF_D1_DATABASE_ID}/query"
    headers = {"Authorization": f"Bearer {CF_API_TOKEN}", "Content-Type": "application/json"}
    body = {"sql": sql, "params": list(params)}
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(url, headers=headers, json=body)
        r.raise_for_status()
        data = r.json()
    if not data.get("success"):
        return []
    results = data.get("result", [])
    if not results:
        return []
    return results[0].get("results", [])


async def init_d1():
    for statement in SCHEMA_STATEMENTS:
        await _query(statement)


# --------------------------------------------------------------------
# Long-term memory (facts)
# --------------------------------------------------------------------
async def add_fact(fact: str, category: str = "general"):
    await _query(
        "INSERT INTO long_term_memory (fact, category, created_at) VALUES (?, ?, ?)",
        (fact, category, dt.datetime.utcnow().isoformat()),
    )


async def all_facts(limit: int = 50) -> list[str]:
    rows = await _query("SELECT fact FROM long_term_memory ORDER BY id DESC LIMIT ?", (limit,))
    return [r["fact"] for r in rows]


# --------------------------------------------------------------------
# Long-term tasks (standing / recurring / \longtermtask marked)
# --------------------------------------------------------------------
async def create_long_task(
    title: str, section: str, category: str,
    due_at_utc: dt.datetime | None, recurrence: str | None = None,
    weather_dependent: bool = False, notes: str = ""
) -> None:
    await _query(
        """INSERT INTO long_term_tasks
           (title, section, category, due_at_utc, recurrence, weather_dependent, notes, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (title, section, category, due_at_utc.isoformat() if due_at_utc else None,
         recurrence, int(weather_dependent), notes, dt.datetime.utcnow().isoformat()),
    )


async def due_long_tasks(now_utc: dt.datetime) -> list[dict]:
    return await _query(
        """SELECT * FROM long_term_tasks
           WHERE status != 'done' AND due_at_utc IS NOT NULL AND due_at_utc <= ?
           ORDER BY due_at_utc ASC""",
        (now_utc.isoformat(),),
    )


async def set_long_task_status(task_id: int, status: str, notes: str = ""):
    await _query(
        "UPDATE long_term_tasks SET status = ?, notes = ? WHERE id = ?", (status, notes, task_id)
    )


async def long_tasks_for_growth(limit: int = 200) -> list[dict]:
    return await _query("SELECT * FROM long_term_tasks ORDER BY created_at DESC LIMIT ?", (limit,))


# --------------------------------------------------------------------
# Task history (archived for growth analysis)
# --------------------------------------------------------------------
async def archive_task(report_date: str, task_title: str, status: str, retention: str, notes: str = ""):
    await _query(
        """INSERT INTO task_history (report_date, task_title, status, retention, notes, created_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (report_date, task_title, status, retention, notes, dt.datetime.utcnow().isoformat()),
    )


async def history_for_growth(days: int = 30) -> list[dict]:
    cutoff = (dt.datetime.utcnow() - dt.timedelta(days=days)).date().isoformat()
    return await _query(
        "SELECT * FROM task_history WHERE report_date >= ? ORDER BY report_date", (cutoff,)
    )


# --------------------------------------------------------------------
# Feedback log (requirement 8)
# --------------------------------------------------------------------
async def log_feedback(feedback_text: str, analysis: dict, improvement_action: str):
    await _query(
        """INSERT INTO feedback_log (feedback_text, analysis, improvement_action, created_at)
           VALUES (?, ?, ?, ?)""",
        (feedback_text, json.dumps(analysis), improvement_action, dt.datetime.utcnow().isoformat()),
    )


async def recent_feedback(limit: int = 20) -> list[dict]:
    return await _query("SELECT * FROM feedback_log ORDER BY id DESC LIMIT ?", (limit,))
