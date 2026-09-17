from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse
from .config import TWILIO_VOICE
from . import db_turso, db_d1
from .reminders import start_scheduler
from . import telegram_bot, ws

app = FastAPI(title="Shadow Assistant")
app.include_router(telegram_bot.router)
app.include_router(ws.router)

_scheduler = None


@app.on_event("startup")
async def on_startup():
    global _scheduler
    await db_turso.init_turso()
    await db_d1.init_d1()
    _scheduler = start_scheduler()


@app.get("/")
async def health():
    return {"status": "Shadow is awake"}


@app.api_route("/twilio/say", methods=["GET", "POST"])
async def twilio_say(request: Request):
    """Twilio fetches this to know what to say on the reminder call."""
    text = request.query_params.get("t", "This is your reminder.")
    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response><Say voice="{TWILIO_VOICE}">{text}</Say></Response>"""
    return PlainTextResponse(content=twiml, media_type="application/xml")
