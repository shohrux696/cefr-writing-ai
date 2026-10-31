"""Tests for question checks in services/question_service.py (no database, no network)."""

import pytest

from config import TASKS
from services.question_service import (
    QUESTION_TOPICS,
    QuestionFormatError,
    check_word_statements,
    choose_topic,
    is_too_similar,
    validate_question,
)

TASK_11_OK = (
    "Write an informal email to your friend. Tell them about a trip you took recently, "
    "invite them to join you next weekend and ask how their exams are going. Write about 50 words."
)
TASK_12_OK = (
    "Write a formal email to the director of a language school. Ask about the course schedule "
    "and the fees for next term, and suggest a meeting next week. Write 120 to 150 words."
)
TASK_2_OK = (
    "Some people think that learning a foreign language should be compulsory at school. "
    "Post your opinion in an online discussion, giving reasons and examples. Write 180 to 200 words."
)


def test_valid_informal_question_passes():
    assert validate_question(TASKS["task_11"], "travel", {"topic": "travel", "prompt": TASK_11_OK}) == TASK_11_OK


def test_valid_formal_question_passes():
    assert validate_question(TASKS["task_12"], "education", {"topic": "education", "prompt": TASK_12_OK})


def test_valid_online_discussion_passes():
    assert validate_question(TASKS["task_2"], "education", {"topic": "education", "prompt": TASK_2_OK})


def test_wrong_topic_is_rejected():
    with pytest.raises(QuestionFormatError):
        validate_question(TASKS["task_11"], "travel", {"topic": "food", "prompt": TASK_11_OK})


def test_formal_word_in_informal_task_is_rejected():
    bad = TASK_11_OK.replace("informal", "formal")
    with pytest.raises(QuestionFormatError):
        validate_question(TASKS["task_11"], "travel", {"topic": "travel", "prompt": bad})


def test_informal_word_in_formal_task_is_rejected():
    bad = TASK_12_OK.replace("formal email", "informal email")
    with pytest.raises(QuestionFormatError):
        validate_question(TASKS["task_12"], "education", {"topic": "education", "prompt": bad})


def test_word_count_outside_range_is_rejected():
    bad = TASK_12_OK.replace("120 to 150 words", "300 words")
    with pytest.raises(QuestionFormatError):
        check_word_statements(TASKS["task_12"], bad)


def test_word_count_inside_range_is_accepted():
    check_word_statements(TASKS["task_2"], TASK_2_OK)


def test_cyrillic_text_is_rejected():
    bad = TASK_2_OK + " Бу ёзиш учун."
    with pytest.raises(QuestionFormatError):
        validate_question(TASKS["task_2"], "education", {"topic": "education", "prompt": bad})


def test_too_short_prompt_is_rejected():
    with pytest.raises(QuestionFormatError):
        validate_question(TASKS["task_11"], "travel", {"topic": "travel", "prompt": "Write an email."})


def test_identical_prompt_is_too_similar():
    assert is_too_similar(TASK_11_OK, [TASK_11_OK]) is True


def test_unrelated_prompt_is_not_too_similar():
    other = (
        "Describe the advantages of living in a big city compared with a village. "
        "Mention transport and jobs. Write about 50 words."
    )
    assert is_too_similar(TASK_11_OK, [other]) is False


def test_choose_topic_avoids_recent_topics():
    recent = [topic for topic in QUESTION_TOPICS if topic != "travel"]
    assert choose_topic(recent, set()) == "travel"


def test_choose_topic_avoids_session_topics():
    avoid = {topic for topic in QUESTION_TOPICS if topic != "health"}
    assert choose_topic([], avoid) == "health"


def test_choose_topic_always_returns_known_topic():
    for _ in range(20):
        assert choose_topic(["education"], {"work"}) in QUESTION_TOPICS
