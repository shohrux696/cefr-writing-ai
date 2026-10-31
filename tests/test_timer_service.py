"""Tests for services/timer_service.py"""

import asyncio
from datetime import datetime, timedelta, timezone

from services import timer_service


def test_format_seconds_minutes():
    assert timer_service.format_seconds(65) == "01:05"
    assert timer_service.format_seconds(0) == "00:00"


def test_format_seconds_hours():
    assert timer_service.format_seconds(3725) == "1:02:05"


def test_format_seconds_negative_is_zero():
    assert timer_service.format_seconds(-10) == "00:00"


def test_seconds_left_past_deadline_is_zero():
    past = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    assert timer_service.seconds_left(past) == 0


def test_seconds_left_future_is_positive():
    future = (datetime.now(timezone.utc) + timedelta(minutes=2)).isoformat()
    left = timer_service.seconds_left(future)
    assert 110 <= left <= 120


def test_parse_deadline_without_timezone_is_utc():
    value = timer_service.parse_deadline("2030-01-01T10:00:00")
    assert value.tzinfo is not None


def test_expired_timer_calls_handler():
    calls: list[tuple[int, int, int]] = []

    async def handler(telegram_id: int, session_id: int, task_id: int) -> None:
        calls.append((telegram_id, session_id, task_id))

    async def scenario() -> None:
        timer_service.set_expiry_handler(handler)
        past = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        timer_service.schedule_expiry(
            task_id=7, session_id=3, telegram_id=99, deadline_iso=past
        )
        await asyncio.sleep(0.1)

    asyncio.run(scenario())
    assert calls == [(99, 3, 7)]


def test_cancelled_timer_does_not_call_handler():
    calls: list[int] = []

    async def handler(telegram_id: int, session_id: int, task_id: int) -> None:
        calls.append(task_id)

    async def scenario() -> None:
        timer_service.set_expiry_handler(handler)
        future = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()
        timer_service.schedule_expiry(
            task_id=8, session_id=1, telegram_id=5, deadline_iso=future
        )
        assert timer_service.is_timer_active(8) is True
        timer_service.cancel_timer(8)
        await asyncio.sleep(0.05)
        assert timer_service.is_timer_active(8) is False

    asyncio.run(scenario())
    assert calls == []
