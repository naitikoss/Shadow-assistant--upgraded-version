"""
ntfy.sh integration — the free replacement for Twilio phone calls.

ntfy can't place an actual VoIP/telephone call (no service that isn't paid
telephony can), but it *can* push an urgent, repeating, screen-waking
notification to your phone for free, forever, with no account and no key.
Tapping the notification deep-links straight into the Telegram bot chat,
where a spoken (TTS) voice note is already waiting — so the overall
"call section" experience becomes: phone rings/vibrates -> tap -> Shadow's
voice note is right there.

Setup: pick any private, hard-to-guess topic name (config.NTFY_TOPIC) and
subscribe to it in the ntfy app. That's the entire setup — see SETUP_NOTES.md.
"""
import httpx
from .config import NTFY_SERVER, NTFY_TOPIC, TELEGRAM_BOT_USERNAME


def _telegram_deep_link() -> str | None:
    if not TELEGRAM_BOT_USERNAME:
        return None
    return f"https://t.me/{TELEGRAM_BOT_USERNAME}"


async def ring(title: str, message: str, urgent: bool = True) -> bool:
    """Pushes an ntfy notification. Returns True if it was actually sent
    (i.e. NTFY_TOPIC is configured), False otherwise so callers can decide
    whether to fall back to something else."""
    if not NTFY_TOPIC:
        return False

    headers = {
        "Title": title,
        "Priority": "urgent" if urgent else "default",
        "Tags": "loudspeaker" if urgent else "bell",
    }
    link = _telegram_deep_link()
    if link:
        headers["Click"] = link
        headers["Actions"] = f"view, Open Shadow, {link}"

    url = f"{NTFY_SERVER.rstrip('/')}/{NTFY_TOPIC}"
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(url, headers=headers, content=message.encode("utf-8"))
        return r.status_code < 300
