from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from .models import PendingMemory
from . import memory, llm
from .tasks import maybe_create_task

YES_WORDS = {"yes", "haan", "ha", "y", "yep", "sahi", "ok", "theek", "thik"}
NO_WORDS = {"no", "nahi", "nah", "n", "mat"}


async def _latest_unresolved_pending(session: AsyncSession) -> PendingMemory | None:
    result = await session.execute(
        select(PendingMemory).where(PendingMemory.resolved == False).order_by(PendingMemory.id.desc())  # noqa: E712
    )
    return result.scalars().first()


async def handle_message(session: AsyncSession, channel: str, text: str) -> str:
    """Runs the full pipeline for one incoming user message and returns Shadow's reply text."""

    # 1. is this a yes/no answer to a pending "remember this?" question?
    pending = await _latest_unresolved_pending(session)
    lowered = text.strip().lower()
    if pending and (lowered in YES_WORDS or lowered in NO_WORDS):
        accepted = lowered in YES_WORDS
        await memory.resolve_pending(session, pending.id, accepted)
        return "Yaad rakh liya 👍" if accepted else "Theek hai, nahi rakhta yaad."

    # 2. save the user's turn into short-term memory
    await memory.save_turn(session, "user", channel, text)

    # 3. did they just ask for a task/reminder?
    task = await maybe_create_task(session, text)

    # 4. build context: recent short-term turns + relevant long-term facts
    context = await memory.recent_context(session, limit=20)
    facts = await memory.long_term_facts(session)
    system_context = ""
    if facts:
        system_context = "Known long-term facts about Nai:\n- " + "\n- ".join(facts)
    messages = ([{"role": "user", "content": system_context}] if system_context else []) + context

    reply = await llm.chat_reply(messages)

    if task:
        reply += f"\n\n(Task set: \"{task.title}\" — {task.reminder_type.value} reminder at {task.due_at} UTC)"

    # 5. does this message contain a durable fact worth remembering? queue a confirm, don't write yet
    new_pending = await memory.maybe_queue_for_long_term(session, text)
    if new_pending:
        reply += f"\n\nEk cheez — \"{new_pending.fact}\" ko main long-term yaad rakh lu? (yes/no)"

    await memory.save_turn(session, "assistant", channel, reply)
    return reply
