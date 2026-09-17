"""
Turso (libSQL) — SHORT-TERM store.

Holds anything that does not need to survive forever:
- rolling conversation memory
- pending yes/no confirmations
- day-to-day tasks / reminders / break-and-work alarms / crosschecks
- today's report draft (rolled up into the long-term Google Sheet + D1
  task_history at end-of-day, then this table is cleared)

Uses the official `libsql-client` package (async). Falls back to a local
sqlite file automatically if TURSO_DATABASE_URL isn't set, so the project
still runs during local development without a Turso account.
"""
import json
import datetime as dt
import libsql_client
from .config import TURSO_DATABASE_URL, TURSO_AUTH_TOKEN

_client = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS short_term_memory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    role TEXT NOT NULL,
    channel TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pending_confirmations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,            -- 'memory' | 'confirm_long_term' | 'prev_task_status'
    payload TEXT NOT NULL,         -- JSON blob, shape depends on kind
    resolved INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS short_term_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    section TEXT NOT NULL,          -- 'call' | 'message'
    category TEXT NOT NULL,         -- task|reminder|leftover|break|work_alarm|crosscheck|
                                     -- task_description|work_division|growth_analysis|task_update|query
    due_at_utc TEXT NOT NULL,
    weather_dependent INTEGER NOT NULL DEFAULT 0,
    done INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'pending',   -- pending|in_progress|done|skipped
    reminded INTEGER NOT NULL DEFAULT 0,
    announced INTEGER NOT NULL DEFAULT 0,     -- one-time "here's your task" call already made?
    notes TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS daily_report_draft (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    report_date TEXT NOT NULL,      -- YYYY-MM-DD (local)
    task_title TEXT NOT NULL,
    status TEXT NOT NULL,           -- done|pending|in_progress|skipped
    notes TEXT,
    retention TEXT NOT NULL DEFAULT 'short',  -- 'short' | 'long' — which sheet it belongs on
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS used_quotes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    quote TEXT NOT NULL,
    used_on TEXT NOT NULL
);
"""


def _get_client():
    global _client
    if _client is None:
        if TURSO_DATABASE_URL:
            _client = libsql_client.create_client(
                url=TURSO_DATABASE_URL, auth_token=TURSO_AUTH_TOKEN
            )
        else:
            # local dev fallback — no Turso account configured yet
            _client = libsql_client.create_client(url="file:shadow_short_term.db")
    return _client


async def init_turso():
    client = _get_client()
    for statement in [s.strip() for s in SCHEMA.split(";") if s.strip()]:
        await client.execute(statement)


async def execute(sql: str, args: list | tuple = ()):
    client = _get_client()
    return await client.execute(sql, list(args))


async def fetchall(sql: str, args: list | tuple = ()) -> list[dict]:
    rs = await execute(sql, args)
    return [dict(zip(rs.columns, row)) for row in rs.rows]


async def fetchone(sql: str, args: list | tuple = ()) -> dict | None:
    rows = await fetchall(sql, args)
    return rows[0] if rows else None


# --------------------------------------------------------------------
# Conversation memory
# --------------------------------------------------------------------
async def save_turn(role: str, channel: str, content: str):
    await execute(
        "INSERT INTO short_term_memory (role, channel, content, created_at) VALUES (?, ?, ?, ?)",
        (role, channel, content, dt.datetime.utcnow().isoformat()),
    )
    rows = await fetchall("SELECT id FROM short_term_memory ORDER BY id DESC")
    from .config import SHORT_TERM_MAX_MESSAGES
    if len(rows) > SHORT_TERM_MAX_MESSAGES:
        stale_ids = [r["id"] for r in rows[SHORT_TERM_MAX_MESSAGES:]]
        placeholders = ",".join("?" * len(stale_ids))
        await execute(f"DELETE FROM short_term_memory WHERE id IN ({placeholders})", stale_ids)


async def recent_context(limit: int = 20) -> list[dict]:
    rows = await fetchall(
        "SELECT role, content FROM short_term_memory ORDER BY id DESC LIMIT ?", (limit,)
    )
    return list(reversed(rows))


# --------------------------------------------------------------------
# Pending confirmations (memory yes/no, long-term-or-not, previous task status)
# --------------------------------------------------------------------
async def queue_confirmation(kind: str, payload: dict) -> int:
    await execute(
        "INSERT INTO pending_confirmations (kind, payload, created_at) VALUES (?, ?, ?)",
        (kind, json.dumps(payload), dt.datetime.utcnow().isoformat()),
    )
    row = await fetchone("SELECT last_insert_rowid() AS id")
    return row["id"]


async def latest_unresolved(kind: str | None = None) -> dict | None:
    if kind:
        row = await fetchone(
            "SELECT * FROM pending_confirmations WHERE resolved = 0 AND kind = ? ORDER BY id DESC",
            (kind,),
        )
    else:
        row = await fetchone(
            "SELECT * FROM pending_confirmations WHERE resolved = 0 ORDER BY id DESC"
        )
    if row:
        row["payload"] = json.loads(row["payload"])
    return row


async def resolve_confirmation(confirmation_id: int):
    await execute(
        "UPDATE pending_confirmations SET resolved = 1 WHERE id = ?", (confirmation_id,)
    )


# --------------------------------------------------------------------
# Short-term tasks (day tasks / reminders / breaks / crosschecks)
# --------------------------------------------------------------------
async def create_short_task(
    title: str, section: str, category: str, due_at_utc: dt.datetime,
    weather_dependent: bool = False, notes: str = ""
) -> int:
    await execute(
        """INSERT INTO short_term_tasks
           (title, section, category, due_at_utc, weather_dependent, notes, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (title, section, category, due_at_utc.isoformat(), int(weather_dependent), notes,
         dt.datetime.utcnow().isoformat()),
    )
    row = await fetchone("SELECT last_insert_rowid() AS id")
    return row["id"]


async def due_tasks(now_utc: dt.datetime) -> list[dict]:
    return await fetchall(
        """SELECT * FROM short_term_tasks
           WHERE done = 0 AND reminded = 0 AND due_at_utc <= ?
           ORDER BY due_at_utc ASC""",
        (now_utc.isoformat(),),
    )


async def unannounced_tasks() -> list[dict]:
    """Tasks just created that still need their one-time 'here's the plan' call."""
    return await fetchall("SELECT * FROM short_term_tasks WHERE announced = 0")


async def mark_announced(task_id: int):
    await execute("UPDATE short_term_tasks SET announced = 1 WHERE id = ?", (task_id,))


async def mark_reminded(task_id: int):
    await execute("UPDATE short_term_tasks SET reminded = 1 WHERE id = ?", (task_id,))


async def set_task_status(task_id: int, status: str, notes: str = ""):
    done = 1 if status == "done" else 0
    await execute(
        "UPDATE short_term_tasks SET status = ?, done = ?, notes = ? WHERE id = ?",
        (status, done, notes, task_id),
    )


async def latest_task_needing_status() -> dict | None:
    """Most recent task that's due/past-due but never got a status update — used to
    ask 'pichla task kaisa raha?' before starting a new one (requirement 11)."""
    return await fetchone(
        """SELECT * FROM short_term_tasks
           WHERE status = 'pending' AND due_at_utc <= ?
           ORDER BY due_at_utc DESC LIMIT 1""",
        (dt.datetime.utcnow().isoformat(),),
    )


async def tasks_for_day(start_utc: dt.datetime, end_utc: dt.datetime) -> list[dict]:
    return await fetchall(
        "SELECT * FROM short_term_tasks WHERE due_at_utc >= ? AND due_at_utc < ? ORDER BY due_at_utc",
        (start_utc.isoformat(), end_utc.isoformat()),
    )


# --------------------------------------------------------------------
# Daily report draft (rolled into Google Sheets + D1 task_history at EOD)
# --------------------------------------------------------------------
async def add_report_line(report_date: str, task_title: str, status: str, notes: str, retention: str = "short"):
    await execute(
        """INSERT INTO daily_report_draft (report_date, task_title, status, notes, retention, created_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (report_date, task_title, status, notes, retention, dt.datetime.utcnow().isoformat()),
    )


async def report_lines_for(report_date: str) -> list[dict]:
    return await fetchall(
        "SELECT * FROM daily_report_draft WHERE report_date = ? ORDER BY id", (report_date,)
    )


async def clear_report(report_date: str):
    await execute("DELETE FROM daily_report_draft WHERE report_date = ?", (report_date,))


# --------------------------------------------------------------------
# Motivational quote dedup (requirement 9 — daily, never repeated)
# --------------------------------------------------------------------
async def recent_quotes(days: int = 60) -> list[str]:
    cutoff = (dt.datetime.utcnow() - dt.timedelta(days=days)).date().isoformat()
    rows = await fetchall("SELECT quote FROM used_quotes WHERE used_on >= ?", (cutoff,))
    return [r["quote"] for r in rows]


async def record_quote_used(quote: str, used_on: str):
    await execute("INSERT INTO used_quotes (quote, used_on) VALUES (?, ?)", (quote, used_on))
