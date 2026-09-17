from . import memory, llm, db_turso, tasks, feedback, reminders, timeutils
from .config import FEATURES

YES_WORDS = {"yes", "haan", "ha", "y", "yep", "sahi", "ok", "theek", "thik"}
NO_WORDS = {"no", "nahi", "nah", "n", "mat"}


def _is_yes_no(text: str) -> bool:
    return text.strip().lower() in YES_WORDS or text.strip().lower() in NO_WORDS


async def _handle_yes_no_pending(text: str) -> str | None:
    """Resolves a pending 'memory' or 'confirm_long_term' yes/no question, if any
    is waiting and the incoming message actually looks like an answer."""
    if not _is_yes_no(text):
        return None
    accepted = text.strip().lower() in YES_WORDS

    pending = await db_turso.latest_unresolved("confirm_long_term")
    if pending:
        await db_turso.resolve_confirmation(pending["id"])
        await tasks.resolve_long_term_confirmation(accepted, pending["payload"])
        if accepted:
            due_local = timeutils.utc_naive_to_local(
                timeutils.parse_local_iso(pending["payload"]["due_at_utc"])
            )
            await reminders.announce_task(pending["payload"]["title"], due_local, pending["payload"]["section"])
            return "Theek hai, isse long-term me daal diya 👍"
        return "Thik hai, short-term me hi rakh diya."

    pending = await db_turso.latest_unresolved("memory")
    if pending:
        await memory.resolve_pending_memory(pending["id"], pending["payload"], accepted)
        return "Yaad rakh liya 👍" if accepted else "Theek hai, nahi rakhta yaad."

    return None


async def _handle_prev_task_status_pending(text: str) -> str | None:
    """If Shadow was waiting on 'pichla task kaisa raha?', treat this message as
    the answer, analyse it, and log it into today's report (requirement 11)."""
    pending = await db_turso.latest_unresolved("prev_task_status")
    if not pending:
        return None
    payload = pending["payload"]
    analysis = await llm.analyze_prev_status(payload["title"], text)
    await db_turso.resolve_confirmation(pending["id"])
    await db_turso.set_task_status(payload["task_id"], analysis["status"], analysis.get("notes", ""))
    await db_turso.add_report_line(
        timeutils.today_str(), payload["title"], analysis["status"], analysis.get("notes", ""), retention="short"
    )
    verdicts = {"done": "Badhiya, mark kar diya complete ✅", "skipped": "Thik hai, skip mark kar diya.",
                "in_progress": "Samajh gaya, abhi in-progress rakha hai."}
    return verdicts.get(analysis["status"], "Update note kar liya.")


async def _maybe_ask_about_previous_task() -> str | None:
    """requirement 11: before getting into a new task conversation, check whether
    an earlier task never got a status update, and if so ask about it now."""
    if not FEATURES.get("ask_previous_task"):
        return None
    stale = await db_turso.latest_task_needing_status()
    if not stale:
        return None
    await db_turso.queue_confirmation("prev_task_status", {"task_id": stale["id"], "title": stale["title"]})
    return f"Ek second — pichla task \"{stale['title']}\" ka kya hua, complete hua ya abhi baaki hai?"


async def _handle_task_creation(text: str, forced_long_term: bool) -> str:
    result = await tasks.maybe_create_task(text, forced_long_term)
    if result is None:
        return ""

    kind = result["kind"]
    if kind == "short_task":
        t = result["task"]
        msg = f"\n\nTask set: \"{t['title']}\" — {t['section']} reminder at {timeutils.human(t['due_local'])}."
        if FEATURES.get("task_announcement_call"):
            await reminders.announce_task(t["title"], t["due_local"], t["section"])
        return msg

    if kind == "long_task":
        msg = f"\n\nLong-term task save kar diya: \"{result['title']}\" ({timeutils.human(result['due_local'])})."
        if FEATURES.get("task_announcement_call"):
            await reminders.announce_task(result["title"], result["due_local"], "both")
        return msg

    if kind == "needs_long_term_confirmation":
        return (f"\n\nYe '{result['title']}' recurring/standing task jaisa lag raha hai — "
                f"isse long-term me rakhna hai? (yes/no). Agar hamesha long-term rakhwana ho to "
                f"agli baar message ke shuru me `\\longtermtask` likh dena.")

    if kind == "weather_task":
        msg = (f"\n\n{result['reason']} Maine '{result['title']}' {timeutils.human(result['due_local'])} "
               f"pe schedule kar diya hai aur ek reminder (call + message) us waqt ke liye set kar diya hai.")
        if FEATURES.get("task_announcement_call"):
            await reminders.announce_task(result["title"], result["due_local"], "both")
        return msg

    return ""


async def handle_message(channel: str, text: str) -> str:
    """Runs the full pipeline for one incoming user message and returns Shadow's reply text."""

    # 0. requirement 5 — strip the forced long-term marker up front
    text, forced_long_term = tasks.strip_long_term_marker(text)

    # 1. is this a yes/no answer to a pending confirmation?
    answer = await _handle_yes_no_pending(text)
    if answer is not None:
        return answer

    # 1b. is this the answer to "how did the previous task go?"
    answer = await _handle_prev_task_status_pending(text)
    if answer is not None:
        return answer

    # 2. save the user's turn into short-term memory
    await memory.save_turn("user", channel, text)

    # 3. feedback gets routed straight to the learning loop (requirement 8)
    if FEATURES.get("feedback_learning") and feedback.looks_like_feedback(text):
        reply = await feedback.handle_feedback(text)
        await memory.save_turn("assistant", channel, reply)
        return reply

    # 4. before diving into a new task, check if an old one still needs a status update
    prev_prompt = await _maybe_ask_about_previous_task()

    # 5. did they just ask for a task/reminder?
    task_note = await _handle_task_creation(text, forced_long_term)

    # 6. build context: recent short-term turns + relevant long-term facts
    context = await memory.recent_context(limit=20)
    facts = await memory.long_term_facts()
    system_context = ""
    if facts:
        system_context = "Known long-term facts about Nai:\n- " + "\n- ".join(facts)
    messages = ([{"role": "user", "content": system_context}] if system_context else []) + context

    reply = await llm.chat_reply(messages)

    if prev_prompt:
        reply = f"{prev_prompt}\n\n{reply}"
    if task_note:
        reply += task_note

    # 7. does this message contain a durable fact worth remembering? queue a confirm, don't write yet
    new_pending = await memory.maybe_queue_for_long_term(text)
    if new_pending:
        reply += f"\n\nEk cheez — \"{new_pending['fact']}\" ko main long-term yaad rakh lu? (yes/no)"

    await memory.save_turn("assistant", channel, reply)
    return reply
