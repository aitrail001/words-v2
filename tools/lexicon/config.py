from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping
import os


_ALLOWED_REASONING_EFFORTS = {"low", "medium", "high"}


def _normalize_reasoning_effort(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    if not normalized:
        return None
    if normalized not in _ALLOWED_REASONING_EFFORTS:
        raise ValueError(
            f"Unsupported LEXICON_LLM_REASONING_EFFORT '{value}'. Expected one of: low, medium, high."
        )
    return normalized


@dataclass(frozen=True)
class LexiconSettings:
    output_root: Path
    llm_base_url: str | None
    llm_model: str | None
    llm_api_key: str | None
    llm_transport: str | None
    llm_reasoning_effort: str | None

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
        )
