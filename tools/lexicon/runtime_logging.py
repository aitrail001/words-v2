from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Literal
import json
import sys

RuntimeLogLevel = Literal["quiet", "info", "debug"]

_LEVEL_ORDER: dict[RuntimeLogLevel, int] = {
    "quiet": 0,
    "info": 1,
    "debug": 2,
}
_REDACTED_VALUE = "[redacted]"
_REDACTED_FIELD_NAMES = {
    "body",
    "input",
    "output_text",
    "payload",
    "raw",
    "raw_response",
    "response",
    "response_text",
}


@dataclass(frozen=True)
class RuntimeLogConfig:
    level: RuntimeLogLevel = "info"
    log_file: Path | None = None


class RuntimeLogger:
    def __init__(
        self,
        config: RuntimeLogConfig,
        *,
        stream: Any | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if config.level not in _LEVEL_ORDER:
            raise ValueError(f"Unsupported runtime log level: {config.level}")
        self.config = config
        self._stream = stream or sys.stdout
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def info(self, event: str, message: str = "", **fields: Any) -> None:
        self.emit("info", event, message, **fields)

    def debug(self, event: str, message: str = "", **fields: Any) -> None:
        self.emit("debug", event, message, **fields)

    def emit(self, level: RuntimeLogLevel, event: str, message: str = "", **fields: Any) -> dict[str, Any]:
        if level not in _LEVEL_ORDER:
            raise ValueError(f"Unsupported runtime log level: {level}")

        record = {
            "timestamp": _format_timestamp(self._clock()),
            "level": level,
            "event": event,
            "message": message,
            "fields": _sanitize_fields(fields),
        }
        if self._should_emit(level) and self.config.log_file is not None:
            self._write_file_record(record)
        if self._should_emit(level):
            self._write_terminal_record(record)
        return record

    def _should_emit(self, level: RuntimeLogLevel) -> bool:
        if self.config.level == "quiet":
            return False
        return _LEVEL_ORDER[level] <= _LEVEL_ORDER[self.config.level]

    def _write_terminal_record(self, record: dict[str, Any]) -> None:
        parts = [record["timestamp"], f"[{record['level']}]", f"{record['event']}:"]
        if record["message"]:
            parts.append(str(record["message"]))
        fields = record["fields"]
        if isinstance(fields, dict) and fields:
            for key in sorted(fields):
                parts.append(f"{key}={_format_terminal_value(fields[key])}")
        print(" ".join(parts), file=self._stream)

    def _write_file_record(self, record: dict[str, Any]) -> None:
        path = self.config.log_file
        if path is None:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def _format_timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    value = value.astimezone(timezone.utc).replace(microsecond=0)
    return value.isoformat().replace("+00:00", "Z")


def _sanitize_fields(fields: dict[str, Any]) -> dict[str, Any]:
    sanitized: dict[str, Any] = {}
    for key, value in fields.items():
        sanitized[key] = _sanitize_value(key, value)
    return sanitized


def _sanitize_value(field_name: str, value: Any) -> Any:
    if field_name in _REDACTED_FIELD_NAMES:
        return _REDACTED_VALUE
    if isinstance(value, dict):
        return {key: _sanitize_value(key, nested_value) for key, nested_value in value.items()}
    if isinstance(value, list):
        return [_sanitize_value(field_name, item) for item in value]
    return value


def _format_terminal_value(value: Any) -> str:
    if isinstance(value, str):
        return value
    if value is None or isinstance(value, (int, float, bool)):
        return str(value)
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
