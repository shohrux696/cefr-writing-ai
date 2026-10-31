"""Google Gemini API client with timeouts, retries and error classification.

This module only sends a request and returns the raw text of the answer.
Parsing and validating the JSON is done in evaluation_service.py.
"""

from __future__ import annotations

import asyncio
import logging

from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from config import (
    GEMINI_API_KEY,
    GEMINI_MAX_RETRIES,
    GEMINI_MODEL,
    GEMINI_TIMEOUT_SECONDS,
)

logger = logging.getLogger(__name__)

# Maximum number of Gemini requests running at the same time (protects free-tier quota)
MAX_CONCURRENT_REQUESTS = 3

_client: genai.Client | None = None
_semaphore: asyncio.Semaphore | None = None


class GeminiError(Exception):
    """Base error. The message is written in Uzbek and can be shown to students."""


class GeminiConfigError(GeminiError):
    """API key is missing or rejected."""


class GeminiRateLimitError(GeminiError):
    """Free-tier rate limit or quota reached."""


class GeminiUnavailableError(GeminiError):
    """Timeout, connection problem or temporary server error."""


class GeminiEmptyResponseError(GeminiError):
    """Gemini returned no text (blocked or empty answer)."""


def is_configured() -> bool:
    """True when GEMINI_API_KEY is set."""
    return bool(GEMINI_API_KEY)


def _get_client() -> genai.Client:
    global _client
    if not GEMINI_API_KEY:
        raise GeminiConfigError(
            "AI baholash sozlanmagan: GEMINI_API_KEY o'rnatilmagan."
        )
    if _client is None:
        _client = genai.Client(api_key=GEMINI_API_KEY)
    return _client


def _get_semaphore() -> asyncio.Semaphore:
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
    return _semaphore


def _extract_text(response: object) -> str:
    text = getattr(response, "text", None)
    if not text or not str(text).strip():
        raise GeminiEmptyResponseError("Gemini bo'sh javob qaytardi.")
    return str(text)


def _backoff_seconds(attempt: int, error: GeminiError) -> float:
    if isinstance(error, GeminiRateLimitError):
        return 5.0 * attempt
    return float(2 ** attempt)


async def generate_json(system_instruction: str, user_message: str) -> str:
    """Send one request to Gemini and return the raw text of the answer.

    Retries on timeouts, connection problems, temporary server errors,
    rate limits and empty responses. Raises GeminiError subclasses with
    Uzbek messages when all attempts fail.
    """
    client = _get_client()
    config = types.GenerateContentConfig(
        system_instruction=system_instruction,
        response_mime_type="application/json",
        temperature=0.2,
        max_output_tokens=8192,
    )

    attempts = max(0, GEMINI_MAX_RETRIES) + 1
    last_error: GeminiError | None = None

    for attempt in range(1, attempts + 1):
        try:
            async with _get_semaphore():
                response = await asyncio.wait_for(
                    client.aio.models.generate_content(
                        model=GEMINI_MODEL,
                        contents=user_message,
                        config=config,
                    ),
                    timeout=GEMINI_TIMEOUT_SECONDS,
                )
            return _extract_text(response)

        except GeminiEmptyResponseError as exc:
            logger.warning("Gemini returned empty response (attempt %d/%d)", attempt, attempts)
            last_error = exc

        except asyncio.TimeoutError:
            logger.warning("Gemini timeout after %ss (attempt %d/%d)",
                           GEMINI_TIMEOUT_SECONDS, attempt, attempts)
            last_error = GeminiUnavailableError(
                "AI javobi juda sekin keldi. Iltimos, biroz kutib qayta urinib ko'ring."
            )

        except genai_errors.APIError as exc:
            code = getattr(exc, "code", None)
            logger.warning("Gemini API error code=%s (attempt %d/%d)", code, attempt, attempts)
            if code == 429:
                last_error = GeminiRateLimitError(
                    "AI limiti vaqtincha tugagan. Bir necha daqiqadan keyin qayta urinib ko'ring."
                )
            elif code in (401, 403):
                raise GeminiConfigError(
                    "AI kaliti noto'g'ri yoki ruxsat berilmagan. Administrator bilan bog'laning."
                ) from exc
            elif code == 400:
                raise GeminiError(
                    "AI so'rovni qabul qilmadi. Matnni tekshirib, qayta yuboring."
                ) from exc
            elif code is not None and code >= 500:
                last_error = GeminiUnavailableError(
                    "AI xizmati vaqtincha ishlamayapti. Keyinroq qayta urinib ko'ring."
                )
            else:
                raise GeminiError(
                    "AI xizmatida noma'lum xatolik yuz berdi. Keyinroq qayta urinib ko'ring."
                ) from exc

        except GeminiError:
            raise

        except Exception as exc:  # network and other unexpected errors
            logger.warning("Gemini connection error: %s (attempt %d/%d)",
                           type(exc).__name__, attempt, attempts)
            last_error = GeminiUnavailableError(
                "AI xizmatiga ulanib bo'lmadi. Internet aloqasini tekshiring."
            )

        if attempt < attempts and last_error is not None:
            await asyncio.sleep(_backoff_seconds(attempt, last_error))

    raise last_error or GeminiUnavailableError(
        "AI xizmati javob bermadi. Keyinroq qayta urinib ko'ring."
    )
