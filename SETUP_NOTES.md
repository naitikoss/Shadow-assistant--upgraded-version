# Shadow Assistant — upgrade notes

This is a rewrite of `backend/app/` covering the 11 points you listed. It
replaces the old single Postgres database with two stores, adds weather +
calendar + sheets integrations, and restructures the reminder pipeline into
"call section" vs "message section" as you described.

## 0. A pre-existing bug this also fixes
`app/keypool.py` was a **completely empty file**, even though `llm.py` and
`stt.py` both `import KeyPool` from it. As committed on GitHub, the bot could
not start. `keypool.py` now has a real round-robin key pool with 429 cooldown
handling.

## 1. Future-improvement-ready (requirement 1)
- `config.py` has a `FEATURES = {...}` dict at the top. Every new behaviour
  (weather scheduling, task announcement calls, morning greeting, EOD report,
  "ask previous task", feedback learning, calendar, sheets) is gated behind a
  flag there. Turn things on/off without touching logic.
- Each integration (weather, calendar, sheets, D1, Turso, feedback) lives in
  its own file with a narrow interface, so a future swap (e.g. a different
  calendar provider) only touches one file.

## 2. Call section vs Message section (requirement 2)
`llm.py`'s `extract_task()` prompt now classifies every task-like message into:
- **Call section** categories: `task`, `leftover`, `break`, `work_alarm`, `crosscheck`
- **Message section** categories: `task_description`, `work_division`, `growth_analysis`, `task_update`, `query`

`reminders.dispatch(text, section)` then sends to Twilio, Telegram, or both
based on that classification.

## 3. Timezone / date / time (requirement 3)
New `app/timeutils.py` — stdlib only (`datetime` + `zoneinfo`), pinned to
`Asia/Kolkata` via `config.LOCAL_TIMEZONE`. Every other module now goes
through this instead of calling `datetime.now()`/`utcnow()` directly.

## 4. Weather (Open-Meteo) + Calendar (Google Calendar) (requirement 4)
- `app/weather.py` — free Open-Meteo forecast API, no key needed. Just set
  `HOME_LAT` / `HOME_LON` (defaults to Indore).
- `app/calendar_api.py` — Google Calendar v3 over plain REST, using a shared
  OAuth refresh-token helper (`app/google_auth.py`) so we don't need the full
  `google-api-python-client` dependency.

### Getting Google OAuth credentials (used by both Calendar and Sheets)
1. Go to Google Cloud Console → create a project → enable **Google Calendar
   API** and **Google Sheets API**.
2. Create an OAuth 2.0 Client ID of type **Desktop app** → note the
   `client_id` / `client_secret`.
3. Run through the OAuth consent flow once locally (any short Python script
   using `google-auth-oauthlib` works) to get a **refresh token** with scopes
   `https://www.googleapis.com/auth/calendar` and
   `https://www.googleapis.com/auth/spreadsheets`.
4. Put `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REFRESH_TOKEN` into
   Render's env vars. This refresh token doesn't expire under normal use, so
   this is a one-time setup.

## 5. Long-term task marker (requirement 5)
Start any message with `\longtermtask` (configurable via `LONG_TERM_MARKER`)
and Shadow stores it straight into Cloudflare D1 with no confirmation
question. Otherwise, if the task *looks* recurring/standing, Shadow asks
"long-term me rakhna hai kya? (yes/no)" before storing it — see
`tasks.maybe_create_task()` and `brain._handle_yes_no_pending()`.

## 6. Weather-aware task scheduling (requirement 6)
If a task genuinely depends on outdoor weather (LLM-flagged
`weather_dependent: true` — e.g. washing the car, a walk, travel), Shadow:
1. Pulls the 7-day Open-Meteo forecast (`weather.get_week_forecast()`)
2. Picks the best day (lowest rain chance, no storms — `best_day_for_outdoor_task()`)
3. Creates a Google Calendar event for that slot
4. Schedules exactly one reminder (call **and** message) for that time
5. Tells you why it picked that day, in the reply

## 7. One announcement call per task (requirement 7)
`reminders.announce_task()` fires immediately when any task is created
(short-term, long-term, or weather-planned) — separate from the later
due-time reminder. Toggle via `FEATURES["task_announcement_call"]`.

## 8. Feedback → improvement loop (requirement 8)
`app/feedback.py` detects feedback-shaped messages, asks the LLM to analyse
sentiment/category/a concrete improvement action, and logs all of it to D1's
`feedback_log` table — a durable, growing backlog you (or a future Claude
session) can read back to prioritize real changes.

## 9. Morning greeting with a unique daily quote (requirement 9)
`reminders._morning_greeting()` runs on a cron trigger at `WAKE_TIME`
(default 07:00 IST). It asks the LLM for a fresh motivational line, checks it
against the last 60 days of used quotes (`db_turso.recent_quotes`) so it's
never repeated, calls you with the greeting, and messages today's task list.

## 10. End-of-day report (requirement 10)
`reminders._end_of_day_report()` runs at `EOD_REPORT_TIME` (default 22:30
IST): gathers today's task outcomes, asks the LLM to synthesize
done/not-done/tomorrow's-plan, sends it as a message + a short summary call,
then logs every line to the right Google Sheet tab and archives it into D1's
`task_history` (for growth analysis over time).

## 11. "How did the previous task go?" + report section (requirement 11)
Before finalizing a new task request, `brain._maybe_ask_about_previous_task()`
checks for a due-but-unconfirmed earlier task and asks about it. Your next
reply is analyzed (`llm.analyze_prev_status`) into a status + note, written
into `daily_report_draft` (Turso), and rolled into the two Google Sheets at
end of day — `GOOGLE_SHEETS_SHORT_TERM_ID` for day tasks,
`GOOGLE_SHEETS_LONG_TERM_ID` for standing/recurring ones.

**Note on scope:** this "ask before creating" flow currently only tracks
short-term (day-to-day) tasks, since that's what the requirement's examples
describe. Extending it to long-term/recurring tasks is a natural next step —
add a `latest_long_task_needing_status()` in `db_d1.py` and wire it the same
way `brain.py` already does for short-term ones.

---

## New environment variables to set on Render
See the updated `render.yaml` for the full list (all commented by section):
Turso, Cloudflare D1, Google OAuth + Sheets IDs, `HOME_LAT`/`HOME_LON`,
`WAKE_TIME`, `EOD_REPORT_TIME`. The old `DATABASE_URL` (Postgres) is gone —
Render's free Postgres add-on can be deleted from your dashboard.

### Turso
```
turso db create shadow-db
turso db show shadow-db --url        # -> TURSO_DATABASE_URL
turso db tokens create shadow-db     # -> TURSO_AUTH_TOKEN
```

### Cloudflare D1
```
wrangler d1 create shadow-longterm
# note the database_id -> CF_D1_DATABASE_ID
# CF_ACCOUNT_ID from your Cloudflare dashboard
# CF_API_TOKEN: create one with "D1: Edit" permission at
# dash.cloudflare.com/profile/api-tokens
```

## requirements.txt changes
Removed: `sqlalchemy`, `asyncpg` (no longer needed — no Postgres).
Added: `libsql-client` (Turso's official async Python client).

## What's unchanged
`stt.py`, `tts.py`, and the `orb-client/` folder are untouched — voice
transcription/synthesis and the local orb GUI didn't need to change for any
of these 11 requirements.
