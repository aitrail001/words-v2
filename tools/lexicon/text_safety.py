from __future__ import annotations

from typing import Any
import unicodedata


def contains_control_characters(value: str) -> bool:
    return any(unicodedata.category(char) == "Cc" for char in value)


def validate_no_control_characters(value: str, *, field: str, exc_type: type[Exception] = RuntimeError) -> str:
    if contains_control_characters(value):
        raise exc_type(f"{field} contains a control character")
    return value


def sanitize_control_characters(value: Any) -> Any:
    if isinstance(value, str):
        return "".join(char for char in value if unicodedata.category(char) != "Cc")
    if isinstance(value, list):
        return [sanitize_control_characters(item) for item in value]
    if isinstance(value, tuple):
        return tuple(sanitize_control_characters(item) for item in value)
    if isinstance(value, dict):
        return {key: sanitize_control_characters(item) for key, item in value.items()}
    return value


def validate_nested_no_control_characters(value: Any, *, field: str, exc_type: type[Exception] = ValueError) -> None:
    if isinstance(value, str):
        validate_no_control_characters(value, field=field, exc_type=exc_type)
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            validate_nested_no_control_characters(item, field=f"{field}[{index}]", exc_type=exc_type)
        return
    if isinstance(value, tuple):
        for index, item in enumerate(value):
            validate_nested_no_control_characters(item, field=f"{field}[{index}]", exc_type=exc_type)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            key_text = str(key)
            validate_no_control_characters(key_text, field=f"{field}.<key>", exc_type=exc_type)
            validate_nested_no_control_characters(item, field=f"{field}.{key_text}", exc_type=exc_type)
