import base64
import json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from .config import ORB_CLIENT_TOKEN
from .brain import handle_message
from .stt import transcribe
from .tts import synthesize

router = APIRouter()


@router.websocket("/ws/orb")
async def orb_socket(ws: WebSocket):
    await ws.accept()
    try:
        auth = await ws.receive_json()
        if auth.get("token") != ORB_CLIENT_TOKEN:
            await ws.close(code=4001)
            return

        while True:
            raw = await ws.receive_json()
            kind = raw.get("type")

            if kind == "text":
                user_text = raw["text"]
            elif kind == "audio":
                audio_bytes = base64.b64decode(raw["audio_b64"])
                user_text = await transcribe(audio_bytes, "orb.wav")
                if not user_text:
                    await ws.send_json({"type": "error", "message": "Sunai nahi diya, phir se try karo."})
                    continue
                await ws.send_json({"type": "transcript", "text": user_text})
            else:
                continue

            reply = await handle_message("orb", user_text)

            await ws.send_json({"type": "reply_text", "text": reply})

            audio = await synthesize(reply)
            await ws.send_json({"type": "reply_audio", "audio_b64": base64.b64encode(audio).decode()})

    except WebSocketDisconnect:
        pass
