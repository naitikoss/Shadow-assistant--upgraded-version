import os

# =========================================================================
# FEATURE FLAGS — flip these to switch behaviour on/off without touching
# the rest of the codebase. This is the main "future improvement ready"
# hook: new features should land behind a flag here first.
# =========================================================================
FEATURES = {
    "weather_aware_tasks": True,     # requirement 6
    "task_announcement_call": True,  # requirement 7
    "morning_greeting": True,        # requirement 9
    "eod_report": True,              # requirement 10
    "ask_previous_task": True,       # requirement 11
    "feedback_learning": True,       # requirement 8
    "google_calendar": True,
    "google_sheets_reports": True,
    "use_ntfy_calls": True,          # "call section" -> ntfy ring + Telegram voice note (free).
                                      # Set False to fall back to Twilio (needs the TWILIO_* vars).
}

# =========================================================================
# Databases
# short-term (Turso / libSQL) -> conversation memory, day-to-day tasks,
#   reminders, alarms, anything that does NOT need to survive forever.
# long-term (Cloudflare D1)  -> durable facts, standing/recurring tasks,
#   task history for growth analysis, feedback log.
# =========================================================================
TURSO_DATABASE_URL = os.getenv("TURSO_DATABASE_URL", "")       # e.g. libsql://shadow-db-xxx.turso.io
TURSO_AUTH_TOKEN = os.getenv("TURSO_AUTH_TOKEN", "")

CF_ACCOUNT_ID = os.getenv("CF_ACCOUNT_ID", "")
CF_D1_DATABASE_ID = os.getenv("CF_D1_DATABASE_ID", "")
CF_API_TOKEN = os.getenv("CF_API_TOKEN", "")                   # token with D1:Edit permission

# --- LLM providers (multi-provider, multi-key rotation) ---
GEMINI_API_KEYS = [k for k in os.getenv("GEMINI_API_KEYS", os.getenv("GEMINI_API_KEY", "")).split(",") if k.strip()]
GROQ_API_KEYS = [k for k in os.getenv("GROQ_API_KEYS", os.getenv("GROQ_API_KEY", "")).split(",") if k.strip()]

# --- Telegram ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_WEBHOOK_SECRET = os.getenv("TELEGRAM_WEBHOOK_SECRET", "change-me")
TELEGRAM_OWNER_ID = int(os.getenv("TELEGRAM_OWNER_ID", "0"))

# --- Twilio (legacy/optional — only used if NTFY_TOPIC is not set) ---
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_FROM_NUMBER = os.getenv("TWILIO_FROM_NUMBER", "")
TWILIO_CALL_TO_NUMBER = os.getenv("TWILIO_CALL_TO_NUMBER", "")
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "https://your-app.onrender.com")
TWILIO_VOICE = os.getenv("TWILIO_VOICE", "Polly.Aditi")

# --- ntfy.sh (free push-notification "ring" + Telegram voice-note reply) ---
# This is now the default "call section" channel — see reminders.py / ntfy_client.py.
NTFY_SERVER = os.getenv("NTFY_SERVER", "https://ntfy.sh")
NTFY_TOPIC = os.getenv("NTFY_TOPIC", "")           # your private random topic name, e.g. shadow-nai-x7k29
TELEGRAM_BOT_USERNAME = os.getenv("TELEGRAM_BOT_USERNAME", "")  # without the @, e.g. shadow_nai_bot

# --- Orb client auth ---
ORB_CLIENT_TOKEN = os.getenv("ORB_CLIENT_TOKEN", "change-me")

# --- Memory behaviour ---
SHORT_TERM_MAX_MESSAGES = int(os.getenv("SHORT_TERM_MAX_MESSAGES", "40"))

# =========================================================================
# Timezone / locale — India only, using the stdlib (zoneinfo + datetime).
# See app/timeutils.py for the actual helpers built on top of this.
# =========================================================================
LOCAL_TIMEZONE = os.getenv("LOCAL_TIMEZONE", "Asia/Kolkata")
LOCALE_COUNTRY = "IN"

# Daily routine times (24h "HH:MM", interpreted in LOCAL_TIMEZONE)
WAKE_TIME = os.getenv("WAKE_TIME", "07:00")              # requirement 9 — morning call
EOD_REPORT_TIME = os.getenv("EOD_REPORT_TIME", "22:30")  # requirement 10 — end of day report

# --- Weather (Open-Meteo, no API key needed) ---
HOME_LAT = float(os.getenv("HOME_LAT", "22.7196"))   # defaults to Indore
HOME_LON = float(os.getenv("HOME_LON", "75.8577"))
WEATHER_TIMEZONE = LOCAL_TIMEZONE

# --- Google Calendar + Google Sheets (shared OAuth refresh-token flow) ---
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
GOOGLE_REFRESH_TOKEN = os.getenv("GOOGLE_REFRESH_TOKEN", "")
GOOGLE_CALENDAR_ID = os.getenv("GOOGLE_CALENDAR_ID", "primary")

# Two tabs/spreadsheets for the report section (requirement 11)
GOOGLE_SHEETS_SHORT_TERM_ID = os.getenv("GOOGLE_SHEETS_SHORT_TERM_ID", "")
GOOGLE_SHEETS_LONG_TERM_ID = os.getenv("GOOGLE_SHEETS_LONG_TERM_ID", "")
GOOGLE_SHEETS_SHORT_TERM_RANGE = os.getenv("GOOGLE_SHEETS_SHORT_TERM_RANGE", "ShortTerm!A:F")
GOOGLE_SHEETS_LONG_TERM_RANGE = os.getenv("GOOGLE_SHEETS_LONG_TERM_RANGE", "LongTerm!A:F")

# --- Long-term task marker (requirement 5) ---
# Type this literally in front of any task text and Shadow stores it
# straight into long-term (D1) without asking for confirmation.
LONG_TERM_MARKER = os.getenv("LONG_TERM_MARKER", "\\longtermtask")
