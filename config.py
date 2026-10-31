"""Central configuration. All secrets come from environment variables (.env)."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROMPTS_DIR = os.path.join(BASE_DIR, "prompts")


class ConfigError(RuntimeError):
    """Raised when required configuration is missing or invalid."""


def _get_int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} butun son bo'lishi kerak.") from exc


BOT_TOKEN: str = os.getenv("BOT_TOKEN", "").strip()
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "").strip()
ADMIN_ID: int = _get_int("ADMIN_ID", 0)
DATABASE_PATH: str = os.getenv("DATABASE_PATH", "").strip() or os.path.join(BASE_DIR, "cefr_bot.db")
GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "").strip() or "gemini-2.5-flash"
GEMINI_TIMEOUT_SECONDS: int = _get_int("GEMINI_TIMEOUT_SECONDS", 90)
GEMINI_MAX_RETRIES: int = _get_int("GEMINI_MAX_RETRIES", 2)
MAX_WRITING_CHARS: int = _get_int("MAX_WRITING_CHARS", 4000)
MIN_WRITING_WORDS: int = _get_int("MIN_WRITING_WORDS", 5)
DIMENSION_MAX_SCORE: int = _get_int("DIMENSION_MAX_SCORE", 5)
OVERALL_MAX_SCORE: int = _get_int("OVERALL_MAX_SCORE", 100)
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "").strip().upper() or "INFO"

SOURCE_SINGLE = "single"
SOURCE_MOCK = "mock"


@dataclass(frozen=True)
class TaskSpec:
    """Specification of one writing task.

    The instructions text is shown to students. Edit it here if your
    teaching materials change. Time limits are practice defaults and can be
    changed by the administrator inside the bot.
    """

    key: str
    title: str
    instructions: str
    target_min_words: int
    target_max_words: int
    default_minutes: int
    prompt_file: str


TASKS: dict[str, TaskSpec] = {
    "task_11": TaskSpec(
        key="task_11",
        title="Task 1.1 — Informal email",
        instructions=(
            "Write an informal email to your friend. Tell him or her about a trip "
            "you took recently, invite your friend to join you next weekend, and ask "
            "how the exams are going. Target length: about 50 words."
        ),
        target_min_words=40,
        target_max_words=60,
        default_minutes=20,
        prompt_file="task_11.txt",
    ),
    "task_12": TaskSpec(
        key="task_12",
        title="Task 1.2 — Formal email",
        instructions=(
            "Write a formal email to the director of a language school. Ask about the "
            "course schedule and the fees for the next term, and suggest a meeting "
            "next week. Target length: 120 to 150 words."
        ),
        target_min_words=120,
        target_max_words=150,
        default_minutes=20,
        prompt_file="task_12.txt",
    ),
    "task_2": TaskSpec(
        key="task_2",
        title="Task 2 — Blog post / opinion",
        instructions=(
            "Some people think that learning a foreign language should be compulsory "
            "at school. Do you agree or disagree? Write a blog post giving your opinion, "
            "with reasons and examples. Target length: 180 to 200 words."
        ),
        target_min_words=180,
        target_max_words=200,
        default_minutes=40,
        prompt_file="task_2.txt",
    ),
}

# Order of tasks in the FULL MOCK TEST
MOCK_TASK_ORDER: tuple[str, ...] = ("task_11", "task_12", "task_2")


def validate_config() -> None:
    """Check required settings at startup. Raises ConfigError if something is wrong."""
    errors: list[str] = []
    if not BOT_TOKEN or ":" not in BOT_TOKEN:
        errors.append("BOT_TOKEN yo'q yoki noto'g'ri")
    if ADMIN_ID <= 0:
        errors.append("ADMIN_ID yo'q yoki noto'g'ri")
    if DIMENSION_MAX_SCORE <= 0 or OVERALL_MAX_SCORE <= 0:
        errors.append("DIMENSION_MAX_SCORE va OVERALL_MAX_SCORE musbat bo'lishi kerak")
    if MAX_WRITING_CHARS <= 0 or MIN_WRITING_WORDS <= 0:
        errors.append("MAX_WRITING_CHARS va MIN_WRITING_WORDS musbat bo'lishi kerak")
    if errors:
        raise ConfigError("; ".join(errors))

    if not GEMINI_API_KEY:
        logging.getLogger(__name__).warning(
            "GEMINI_API_KEY o'rnatilmagan. AI baholash ishlamaydi."
        )


def _mask(secret: str) -> str:
    if len(secret) <= 8:
        return "***"
    return "***" + secret[-4:]


class SecretFilter(logging.Filter):
    """Replaces known secrets with masked values in every log message."""

    def __init__(self, secrets: list[str]) -> None:
        super().__init__()
        self._secrets = [s for s in secrets if s]

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        for secret in self._secrets:
            message = message.replace(secret, _mask(secret))
        record.msg = message
        record.args = ()
        return True


def setup_logging() -> None:
    """Configure logging for the whole application."""
    logging.basicConfig(
        level=LOG_LEVEL,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    secret_filter = SecretFilter([BOT_TOKEN, GEMINI_API_KEY])
    for handler in logging.getLogger().handlers:
        handler.addFilter(secret_filter)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
