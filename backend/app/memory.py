from . import db_turso, db_d1, llm


async def save_turn(role: str, channel: str, content: str):
    await db_turso.save_turn(role, channel, content)


async def recent_context(limit: int = 20) -> list[dict]:
    return await db_turso.recent_context(limit)


async def long_term_facts(limit: int = 50) -> list[str]:
    return await db_d1.all_facts(limit)


async def maybe_queue_for_long_term(user_message: str) -> dict | None:
    """Ask the LLM if this message has a durable fact. If yes, queue it for a
    one-time yes/no confirmation instead of writing straight to long-term memory."""
    verdict = await llm.classify_for_memory(user_message)
    if verdict.get("is_long_term") and verdict.get("fact"):
        confirmation_id = await db_turso.queue_confirmation(
            "memory", {"fact": verdict["fact"], "category": verdict.get("category", "general")}
        )
        return {"id": confirmation_id, "fact": verdict["fact"], "category": verdict.get("category", "general")}
    return None


async def resolve_pending_memory(confirmation_id: int, payload: dict, accepted: bool):
    await db_turso.resolve_confirmation(confirmation_id)
    if accepted:
        await db_d1.add_fact(payload["fact"], payload.get("category", "general"))
