"""
Shadow Orb — a small always-on-top floating ball that sits on your desktop.

Left click        -> start/stop recording your voice (sent to Shadow for STT)
Right click        -> type a text message instead
Drag                -> move it anywhere on screen
Double-click        -> quit

Talks to the cloud backend (Render) over a WebSocket, so all the "brain",
memory and LLM work happens server-side — this script is just eyes/ears/mouth.
"""

import asyncio
import base64
import json
import queue
import threading
import tkinter as tk
from tkinter import simpledialog

import numpy as np
import sounddevice as sd
import soundfile as sf
import websockets
import io
import simpleaudio as sa

# ---- CONFIG: fill these in ----
BACKEND_WS_URL = "wss://shadow-backend.onrender.com/ws/orb"   # apna Render URL, https ki jagah wss, http ki jagah ws
ORB_CLIENT_TOKEN = "517bcfba7001e6e3dc6166ee8ca2201f93d7b08968f8f2d5"
# --------------------------------

SAMPLE_RATE = 16000


class OrbApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.overrideredirect(True)          # no title bar
        self.root.attributes("-topmost", True)     # always on top
        self.root.attributes("-alpha", 0.92)
        self.root.geometry("90x90+80+80")
        try:
            self.root.wm_attributes("-transparentcolor", "black")
        except tk.TclError:
            pass  # not supported on all platforms

        self.canvas = tk.Canvas(root, width=90, height=90, bg="black", highlightthickness=0)
        self.canvas.pack()
        self.orb = self.canvas.create_oval(10, 10, 80, 80, fill="#3b82f6", outline="#93c5fd", width=3)
        self.status_label = tk.Label(root, text="", fg="white", bg="black", font=("Segoe UI", 7))
        self.status_label.place(relx=0.5, rely=1.0, anchor="s")

        self.canvas.bind("<Button-1>", self.toggle_recording)
        self.canvas.bind("<Button-3>", self.type_message)
        self.canvas.bind("<Double-Button-1>", lambda e: self.root.destroy())
        self.canvas.bind("<B1-Motion>", self.drag)

        self.recording = False
        self.audio_frames = []
        self.stream = None

        self.outbound_q: "queue.Queue" = queue.Queue()
        self.loop = asyncio.new_event_loop()
        threading.Thread(target=self._run_ws_loop, daemon=True).start()

    # ---------- dragging ----------
    def drag(self, event):
        x = self.root.winfo_pointerx() - 45
        y = self.root.winfo_pointery() - 45
        self.root.geometry(f"+{x}+{y}")

    # ---------- status ----------
    def set_status(self, text: str, color: str = "#3b82f6"):
        self.status_label.config(text=text)
        self.canvas.itemconfig(self.orb, fill=color)

    # ---------- voice recording ----------
    def toggle_recording(self, event=None):
        if not self.recording:
            self.recording = True
            self.audio_frames = []
            self.set_status("listening...", "#ef4444")
            self.stream = sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="float32",
                                          callback=self._audio_callback)
            self.stream.start()
        else:
            self.recording = False
            self.stream.stop()
            self.stream.close()
            self.set_status("thinking...", "#f59e0b")
            audio = np.concatenate(self.audio_frames, axis=0) if self.audio_frames else np.zeros((1,))
            buf = io.BytesIO()
            sf.write(buf, audio, SAMPLE_RATE, format="WAV")
            self.outbound_q.put({"type": "audio", "audio_b64": base64.b64encode(buf.getvalue()).decode()})

    def _audio_callback(self, indata, frames, time_info, status):
        self.audio_frames.append(indata.copy())

    # ---------- text input ----------
    def type_message(self, event=None):
        text = simpledialog.askstring("Shadow", "Type your message:")
        if text:
            self.set_status("thinking...", "#f59e0b")
            self.outbound_q.put({"type": "text", "text": text})

    # ---------- websocket loop (background thread) ----------
    def _run_ws_loop(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self._ws_main())

    async def _ws_main(self):
        while True:
            try:
                async with websockets.connect(BACKEND_WS_URL, max_size=20_000_000) as ws:
                    await ws.send(json.dumps({"token": ORB_CLIENT_TOKEN}))
                    self.root.after(0, self.set_status, "ready", "#22c55e")
                    await asyncio.gather(self._sender(ws), self._receiver(ws))
            except Exception:
                self.root.after(0, self.set_status, "offline", "#6b7280")
                await asyncio.sleep(5)

    async def _sender(self, ws):
        while True:
            try:
                msg = self.outbound_q.get_nowait()
                await ws.send(json.dumps(msg))
            except queue.Empty:
                await asyncio.sleep(0.1)

    async def _receiver(self, ws):
        async for raw in ws:
            data = json.loads(raw)
            kind = data.get("type")
            if kind == "transcript":
                self.root.after(0, self.set_status, f"you: {data['text'][:20]}", "#f59e0b")
            elif kind == "reply_text":
                self.root.after(0, self.set_status, data["text"][:24], "#22c55e")
            elif kind == "reply_audio":
                audio_bytes = base64.b64decode(data["audio_b64"])
                self._play_audio(audio_bytes)
            elif kind == "error":
                self.root.after(0, self.set_status, data["message"][:24], "#ef4444")

    def _play_audio(self, mp3_bytes: bytes):
        # edge-tts returns mp3; simpleaudio needs wav, so decode via soundfile
        try:
            data, sr = sf.read(io.BytesIO(mp3_bytes))
            pcm = (data * 32767).astype(np.int16)
            sa.play_buffer(pcm, 1 if pcm.ndim == 1 else pcm.shape[1], 2, sr)
        except Exception:
            pass  # playback failure shouldn't crash the orb


if __name__ == "__main__":
    root = tk.Tk()
    app = OrbApp(root)
    root.mainloop()
