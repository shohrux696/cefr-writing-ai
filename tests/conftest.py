"""Pytest setup: make the project root importable and isolate the database."""

from __future__ import annotations

import os
import sys

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import database  # noqa: E402


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    """Point the database module at a fresh SQLite file for one test."""
    db_file = tmp_path / "test_bot.db"
    monkeypatch.setattr(database, "DATABASE_PATH", str(db_file))
    import asyncio

    asyncio.run(database.init_db())
    return str(db_file)
