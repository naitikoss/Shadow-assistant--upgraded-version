import json
import httpx
from .config import GEMINI_API_KEYS, GROQ_API_KEYS
from .keypool import KeyPool

gemini_pool = KeyPool(GEMINI_API_KEYS)
groq_pool = KeyPool(GROQ_API_KEYS)

SYSTEM_PROMPT = (
    "You are Shadow, Nai's personal AI buddy. Be concise, warm, a little witty, "
    "and genuinely useful — like Jarvis, not a customer-support bot. "
    "Reply in the same mix of Hindi/English (Hinglish) the user writes in when they use Hinglish."
)


async def _call_gemini(messages: list[dict]) -> str | None:
    if not gemini_pool.available():
        return None
    contents = [{"role": "user" if m["role"] == "user" else "model", "parts": [{"text": m["content"]}]} for m in messages]
    payload = {"contents": contents, "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]}}

    for _ in range(len(gemini_pool.keys)):
        key = gemini_pool.next_key()
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={key}"
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                r = await client.post(url, json=payload)
                if r.status_code == 429:
                    gemini_pool.mark_rate_limited(key)
                    continue
                r.raise_for_status()
                data = r.json()
                return data["candidates"][0]["content"]["parts"][0]["text"]
        except Exception:
            continue
    return None


async def _call_groq(messages: list[dict]) -> str | None:
    if not groq_pool.available():
        return None
    url = "https://api.groq.com/openai/v1/chat/completions"
    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [{"role": "system", "content": SYSTEM_PROMPT}] + messages,
    }

    for _ in range(len(groq_pool.keys)):
        key = groq_pool.next_key()
        headers = {"Authorization": f"Bearer {key}"}
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                r = await client.post(url, json=payload, headers=headers)
                if r.status_code == 429:
                    groq_pool.mark_rate_limited(key)
                    continue
                r.raise_for_status()
                return r.json()["choices"][0]["message"]["content"]
        except Exception:
            continue
    return None


async def chat_reply(messages: list[dict]) -> str:
    """messages: [{"role": "user"/"assistant", "content": str}, ...]
    Tries every Gemini key first, then every Groq key, before giving up."""
    reply = await _call_gemini(messages)
    if reply is None:
        reply = await _call_groq(messages)
    return reply or "Thoda dikkat ho gayi mere brain (LLM) tak pahunchne mein — saari keys try kar li, sab fail ho gayi."


async def _ask_json(prompt: str, default: dict) -> dict:
    """Shared helper: ask the LLM for strict JSON, fall back to `default` on any failure."""
    raw = await _call_gemini([{"role": "user", "content": prompt}])
    if raw is None:
        raw = await _call_groq([{"role": "user", "content": prompt}])
    if not raw:
        return default
    try:
        cleaned = raw.strip().strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()
        return json.loads(cleaned)
    except Exception:
        return default


# =========================================================================
# Long-term memory classification (unchanged behaviour, kept here)
# =========================================================================
CLASSIFY_PROMPT = """You are a memory classifier for a personal assistant.
Given the latest user message, decide if it contains a durable fact worth remembering
long-term (preferences, recurring people/places, ongoing goals, standing instructions)
versus something purely transient (small talk, a one-off question, a fleeting mood).

Respond ONLY with strict JSON, no markdown, no preamble:
{{"is_long_term": true/false, "fact": "<the fact distilled into one short sentence, or empty string>", "category": "<one or two words>"}}

User message: "{message}"
"""


async def classify_for_memory(message: str) -> dict:
    prompt = CLASSIFY_PROMPT.format(message=message)
    return await _ask_json(prompt, {"is_long_term": False, "fact": "", "category": "general"})


# =========================================================================
# Task / reminder extraction — now also decides CALL vs MESSAGE section
# and which of the two sections' categories the request belongs to.
#
# CALL section  -> tasks of the day, reminders of leftover work, alarms for
#                  break/work, crosscheck
# MESSAGE section -> daily task description, work division, growth analysis,
#                     task updates, general queries
# =========================================================================
EXTRACT_PROMPT = """You extract reminder/task requests from a message for an assistant
that has two channels:

CALL section categories: "task" (a scheduled task/reminder for the day), "leftover"
(reminder about unfinished work), "break" (break-time alarm), "work_alarm" (get-back-
to-work alarm), "crosscheck" (a check-in call to verify something got done).

MESSAGE section categories: "task_description" (describing what a task involves),
"work_division" (splitting work across the day), "growth_analysis", "task_update"
(updating status of an existing task), "query" (a general question).

The user's current local datetime is {now_local} ({tz}), India. Any relative time
they mention ("kal 6 baje", "tomorrow evening", "in 2 hours") is in THIS local timezone.

Respond ONLY with strict JSON, no markdown:
{{
  "is_task": true/false,
  "title": "<short task title>",
  "due_at_local": "<ISO 8601 datetime WITHOUT timezone offset, in {tz}, or empty if not scheduled>",
  "section": "call" or "message",
  "category": "<one category from the matching section's list above>",
  "weather_dependent": true/false,
  "likely_long_term": true/false
}}

"weather_dependent" is true only if doing the task well genuinely depends on outdoor
weather (e.g. washing the car, a walk/run, travel, outdoor errands).
"likely_long_term" is true if this looks like a standing/recurring habit or goal
rather than a one-off day task.

Message: "{message}"
"""


async def extract_task(message: str, now_local_iso: str, tz: str) -> dict:
    prompt = EXTRACT_PROMPT.format(now_local=now_local_iso, tz=tz, message=message)
    return await _ask_json(prompt, {"is_task": False})


# =========================================================================
# Daily motivational quote (requirement 9) — always fresh, never repeated
# =========================================================================
QUOTE_PROMPT = """Generate ONE short, original, punchy motivational line (max 20 words)
to open Nai's morning, in Hinglish (Hindi+English mix), energetic but not cheesy.
It must be different from all of these already-used lines:
{used}

Respond ONLY with strict JSON: {{"quote": "<the line>"}}
"""


async def generate_daily_quote(used_quotes: list[str]) -> str:
    prompt = QUOTE_PROMPT.format(used="\n".join(f"- {q}" for q in used_quotes) or "(none yet)")
    result = await _ask_json(prompt, {"quote": "Uth ja Nai, aaj ka din tera hai! 🔥"})
    return result.get("quote") or "Uth ja Nai, aaj ka din tera hai! 🔥"


# =========================================================================
# Feedback analysis (requirement 8)
# =========================================================================
FEEDBACK_PROMPT = """The user (Nai) just gave feedback about this assistant (Shadow).
Feedback: "{feedback}"

Analyse it and respond ONLY with strict JSON:
{{
  "summary": "<one line summary of the complaint/praise>",
  "category": "<e.g. timing, tone, task-accuracy, memory, calls, other>",
  "improvement_action": "<one concrete, specific behaviour change Shadow should make going forward>",
  "sentiment": "positive" | "negative" | "neutral"
}}
"""


async def analyze_feedback(feedback_text: str) -> dict:
    prompt = FEEDBACK_PROMPT.format(feedback=feedback_text)
    return await _ask_json(prompt, {
        "summary": feedback_text, "category": "other",
        "improvement_action": "", "sentiment": "neutral",
    })


# =========================================================================
# Previous-task status analysis (requirement 11)
# =========================================================================
PREV_STATUS_PROMPT = """Nai was asked how a previous task went. The task was: "{task_title}".
Their reply: "{reply}"

Respond ONLY with strict JSON:
{{"status": "done" | "in_progress" | "skipped", "notes": "<short one-line summary of what they said>"}}
"""


async def analyze_prev_status(task_title: str, reply: str) -> dict:
    prompt = PREV_STATUS_PROMPT.format(task_title=task_title, reply=reply)
    return await _ask_json(prompt, {"status": "in_progress", "notes": reply})


# =========================================================================
# End-of-day report synthesis (requirement 10)
# =========================================================================
EOD_PROMPT = """Build Nai's end-of-day report from today's task log (JSON below).
Write it in warm, brief Hinglish, structured in three short parts.

Today's task log:
{log}

Respond ONLY with strict JSON:
{{
  "done_summary": "<what got done today, 1-3 lines>",
  "not_done_summary": "<what did not get done / is pending, 1-3 lines>",
  "tomorrow_plan": "<a short suggested plan for tomorrow, 1-3 lines>"
}}
"""


async def build_eod_report(task_log: list[dict]) -> dict:
    prompt = EOD_PROMPT.format(log=json.dumps(task_log, ensure_ascii=False))
    return await _ask_json(prompt, {
        "done_summary": "Aaj ka kuch data nahi mila.",
        "not_done_summary": "-",
        "tomorrow_plan": "Kal fresh start karte hain.",
    })
