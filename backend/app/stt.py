import httpx
from .config import GROQ_API_KEY


async def transcribe(audio_bytes: bytes, filename: str = "audio.ogg") -> str:
    if not GROQ_API_KEY:
        return ""
    url = "https://api.groq.com/openai/v1/audio/transcriptions"
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}"}
    files = {"file": (filename, audio_bytes)}
    data = {"model": "whisper-large-v3-turbo"}
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(url, headers=headers, files=files, data=data)
        r.raise_for_status()
        return r.json().get("text", "")
