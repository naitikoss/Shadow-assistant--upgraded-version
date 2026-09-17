import httpx
from fastapi import APIRouter, Request, HTTPException
from .config import TELEGRAM_BOT_TOKEN, TELEGRAM_OWNER_ID, TELEGRAM_WEBHOOK_SECRET
from .database import SessionLocal
from .brain import handle_message
from .stt import transcribe
from .tts import synthesize

router = APIRouter()
API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"


async def _download_file(file_id: str) -> bytes:
    async with httpx.AsyncClient(timeout=30) as client:
        info = await client.get(f"{API}/getFile", params={"file_id": file_id})
        path = info.json()["result"]["file_path"]
        file_resp = await client.get(f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{path}")
        return file_resp.content


async def _send_text(chat_id: int, text: str):
    async with httpx.AsyncClient(timeout=15) as client:
        await client.post(f"{API}/sendMessage", json={"chat_id": chat_id, "text": text})


async def _send_voice(chat_id: int, audio_bytes: bytes):
    async with httpx.AsyncClient(timeout=30) as client:
        files = {"voice": ("reply.mp3", audio_bytes, "audio/mpeg")}
        await client.post(f"{API}/sendVoice", data={"chat_id": chat_id}, files=files)


@router.post("/telegram/webhook/{secret}")
async def telegram_webhook(secret: str, request: Request):
    if secret != TELEGRAM_WEBHOOK_SECRET:
        raise HTTPException(status_code=403, detail="bad secret")
    update = await request.json()
    message = update.get("message")
    if not message:
        return {"ok": True}

    chat_id = message["chat"]["id"]
    if TELEGRAM_OWNER_ID and chat_id != TELEGRAM_OWNER_ID:
        return {"ok": True}  # ignore anyone who isn't you

    user_text = None
    was_voice = False

    if "voice" in message:
        was_voice = True
        audio_bytes = await _download_file(message["voice"]["file_id"])
        user_text = await transcribe(audio_bytes, "voice.ogg")
    elif "text" in message:
        user_text = message["text"]

    if not user_text:
        await _send_text(chat_id, "Samajh nahi aaya, phir se bolo/likho?")
        return {"ok": True}

    async with SessionLocal() as session:
        reply = await handle_message(session, "telegram", user_text)

    if was_voice:
        audio = await synthesize(reply)
        await _send_voice(chat_id, audio)
    else:
        await _send_text(chat_id, reply)

    return {"ok": True}
