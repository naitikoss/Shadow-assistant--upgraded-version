import os

# --- Database ---
# Render's managed Postgres gives a plain "postgresql://..." URL; SQLAlchemy's async
# engine needs the asyncpg driver prefix, so normalize it here.
_raw_db_url = os.getenv("DATABASE_URL", "postgresql+asyncpg://user:pass@localhost:5432/shadow")
if _raw_db_url.startswith("postgresql://"):
    _raw_db_url = _raw_db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
DATABASE_URL = _raw_db_url

# --- LLM providers (multi-provider, same pattern as chatbot6) ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

# --- Telegram ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_WEBHOOK_SECRET = os.getenv("TELEGRAM_WEBHOOK_SECRET", "change-me")
# your own telegram numeric user id, so the bot only listens to you
TELEGRAM_OWNER_ID = int(os.getenv("TELEGRAM_OWNER_ID", "0"))

# --- Twilio (voice call reminders) ---
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_FROM_NUMBER = os.getenv("TWILIO_FROM_NUMBER", "")
TWILIO_CALL_TO_NUMBER = os.getenv("TWILIO_CALL_TO_NUMBER", "")  # your phone number
# public base url of this backend on Render, used for Twilio's TwiML callback
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "https://your-app.onrender.com")

# --- Orb client auth ---
# shared secret the local orb GUI uses to authenticate its websocket connection
ORB_CLIENT_TOKEN = os.getenv("ORB_CLIENT_TOKEN", "change-me")

# --- Memory behaviour ---
SHORT_TERM_MAX_MESSAGES = int(os.getenv("SHORT_TERM_MAX_MESSAGES", "40"))
