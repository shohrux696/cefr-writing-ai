"""Countdown timers for FULL MOCK TEST tasks.

Deadlines are stored in the database (UTC). Each open task gets one asyncio
task that sleeps until the deadline and then calls the expiry handler.
The handler is registered by the mock test handler at startup, so this module
does not import Telegram code (no circular imports).

If the bot restarts, restore_timers() reschedules all open tasks from the
database. Tasks whose deadline already passed are expired immediately.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone

import database

logger = logging.getLogger(__name__)

# Called as handler(telegram_id, session_id, task_id) when a task time expires
ExpiryHandler = Callable[[int, int, int], Awaitable[None]]

_expiry_handler: ExpiryHandler | None = None
_timers: dict[int, asyncio.Task] = {}


def set_expiry_handler(handler: ExpiryHandler) -> None:
    """Register the function that runs when a mock task time expires."""
    global _expiry_handler
    _expiry_handler = handler


def parse_deadline(deadline_iso: str) -> datetime:
    """Parse an ISO deadline string from the database into an aware datetime."""
    value = datetime.fromisoformat(deadline_iso)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value


def seconds_left(deadline_iso: str) -> int:
    """Seconds remaining until the deadline. Never negative."""
    remaining = (parse_deadline(deadline_iso) - datetime.now(timezone.utc)).total_seconds()
    return max(0, int(remaining))


def format_seconds(seconds: int) -> str:
    """Format seconds as MM:SS, or H:MM:SS when an hour or more."""
    seconds = max(0, int(seconds))
    minutes, sec = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{sec:02d}"
    return f"{minutes:02d}:{sec:02d}"


def is_timer_active(task_id: int) -> bool:
    task = _timers.get(task_id)
    return task is not None and not task.done()


async def _run_timer(task_id: int, session_id: int, telegram_id: int, delay: float) -> None:
    current = asyncio.current_task()
    try:
        if delay > 0:
            await asyncio.sleep(delay)
    except asyncio.CancelledError:
        return
    finally:
        if _timers.get(task_id) is current:
            _timers.pop(task_id, None)

    handler = _expiry_handler
    if handler is None:
        logger.error("Mock timer expired for task %s, but no expiry handler is set", task_id)
        return

    try:
        await handler(telegram_id, session_id, task_id)
    except Exception:
        logger.exception("Expiry handler failed for mock task %s", task_id)


def cancel_timer(task_id: int) -> None:
    """Stop the timer of one mock task (for example after the student submits)."""
    task = _timers.pop(task_id, None)
    if task is not None and not task.done():
        task.cancel()


def cancel_all_timers() -> None:
    """Stop every running mock timer. Called on shutdown."""
    for task_id in list(_timers.keys()):
        cancel_timer(task_id)


def schedule_expiry(
    task_id: int,
    session_id: int,
    telegram_id: int,
    deadline_iso: str,
) -> None:
    """Start (or restart) the timer for one open mock task.

    Must be called from inside the running asyncio event loop.
    """
    cancel_timer(task_id)
    delay = seconds_left(deadline_iso)
    task = asyncio.create_task(
        _run_timer(task_id, session_id, telegram_id, float(delay)),
        name=f"mock-timer-{task_id}",
    )
    _timers[task_id] = task
    logger.info("Mock task %s timer scheduled in %s seconds", task_id, delay)


async def restore_timers() -> int:
    """Reschedule timers for all open mock tasks after a bot restart.

    Returns the number of restored timers.
    """
    rows = await database.list_open_mock_tasks()
    restored = 0
    for row in rows:
        if not row["deadline_at"]:
            continue
        schedule_expiry(
            task_id=int(row["task_id"]),
            session_id=int(row["session_id"]),
            telegram_id=int(row["telegram_id"]),
            deadline_iso=row["deadline_at"],
        )
        restored += 1
    if restored:
        logger.info("Restored %d mock task timer(s) after startup", restored)
    return restored
