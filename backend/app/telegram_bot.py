from fastapi import APIRouter, Request, HTTPException
from .config import TELEGRAM_OWNER_ID, TELEGRAM_WEBHOOK_SECRET
from .brain import handle_message
from .stt import transcribe
from .tts import synthesize
from . import telegram_client

router = APIRouter()


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
        audio_bytes = await telegram_client.download_file(message["voice"]["file_id"])
        user_text = await transcribe(audio_bytes, "voice.ogg")
    elif "text" in message:
        user_text = message["text"]

    if not user_text:
        await telegram_client.send_text("Samajh nahi aaya, phir se bolo/likho?", chat_id)
        return {"ok": True}

    reply = await handle_message("telegram", user_text)

    # If the user *spoke* to Shadow, reply with a spoken voice note back —
    # this is the "conversation after the ring" experience from ntfy_client.
    if was_voice:
        audio = await synthesize(reply)
        await telegram_client.send_voice(audio, chat_id)
    else:
        await telegram_client.send_text(reply, chat_id)

    return {"ok": True}
