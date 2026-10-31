"""Word counting for English writing submissions."""

from __future__ import annotations

import re

_HAS_ALNUM = re.compile(r"[A-Za-z0-9]")


def count_words(text: str | None) -> int:
    """Count words as whitespace-separated tokens that contain a letter or digit.

    Standalone punctuation such as a dash or an ellipsis is not counted.
    """
    if not text:
        return 0
    return sum(1 for token in text.split() if _HAS_ALNUM.search(token))
