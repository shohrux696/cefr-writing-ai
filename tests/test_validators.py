"""Tests for utils/validators.py"""

from config import MAX_WRITING_CHARS, MIN_WRITING_WORDS
from utils.validators import (
    is_command_text,
    parse_positive_int,
    sanitize_text,
    validate_writing,
)


def test_none_is_invalid():
    result = validate_writing(None)
    assert result.is_valid is False


def test_empty_text_is_invalid():
    result = validate_writing("   \n  ")
    assert result.is_valid is False
    assert result.error_message


def test_too_short_text_is_invalid():
    result = validate_writing("Hi there")
    assert result.is_valid is False
    assert str(MIN_WRITING_WORDS) in result.error_message


def test_normal_text_is_valid():
    text = "Hi Ali, I went to Samarkand last week and it was great."
    result = validate_writing(text)
    assert result.is_valid is True
    assert result.word_count >= MIN_WRITING_WORDS
    assert result.cleaned_text == text


def test_too_long_text_is_invalid():
    text = "word " * (MAX_WRITING_CHARS // 2)
    result = validate_writing(text)
    assert result.is_valid is False


def test_control_characters_are_removed():
    cleaned = sanitize_text("Hello\x00 world\x07 this is a test")
    assert "\x00" not in cleaned
    assert "\x07" not in cleaned
    assert "Hello" in cleaned


def test_line_breaks_are_kept():
    assert "\n" in sanitize_text("Line one\nLine two")


def test_command_detection():
    assert is_command_text("/start") is True
    assert is_command_text("  /help") is True
    assert is_command_text("hello") is False
    assert is_command_text(None) is False


def test_parse_positive_int_range():
    assert parse_positive_int("30", 1, 240) == 30
    assert parse_positive_int(" 5 ", 1, 240) == 5
    assert parse_positive_int("0", 1, 240) is None
    assert parse_positive_int("241", 1, 240) is None
    assert parse_positive_int("abc", 1, 240) is None
    assert parse_positive_int(None, 1, 240) is None
