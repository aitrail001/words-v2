from __future__ import annotations

from typing import Any
import unicodedata

_ALLOWED_TEXT_CONTROL_CHARACTERS = {"\n", "\r", "\t"}


def _is_unsafe_control_character(char: str) -> bool:
    return unicodedata.category(char) == "Cc" and char not in _ALLOWED_TEXT_CONTROL_CHARACTERS


def sanitize_control_characters(value: Any) -> Any:
    if isinstance(value, str):
        return "".join(char for char in value if not _is_unsafe_control_character(char))
    if isinstance(value, list):
        return [sanitize_control_characters(item) for item in value]
    if isinstance(value, tuple):
        return tuple(sanitize_control_characters(item) for item in value)
    if isinstance(value, dict):
        return {key: sanitize_control_characters(item) for key, item in value.items()}
    return value
