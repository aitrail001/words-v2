from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping
import os


_ALLOWED_REASONING_EFFORTS = {"none", "low", "medium", "high"}
_DEFAULT_LLM_TIMEOUT_SECONDS = 60


def _normalize_reasoning_effort(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    if not normalized:
        return None
    if normalized not in _ALLOWED_REASONING_EFFORTS:
        raise ValueError(
            f"Unsupported LEXICON_LLM_REASONING_EFFORT '{value}'. Expected one of: none, low, medium, high."
        )
    return normalized


def _normalize_positive_int(value: str | None, *, field_name: str, default: int) -> int:
    if value is None:
        return default
    normalized = value.strip()
    if not normalized:
        return default
    try:
        parsed = int(normalized)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be a positive integer.") from exc
    if parsed <= 0:
        raise ValueError(f"{field_name} must be a positive integer.")
    return parsed


@dataclass(frozen=True)
class LexiconSettings:
    output_root: Path
    llm_base_url: str | None
    llm_model: str | None
    llm_api_key: str | None
    llm_transport: str | None
    llm_reasoning_effort: str | None
    llm_timeout_seconds: int

    @property
    def llm_provider(self) -> str | None:
        return self.llm_base_url

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "LexiconSettings":
        source = dict(os.environ if env is None else env)
        output_root = Path(source.get("LEXICON_OUTPUT_ROOT", "data/lexicon"))
        llm_base_url = source.get("LEXICON_LLM_BASE_URL") or source.get("LEXICON_LLM_PROVIDER")
        return cls(
            output_root=output_root,
            llm_base_url=llm_base_url,
            llm_model=source.get("LEXICON_LLM_MODEL"),
            llm_api_key=source.get("LEXICON_LLM_API_KEY"),
            llm_transport=source.get("LEXICON_LLM_TRANSPORT"),
            llm_reasoning_effort=_normalize_reasoning_effort(source.get("LEXICON_LLM_REASONING_EFFORT")),
            llm_timeout_seconds=_normalize_positive_int(
                source.get("LEXICON_LLM_TIMEOUT_SECONDS"),
                field_name="LEXICON_LLM_TIMEOUT_SECONDS",
                default=_DEFAULT_LLM_TIMEOUT_SECONDS,
            ),
        )
