"""Tests for database.py. Each test uses its own temporary SQLite file."""

import asyncio

import database
from config import SOURCE_MOCK, SOURCE_SINGLE


def test_user_upsert_and_stats(temp_db):
    async def scenario():
        await database.upsert_user(1001, "ali", "Ali", None)
        await database.upsert_user(1001, "ali2", "Ali", "K")
        submission_id = await database.create_submission(
            telegram_id=1001,
            task_type="task_11",
            original_text="Hi Ali, I went to Samarkand.",
            word_count=6,
            source=SOURCE_SINGLE,
        )
        await database.save_evaluation(
            submission_id=submission_id,
            estimated_cefr="B1",
            overall_score=70,
            result={"estimated_cefr_level": "B1", "overall_score": 70},
        )
        return await database.get_user_stats(1001)

    stats = asyncio.run(scenario())
    assert stats["total"] == 1
    assert stats["average_score"] == 70.0
    assert stats["latest_cefr"] == "B1"


def test_history_returns_latest_first(temp_db):
    async def scenario():
        await database.upsert_user(2001, None, "Dilnoza", None)
        first = await database.create_submission(2001, "task_11", "one two three four five", 5)
        second = await database.create_submission(2001, "task_2", "one two three four five", 5)
        return first, second, await database.get_user_history(2001)

    first, second, rows = asyncio.run(scenario())
    assert [row["id"] for row in rows] == [second, first]


def test_submission_detail_is_private_to_owner(temp_db):
    async def scenario():
        await database.upsert_user(3001, None, "A", None)
        await database.upsert_user(3002, None, "B", None)
        submission_id = await database.create_submission(3001, "task_12", "text here now", 3)
        own = await database.get_submission_detail(submission_id, 3001)
        other = await database.get_submission_detail(submission_id, 3002)
        return own, other

    own, other = asyncio.run(scenario())
    assert own is not None
    assert other is None


def test_invalid_source_is_rejected(temp_db):
    async def scenario():
        await database.upsert_user(4001, None, "C", None)
        await database.create_submission(4001, "task_2", "text", 1, source="bogus")

    try:
        asyncio.run(scenario())
    except ValueError:
        return
    raise AssertionError("ValueError was expected")


def test_settings_default_and_override(temp_db):
    async def scenario():
        enabled_default = await database.is_task_enabled("task_2")
        minutes_default = await database.get_task_minutes("task_2")
        await database.set_task_enabled("task_2", False)
        await database.set_task_minutes("task_2", 25)
        return (
            enabled_default,
            await database.is_task_enabled("task_2"),
            minutes_default,
            await database.get_task_minutes("task_2"),
        )

    enabled_default, enabled_after, minutes_default, minutes_after = asyncio.run(scenario())
    assert enabled_default is True
    assert enabled_after is False
    assert minutes_default == 40
    assert minutes_after == 25


def test_mock_session_flow(temp_db):
    async def scenario():
        await database.upsert_user(5001, None, "D", None)
        session_id = await database.create_mock_session(5001, ["task_11", "task_12"])

        first = await database.open_next_mock_task(session_id)
        assert first is not None
        assert first["task_type"] == "task_11"

        submitted = await database.submit_mock_answer(
            task_id=first["id"],
            session_id=session_id,
            task_type="task_11",
            answer_text="Hi Ali, how are you doing today my friend",
            word_count=8,
        )
        submitted_again = await database.submit_mock_answer(
            task_id=first["id"],
            session_id=session_id,
            task_type="task_11",
            answer_text="changed answer",
            word_count=2,
        )

        second = await database.open_next_mock_task(session_id)
        third = await database.open_next_mock_task(session_id)
        await database.finish_mock_session(session_id)
        session = await database.get_mock_session(session_id)
        return submitted, submitted_again, second, third, session

    submitted, submitted_again, second, third, session = asyncio.run(scenario())
    assert submitted is True
    assert submitted_again is False
    assert second is not None and second["task_type"] == "task_12"
    assert third is None
    assert session["status"] == "finished"


def test_expire_only_open_task(temp_db):
    async def scenario():
        await database.upsert_user(6001, None, "E", None)
        session_id = await database.create_mock_session(6001, ["task_2"])
        opened = await database.open_next_mock_task(session_id)
        expired_first = await database.expire_mock_task(opened["id"])
        expired_second = await database.expire_mock_task(opened["id"])
        return expired_first, expired_second

    expired_first, expired_second = asyncio.run(scenario())
    assert expired_first is True
    assert expired_second is False


def test_mock_submission_source_is_saved(temp_db):
    async def scenario():
        await database.upsert_user(7001, None, "F", None)
        session_id = await database.create_mock_session(7001, ["task_2"])
        submission_id = await database.create_submission(
            7001, "task_2", "some long enough text here", 5,
            source=SOURCE_MOCK, mock_session_id=session_id,
        )
        return await database.get_submission_detail(submission_id, 7001)

    detail = asyncio.run(scenario())
    assert detail["source"] == SOURCE_MOCK
