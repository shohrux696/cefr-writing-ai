"""SQLite database layer. All functions are async and use aiosqlite."""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, AsyncIterator

import aiosqlite

from config import DATABASE_PATH, SOURCE_MOCK, SOURCE_SINGLE, TASKS

logger = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    telegram_id INTEGER PRIMARY KEY,
    username TEXT,
    first_name TEXT,
    last_name TEXT,
    registered_at TEXT NOT NULL,
    last_active_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS bot_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS mock_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER NOT NULL REFERENCES users(telegram_id),
    status TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT
);

CREATE TABLE IF NOT EXISTS submissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER NOT NULL REFERENCES users(telegram_id),
    task_type TEXT NOT NULL,
    original_text TEXT NOT NULL,
    word_count INTEGER NOT NULL,
    source TEXT NOT NULL,
    mock_session_id INTEGER REFERENCES mock_sessions(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS evaluations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    submission_id INTEGER NOT NULL UNIQUE REFERENCES submissions(id) ON DELETE CASCADE,
    estimated_cefr TEXT NOT NULL,
    overall_score INTEGER NOT NULL,
    result_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS mock_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL REFERENCES mock_sessions(id) ON DELETE CASCADE,
    task_type TEXT NOT NULL,
    position INTEGER NOT NULL,
    status TEXT NOT NULL,
    opened_at TEXT,
    deadline_at TEXT,
    closed_at TEXT,
    UNIQUE(session_id, task_type)
);

CREATE TABLE IF NOT EXISTS mock_answers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mock_task_id INTEGER NOT NULL UNIQUE REFERENCES mock_tasks(id) ON DELETE CASCADE,
    session_id INTEGER NOT NULL REFERENCES mock_sessions(id) ON DELETE CASCADE,
    task_type TEXT NOT NULL,
    answer_text TEXT NOT NULL,
    word_count INTEGER NOT NULL,
    submitted_at TEXT NOT NULL,
    submission_id INTEGER REFERENCES submissions(id) ON DELETE SET NULL
);
"""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat(timespec="seconds")


@asynccontextmanager
async def get_connection() -> AsyncIterator[aiosqlite.Connection]:
    """Open a connection, commit on success, roll back on error."""
    db = await aiosqlite.connect(DATABASE_PATH)
    db.row_factory = sqlite3.Row
    try:
        await db.execute("PRAGMA foreign_keys = ON")
        yield db
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    finally:
        await db.close()


async def init_db() -> None:
    """Create all tables if they do not exist."""
    directory = os.path.dirname(os.path.abspath(DATABASE_PATH))
    os.makedirs(directory, exist_ok=True)
    async with get_connection() as db:
        await db.executescript(SCHEMA)
    logger.info("Database initialised at %s", DATABASE_PATH)


# ---------------------------------------------------------------------------
# Settings (admin-configurable values)
# ---------------------------------------------------------------------------

async def _read_setting(db: aiosqlite.Connection, key: str) -> str | None:
    cursor = await db.execute("SELECT value FROM bot_settings WHERE key = ?", (key,))
    row = await cursor.fetchone()
    return row["value"] if row else None


async def get_setting(key: str) -> str | None:
    async with get_connection() as db:
        return await _read_setting(db, key)


async def set_setting(key: str, value: str) -> None:
    async with get_connection() as db:
        await db.execute(
            """
            INSERT INTO bot_settings (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, value),
        )


async def is_task_enabled(task_key: str) -> bool:
    value = await get_setting(f"task_enabled:{task_key}")
    return value != "0"


async def set_task_enabled(task_key: str, enabled: bool) -> None:
    await set_setting(f"task_enabled:{task_key}", "1" if enabled else "0")


async def _read_task_minutes(db: aiosqlite.Connection, task_key: str) -> int:
    raw = await _read_setting(db, f"task_minutes:{task_key}")
    if raw is None:
        return TASKS[task_key].default_minutes
    try:
        return int(raw)
    except ValueError:
        return TASKS[task_key].default_minutes


async def get_task_minutes(task_key: str) -> int:
    async with get_connection() as db:
        return await _read_task_minutes(db, task_key)


async def set_task_minutes(task_key: str, minutes: int) -> None:
    await set_setting(f"task_minutes:{task_key}", str(minutes))


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

async def upsert_user(
    telegram_id: int,
    username: str | None,
    first_name: str | None,
    last_name: str | None,
) -> None:
    now = _now_iso()
    async with get_connection() as db:
        await db.execute(
            """
            INSERT INTO users (telegram_id, username, first_name, last_name, registered_at, last_active_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(telegram_id) DO UPDATE SET
                username = excluded.username,
                first_name = excluded.first_name,
                last_name = excluded.last_name,
                last_active_at = excluded.last_active_at
            """,
            (telegram_id, username, first_name, last_name, now, now),
        )


# ---------------------------------------------------------------------------
# Submissions and evaluations
# ---------------------------------------------------------------------------

async def create_submission(
    telegram_id: int,
    task_type: str,
    original_text: str,
    word_count: int,
    source: str = SOURCE_SINGLE,
    mock_session_id: int | None = None,
) -> int:
    if source not in (SOURCE_SINGLE, SOURCE_MOCK):
        raise ValueError(f"Unknown submission source: {source}")
    async with get_connection() as db:
        cursor = await db.execute(
            """
            INSERT INTO submissions
                (telegram_id, task_type, original_text, word_count, source, mock_session_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (telegram_id, task_type, original_text, word_count, source, mock_session_id, _now_iso()),
        )
        return int(cursor.lastrowid)


async def save_evaluation(
    submission_id: int,
    estimated_cefr: str,
    overall_score: int,
    result: dict[str, Any],
) -> None:
    async with get_connection() as db:
        await db.execute(
            """
            INSERT INTO evaluations (submission_id, estimated_cefr, overall_score, result_json, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                submission_id,
                estimated_cefr,
                overall_score,
                json.dumps(result, ensure_ascii=False),
                _now_iso(),
            ),
        )


async def get_user_history(telegram_id: int, limit: int = 10) -> list[sqlite3.Row]:
    async with get_connection() as db:
        cursor = await db.execute(
            """
            SELECT s.id, s.task_type, s.word_count, s.source, s.created_at,
                   e.estimated_cefr, e.overall_score
            FROM submissions s
            LEFT JOIN evaluations e ON e.submission_id = s.id
            WHERE s.telegram_id = ?
            ORDER BY s.id DESC
            LIMIT ?
            """,
            (telegram_id, limit),
        )
        return list(await cursor.fetchall())


async def get_submission_detail(submission_id: int, telegram_id: int) -> sqlite3.Row | None:
    """Return one submission owned by telegram_id, with its evaluation."""
    async with get_connection() as db:
        cursor = await db.execute(
            """
            SELECT s.id, s.task_type, s.original_text, s.word_count, s.source, s.created_at,
                   e.estimated_cefr, e.overall_score, e.result_json
            FROM submissions s
            LEFT JOIN evaluations e ON e.submission_id = s.id
            WHERE s.id = ? AND s.telegram_id = ?
            """,
            (submission_id, telegram_id),
        )
        return await cursor.fetchone()


async def get_user_stats(telegram_id: int) -> dict[str, Any]:
    async with get_connection() as db:
        cursor = await db.execute(
            """
            SELECT COUNT(*) AS total, AVG(e.overall_score) AS avg_score
            FROM submissions s
            LEFT JOIN evaluations e ON e.submission_id = s.id
            WHERE s.telegram_id = ?
            """,
            (telegram_id,),
        )
        totals = await cursor.fetchone()

        cursor = await db.execute(
            """
            SELECT e.estimated_cefr
            FROM submissions s
            JOIN evaluations e ON e.submission_id = s.id
            WHERE s.telegram_id = ?
            ORDER BY s.id DESC
            LIMIT 1
            """,
            (telegram_id,),
        )
        latest = await cursor.fetchone()

    avg_score = totals["avg_score"]
    return {
        "total": totals["total"] or 0,
        "average_score": round(avg_score, 1) if avg_score is not None else None,
        "latest_cefr": latest["estimated_cefr"] if latest else None,
    }


async def _scalar(db: aiosqlite.Connection, sql: str, params: tuple = ()) -> Any:
    cursor = await db.execute(sql, params)
    row = await cursor.fetchone()
    return row[0] if row else None


async def get_bot_statistics() -> dict[str, Any]:
    week_ago = (_now() - timedelta(days=7)).isoformat(timespec="seconds")
    async with get_connection() as db:
        total_users = await _scalar(db, "SELECT COUNT(*) FROM users")
        active_users = await _scalar(
            db, "SELECT COUNT(*) FROM users WHERE last_active_at >= ?", (week_ago,)
        )
        total_submissions = await _scalar(db, "SELECT COUNT(*) FROM submissions")
        evaluated = await _scalar(db, "SELECT COUNT(*) FROM evaluations")
        finished_mocks = await _scalar(
            db, "SELECT COUNT(*) FROM mock_sessions WHERE status = 'finished'"
        )
        average_score = await _scalar(db, "SELECT AVG(overall_score) FROM evaluations")
    return {
        "total_users": total_users or 0,
        "active_users_7d": active_users or 0,
        "total_submissions": total_submissions or 0,
        "evaluated_submissions": evaluated or 0,
        "finished_mock_tests": finished_mocks or 0,
        "average_score": round(average_score, 1) if average_score is not None else None,
    }


async def get_recent_submissions(limit: int = 10) -> list[sqlite3.Row]:
    async with get_connection() as db:
        cursor = await db.execute(
            """
            SELECT s.id, s.task_type, s.word_count, s.source, s.created_at,
                   u.telegram_id, u.username, u.first_name,
                   e.estimated_cefr, e.overall_score
            FROM submissions s
            JOIN users u ON u.telegram_id = s.telegram_id
            LEFT JOIN evaluations e ON e.submission_id = s.id
            ORDER BY s.id DESC
            LIMIT ?
            """,
            (limit,),
        )
        return list(await cursor.fetchall())


# ---------------------------------------------------------------------------
# Mock tests
# ---------------------------------------------------------------------------

async def create_mock_session(telegram_id: int, task_keys: list[str]) -> int:
    """Create a mock session with all tasks in 'waiting' state. Returns session id."""
    async with get_connection() as db:
        cursor = await db.execute(
            "INSERT INTO mock_sessions (telegram_id, status, started_at) VALUES (?, 'active', ?)",
            (telegram_id, _now_iso()),
        )
        session_id = int(cursor.lastrowid)
        for position, task_key in enumerate(task_keys):
            await db.execute(
                """
                INSERT INTO mock_tasks (session_id, task_type, position, status)
                VALUES (?, ?, ?, 'waiting')
                """,
                (session_id, task_key, position),
            )
    return session_id


async def get_active_mock_session(telegram_id: int) -> sqlite3.Row | None:
    async with get_connection() as db:
        cursor = await db.execute(
            """
            SELECT id, telegram_id, status, started_at, finished_at
            FROM mock_sessions
            WHERE telegram_id = ? AND status = 'active'
            ORDER BY id DESC
            LIMIT 1
            """,
            (telegram_id,),
        )
        return await cursor.fetchone()


async def get_mock_session(session_id: int) -> sqlite3.Row | None:
    async with get_connection() as db:
        cursor = await db.execute(
            "SELECT id, telegram_id, status, started_at, finished_at FROM mock_sessions WHERE id = ?",
            (session_id,),
        )
        return await cursor.fetchone()


async def get_mock_tasks(session_id: int) -> list[sqlite3.Row]:
    async with get_connection() as db:
        cursor = await db.execute(
            """
            SELECT id, session_id, task_type, position, status, opened_at, deadline_at, closed_at
            FROM mock_tasks
            WHERE session_id = ?
            ORDER BY position
            """,
            (session_id,),
        )
        return list(await cursor.fetchall())


async def get_open_mock_task(session_id: int) -> sqlite3.Row | None:
    async with get_connection() as db:
        cursor = await db.execute(
            """
            SELECT id, session_id, task_type, position, status, opened_at, deadline_at, closed_at
            FROM mock_tasks
            WHERE session_id = ? AND status = 'open'
            LIMIT 1
            """,
            (session_id,),
        )
        return await cursor.fetchone()


async def open_next_mock_task(session_id: int) -> dict[str, Any] | None:
    """Open the next waiting task and set its deadline. Returns None when no tasks are left."""
    now = _now()
    async with get_connection() as db:
        cursor = await db.execute(
            """
            SELECT id, task_type, position
            FROM mock_tasks
            WHERE session_id = ? AND status = 'waiting'
            ORDER BY position
            LIMIT 1
            """,
            (session_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None

        minutes = await _read_task_minutes(db, row["task_type"])
        deadline = now + timedelta(minutes=minutes)
        await db.execute(
            """
            UPDATE mock_tasks
            SET status = 'open', opened_at = ?, deadline_at = ?
            WHERE id = ? AND status = 'waiting'
            """,
            (
                now.isoformat(timespec="seconds"),
                deadline.isoformat(timespec="seconds"),
                row["id"],
            ),
        )

    return {
        "id": row["id"],
        "task_type": row["task_type"],
        "position": row["position"],
        "deadline_at": deadline.isoformat(timespec="seconds"),
    }


async def submit_mock_answer(
    task_id: int,
    session_id: int,
    task_type: str,
    answer_text: str,
    word_count: int,
) -> bool:
    """Store the answer and close the task. Returns False if the task was no longer open."""
    now = _now_iso()
    async with get_connection() as db:
        cursor = await db.execute(
            "UPDATE mock_tasks SET status = 'submitted', closed_at = ? WHERE id = ? AND status = 'open'",
            (now, task_id),
        )
        if cursor.rowcount != 1:
            return False
        await db.execute(
            """
            INSERT INTO mock_answers
                (mock_task_id, session_id, task_type, answer_text, word_count, submitted_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (task_id, session_id, task_type, answer_text, word_count, now),
        )
    return True


async def expire_mock_task(task_id: int) -> bool:
    """Mark an open task as expired. Returns False if it was already closed."""
    async with get_connection() as db:
        cursor = await db.execute(
            "UPDATE mock_tasks SET status = 'expired', closed_at = ? WHERE id = ? AND status = 'open'",
            (_now_iso(), task_id),
        )
        return cursor.rowcount == 1


async def finish_mock_session(session_id: int) -> None:
    async with get_connection() as db:
        await db.execute(
            "UPDATE mock_sessions SET status = 'finished', finished_at = ? WHERE id = ? AND status = 'active'",
            (_now_iso(), session_id),
        )


async def list_open_mock_tasks() -> list[sqlite3.Row]:
    """Open tasks of active sessions. Used to restore timers after a restart."""
    async with get_connection() as db:
        cursor = await db.execute(
            """
            SELECT mt.id AS task_id, mt.session_id, mt.task_type, mt.position,
                   mt.deadline_at, ms.telegram_id
            FROM mock_tasks mt
            JOIN mock_sessions ms ON ms.id = mt.session_id
            WHERE mt.status = 'open' AND ms.status = 'active'
            """
        )
        return list(await cursor.fetchall())


async def get_mock_answers(session_id: int) -> list[sqlite3.Row]:
    async with get_connection() as db:
        cursor = await db.execute(
            """
            SELECT id, mock_task_id, session_id, task_type, answer_text, word_count,
                   submitted_at, submission_id
            FROM mock_answers
            WHERE session_id = ?
            """,
            (session_id,),
        )
        return list(await cursor.fetchall())


async def attach_submission_to_mock_answer(mock_task_id: int, submission_id: int) -> None:
    async with get_connection() as db:
        await db.execute(
            "UPDATE mock_answers SET submission_id = ? WHERE mock_task_id = ?",
            (submission_id, mock_task_id),
        )


def history_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    """Helper for converting a sqlite3.Row to a plain dictionary."""
    return {key: row[key] for key in row.keys()}
