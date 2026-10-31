"""Tests for the AI answer parser and validator in services/evaluation_service.py"""

import pytest

from config import DIMENSION_MAX_SCORE, OVERALL_MAX_SCORE
from services.evaluation_service import (
    EvaluationFormatError,
    extract_json_object,
    format_result_text,
    normalize_evaluation,
    split_for_telegram,
)

STUDENT_TEXT = "Hi Ali, I am agree with this idea. I go to school every day."


def _valid_raw(**overrides):
    raw = {
        "estimated_cefr_level": "b1",
        "overall_score": 70,
        "task_achievement": {"score": 4, "feedback": "Javob asosan to'g'ri."},
        "organisation": {"score": 3, "feedback": "Tuzilish yaxshi."},
        "vocabulary": {"score": 3, "feedback": "Leksika oddiy."},
        "grammar": {"score": 4, "feedback": "Grammatika yaxshi."},
        "missing_points": [],
        "mistakes": [
            {
                "category": "grammar",
                "original": "I am agree",
                "correction": "I agree",
                "explanation_uz": "'Agree' fe'l, 'am' kerak emas.",
            },
            {
                "category": "vocabulary",
                "original": "invented sentence that is not in the text",
                "correction": "x",
                "explanation_uz": "bu xato qabul qilinmasligi kerak",
            },
        ],
        "corrected_version": "Hi Ali, I agree with this idea.",
        "improved_version": "Hi Ali, I agree with this idea. I go to school every day.",
        "recommendations": ["Fe'l shakllariga e'tibor bering."],
    }
    raw.update(overrides)
    return raw


def test_extract_plain_json():
    data = extract_json_object('{"a": 1}')
    assert data == {"a": 1}


def test_extract_json_inside_code_fence():
    data = extract_json_object('```json\n{"a": 2}\n```')
    assert data == {"a": 2}


def test_extract_json_with_extra_text_around():
    data = extract_json_object('Here is the result: {"a": 3} thanks')
    assert data == {"a": 3}


def test_extract_invalid_json_raises():
    with pytest.raises(EvaluationFormatError):
        extract_json_object("this is not json at all")


def test_extract_non_object_raises():
    with pytest.raises(EvaluationFormatError):
        extract_json_object("[1, 2, 3]")


def test_normalize_valid_answer():
    result = normalize_evaluation(_valid_raw(), STUDENT_TEXT, word_count=14)
    assert result["estimated_cefr_level"] == "B1"
    assert result["word_count"] == 14
    assert result["overall_score"] == 70


def test_invented_mistakes_are_dropped():
    result = normalize_evaluation(_valid_raw(), STUDENT_TEXT, word_count=14)
    originals = [m["original"] for m in result["mistakes"]]
    assert "I am agree" in originals
    assert all(o in STUDENT_TEXT for o in originals)
    assert len(result["mistakes"]) == 1


def test_scores_are_clamped_to_scale():
    raw = _valid_raw(overall_score=999)
    raw["grammar"] = {"score": -5, "feedback": "x"}
    result = normalize_evaluation(raw, STUDENT_TEXT, word_count=10)
    assert result["overall_score"] == OVERALL_MAX_SCORE
    assert result["grammar"]["score"] == 0
    assert result["task_achievement"]["score"] <= DIMENSION_MAX_SCORE


def test_invalid_cefr_level_raises():
    with pytest.raises(EvaluationFormatError):
        normalize_evaluation(_valid_raw(estimated_cefr_level="D5"), STUDENT_TEXT, 10)


def test_missing_recommendations_raises():
    with pytest.raises(EvaluationFormatError):
        normalize_evaluation(_valid_raw(recommendations=[]), STUDENT_TEXT, 10)


def test_missing_dimension_raises():
    raw = _valid_raw()
    del raw["vocabulary"]
    with pytest.raises(EvaluationFormatError):
        normalize_evaluation(raw, STUDENT_TEXT, 10)


def test_format_result_contains_estimate_label():
    result = normalize_evaluation(_valid_raw(), STUDENT_TEXT, word_count=14)
    text = format_result_text("Task 1.1", result)
    assert "taxminiy" in text
    assert "B1" in text


def test_split_for_telegram_respects_limit():
    long_text = "\n".join(["line " * 50] * 200)
    chunks = split_for_telegram(long_text, limit=1000)
    assert len(chunks) > 1
    assert all(len(chunk) <= 1000 for chunk in chunks)
