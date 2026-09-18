"""
Shared Telegram Bot API senders. Split out of telegram_bot.py so that
reminders.py (the scheduler — morning greeting, due-task alerts, EOD report,
task announcements) can push messages/voice notes proactively, not just as
a reply inside the webhook handler.
"""
import httpx
from .config import TELEGRAM_BOT_TOKEN, TELEGRAM_OWNER_ID

API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"


async def download_file(file_id: str) -> bytes:
    async with httpx.AsyncClient(timeout=30) as client:
        info = await client.get(f"{API}/getFile", params={"file_id": file_id})
        path = info.json()["result"]["file_path"]
        file_resp = await client.get(f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{path}")
        return file_resp.content


async def send_text(text: str, chat_id: int | None = None):
    chat_id = chat_id or TELEGRAM_OWNER_ID
    if not TELEGRAM_BOT_TOKEN or not chat_id:
        return
    async with httpx.AsyncClient(timeout=15) as client:
        await client.post(f"{API}/sendMessage", json={"chat_id": chat_id, "text": text})


async def send_voice(audio_bytes: bytes, chat_id: int | None = None, caption: str = ""):
    chat_id = chat_id or TELEGRAM_OWNER_ID
    if not TELEGRAM_BOT_TOKEN or not chat_id:
        return
    async with httpx.AsyncClient(timeout=30) as client:
        files = {"voice": ("reply.mp3", audio_bytes, "audio/mpeg")}
        data = {"chat_id": chat_id}
        if caption:
            data["caption"] = caption
        await client.post(f"{API}/sendVoice", data=data, files=files)
