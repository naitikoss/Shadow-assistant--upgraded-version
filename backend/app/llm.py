import json
import httpx
from .config import GEMINI_API_KEY, GROQ_API_KEY

SYSTEM_PROMPT = (
    "You are Shadow, Nai's personal AI buddy. Be concise, warm, a little witty, "
    "and genuinely useful — like Jarvis, not a customer-support bot. "
    "Reply in the same mix of Hindi/English (Hinglish) the user writes in when they use Hinglish."
)


async def _call_gemini(messages: list[dict]) -> str | None:
    if not GEMINI_API_KEY:
        return None
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
    contents = [{"role": "user" if m["role"] == "user" else "model", "parts": [{"text": m["content"]}]} for m in messages]
    payload = {"contents": contents, "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]}}
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(url, json=payload)
            r.raise_for_status()
            data = r.json()
            return data["candidates"][0]["content"]["parts"][0]["text"]
    except Exception:
        return None


async def _call_groq(messages: list[dict]) -> str | None:
    if not GROQ_API_KEY:
        return None
    url = "https://api.groq.com/openai/v1/chat/completions"
    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [{"role": "system", "content": SYSTEM_PROMPT}] + messages,
    }
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}"}
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(url, json=payload, headers=headers)
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]
    except Exception:
        return None


async def chat_reply(messages: list[dict]) -> str:
    """messages: [{"role": "user"/"assistant", "content": str}, ...]"""
    reply = await _call_gemini(messages)
    if reply is None:
        reply = await _call_groq(messages)
    return reply or "Thoda dikkat ho gayi mere brain (LLM) tak pahunchne mein — dono providers fail ho gaye."


CLASSIFY_PROMPT = """You are a memory classifier for a personal assistant.
Given the latest user message, decide if it contains a durable fact worth remembering
long-term (preferences, recurring people/places, ongoing goals, standing instructions)
versus something purely transient (small talk, a one-off question, a fleeting mood).

Respond ONLY with strict JSON, no markdown, no preamble:
{"is_long_term": true/false, "fact": "<the fact distilled into one short sentence, or empty string>", "category": "<one or two words>"}

User message: "{message}"
"""


async def classify_for_memory(message: str) -> dict:
    prompt = CLASSIFY_PROMPT.replace("{message}", message)
    raw = await _call_gemini([{"role": "user", "content": prompt}])
    if raw is None:
        raw = await _call_groq([{"role": "user", "content": prompt}])
    if not raw:
        return {"is_long_term": False, "fact": "", "category": "general"}
    try:
        cleaned = raw.strip().strip("`").replace("json\n", "").strip()
        parsed = json.loads(cleaned)
        return parsed
    except Exception:
        return {"is_long_term": False, "fact": "", "category": "general"}
