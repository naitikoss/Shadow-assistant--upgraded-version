import httpx
from .llm import groq_pool


async def transcribe(audio_bytes: bytes, filename: str = "audio.ogg") -> str:
    if not groq_pool.available():
        return ""
    url = "https://api.groq.com/openai/v1/audio/transcriptions"
    data = {"model": "whisper-large-v3-turbo"}

    for _ in range(len(groq_pool.keys)):
        key = groq_pool.next_key()
        headers = {"Authorization": f"Bearer {key}"}
        files = {"file": (filename, audio_bytes)}
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                r = await client.post(url, headers=headers, files=files, data=data)
                if r.status_code == 429:
                    groq_pool.mark_rate_limited(key)
                    continue
                r.raise_for_status()
                return r.json().get("text", "")
        except Exception:
            continue
    return ""