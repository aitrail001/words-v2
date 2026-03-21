"""Thin Batch API client helpers for the lexicon offline pipeline."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable


class BatchClient:
    """Thin, injectable batch transport boundary."""

    def __init__(
        self,
        *,
        transport: Callable[[str, dict[str, Any], dict[str, str]], dict[str, Any]] | None = None,
    ) -> None:
        self.transport = transport or _default_transport

    def upload_batch_file(self, path: Path, *, purpose: str = "batch") -> dict[str, Any]:
        payload = {
            "path": str(path),
            "purpose": purpose,
            "content": path.read_text(encoding="utf-8"),
        }
        return self.transport("upload_batch_file", payload, {})

    def create_batch(self, *, input_file_id: str, endpoint: str) -> dict[str, Any]:
        payload = {
            "input_file_id": input_file_id,
            "endpoint": endpoint,
        }
        return self.transport("create_batch", payload, {})

    def get_batch(self, *, batch_id: str) -> dict[str, Any]:
        return self.transport("get_batch", {"batch_id": batch_id}, {})

    def download_file(self, *, file_id: str) -> dict[str, Any]:
        return self.transport("download_file", {"file_id": file_id}, {})


def _default_transport(operation: str, payload: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
    raise RuntimeError(f"BatchClient transport is not configured for operation {operation}")
