import io
import edge_tts

VOICE = "en-IN-NeerjaNeural"  # change to hi-IN-MadhurNeural etc. if you want pure Hindi voice


async def synthesize(text: str) -> bytes:
    communicate = edge_tts.Communicate(text, VOICE)
    buf = io.BytesIO()
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            buf.write(chunk["data"])
    return buf.getvalue()
