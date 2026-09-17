from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from .models import ShortTermMemory, LongTermMemory, PendingMemory
from .llm import classify_for_memory
from .config import SHORT_TERM_MAX_MESSAGES


async def save_turn(session: AsyncSession, role: str, channel: str, content: str):
    session.add(ShortTermMemory(role=role, channel=channel, content=content))
    await session.commit()
    # prune short-term to the last N entries so it stays cheap
    result = await session.execute(select(ShortTermMemory.id).order_by(ShortTermMemory.id.desc()))
    ids = [row[0] for row in result.all()]
    if len(ids) > SHORT_TERM_MAX_MESSAGES:
        stale_ids = ids[SHORT_TERM_MAX_MESSAGES:]
        await session.execute(delete(ShortTermMemory).where(ShortTermMemory.id.in_(stale_ids)))
        await session.commit()


async def recent_context(session: AsyncSession, limit: int = 20) -> list[dict]:
    result = await session.execute(
        select(ShortTermMemory).order_by(ShortTermMemory.id.desc()).limit(limit)
    )
    rows = list(reversed(result.scalars().all()))
    return [{"role": r.role, "content": r.content} for r in rows]


async def long_term_facts(session: AsyncSession, limit: int = 50) -> list[str]:
    result = await session.execute(select(LongTermMemory.fact).order_by(LongTermMemory.id.desc()).limit(limit))
    return [row[0] for row in result.all()]


async def maybe_queue_for_long_term(session: AsyncSession, user_message: str) -> PendingMemory | None:
    """Ask the LLM if this message has a durable fact. If yes, queue it for a one-time
    yes/no confirmation instead of writing straight to long-term memory."""
    verdict = await classify_for_memory(user_message)
    if verdict.get("is_long_term") and verdict.get("fact"):
        pending = PendingMemory(fact=verdict["fact"], category=verdict.get("category", "general"))
        session.add(pending)
        await session.commit()
        await session.refresh(pending)
        return pending
    return None


async def resolve_pending(session: AsyncSession, pending_id: int, accepted: bool):
    pending = await session.get(PendingMemory, pending_id)
    if not pending or pending.resolved:
        return
    pending.resolved = True
    if accepted:
        session.add(LongTermMemory(fact=pending.fact, category=pending.category))
    await session.commit()
