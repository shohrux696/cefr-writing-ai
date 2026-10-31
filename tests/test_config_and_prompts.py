"""Checks that task definitions and prompt files are consistent."""

import os

from config import MOCK_TASK_ORDER, PROMPTS_DIR, TASKS


def test_every_mock_task_exists():
    for key in MOCK_TASK_ORDER:
        assert key in TASKS


def test_every_task_has_prompt_file():
    for spec in TASKS.values():
        path = os.path.join(PROMPTS_DIR, spec.prompt_file)
        assert os.path.isfile(path), f"Missing prompt file: {path}"


def test_word_ranges_are_sane():
    for spec in TASKS.values():
        assert 0 < spec.target_min_words <= spec.target_max_words
        assert spec.default_minutes > 0
