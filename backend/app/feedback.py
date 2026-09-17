"""
Feedback handling (requirement 8): whatever feedback Nai gives gets analysed
and logged to long-term storage (D1) so it accumulates into a real
improvement backlog over time, instead of being forgotten after the reply.
"""
from . import llm, db_d1

_TRIGGER_WORDS = (
    "feedback", "improve", "sudhaar", "behtar karo", "galti", "mistake",
    "you should", "next time", "please change", "stop doing", "don't do",
)


def looks_like_feedback(text: str) -> bool:
    lowered = text.lower()
    return any(word in lowered for word in _TRIGGER_WORDS)


async def handle_feedback(text: str) -> str:
    analysis = await llm.analyze_feedback(text)
    improvement = analysis.get("improvement_action", "")
    await db_d1.log_feedback(text, analysis, improvement)

    ack = "Noted 👍"
    if analysis.get("sentiment") == "negative":
        ack = "Samajh gaya, galti thi — yeh yaad rakh liya taaki agli baar behtar karu."
    elif analysis.get("sentiment") == "positive":
        ack = "Shukriya! Yeh wala approach yaad rakh liya."
    if improvement:
        ack += f"\n(Improvement noted: {improvement})"
    return ack
