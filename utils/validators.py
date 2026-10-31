"""Input validation for writing submissions and admin input."""

from __future__ import annotations

from dataclasses import dataclass

from config import MAX_WRITING_CHARS, MIN_WRITING_WORDS
from utils.word_counter import count_words


@dataclass(frozen=True)
class ValidationResult:
    is_valid: bool
    cleaned_text: str
    word_count: int
    error_message: str | None


def sanitize_text(raw: str) -> str:
    """Remove control characters (keeping line breaks and tabs) and trim the text."""
    cleaned = "".join(ch for ch in raw if ch in "\n\t" or ch.isprintable())
    return cleaned.strip()


def validate_writing(raw: str | None) -> ValidationResult:
    """Check a student's writing before it is sent to AI evaluation."""
    if raw is None:
        return ValidationResult(False, "", 0, "Iltimos, faqat matn yuboring.")

    cleaned = sanitize_text(raw)
    if not cleaned:
        return ValidationResult(
            False, "", 0, "Bo'sh matn yuborib bo'lmaydi. Iltimos, yozuvingizni yuboring."
        )

    if len(cleaned) > MAX_WRITING_CHARS:
        return ValidationResult(
            False,
            cleaned,
            count_words(cleaned),
            f"Matn juda uzun. Eng ko'p {MAX_WRITING_CHARS} belgi yuborish mumkin "
            f"(hozir: {len(cleaned)}).",
        )

    words = count_words(cleaned)
    if words < MIN_WRITING_WORDS:
        return ValidationResult(
            False,
            cleaned,
            words,
            f"Matn juda qisqa. Kamida {MIN_WRITING_WORDS} ta so'z yozing (hozir: {words}).",
        )

    return ValidationResult(True, cleaned, words, None)


def is_command_text(text: str | None) -> bool:
    """True when the message is a Telegram command such as /start."""
    return bool(text) and text.strip().startswith("/")


def parse_positive_int(raw: str | None, min_value: int, max_value: int) -> int | None:
    """Parse an integer inside [min_value, max_value]. Returns None when invalid."""
    if raw is None:
        return None
    try:
        value = int(raw.strip())
    except ValueError:
        return None
    if value < min_value or value > max_value:
        return None
    return value
