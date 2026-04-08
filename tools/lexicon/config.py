from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping
import os


_ALLOWED_REASONING_EFFORTS = {"none", "low", "medium", "high"}
_DEFAULT_LLM_TIMEOUT_SECONDS = 60
_DEFAULT_LLM_REASONING_EFFORT = "none"
_STAGE_ENV_PREFIXES = {
    "core": "LEXICON_CORE_LLM_",
    "translations": "LEXICON_TRANSLATIONS_LLM_",
}


def _normalize_reasoning_effort(value: str | None) -> str | None:
    if value is None:
        return _DEFAULT_LLM_REASONING_EFFORT
    normalized = value.strip().lower()
    if not normalized:
        return _DEFAULT_LLM_REASONING_EFFORT
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
    def _resolve_stage_value(
        cls,
        source: Mapping[str, str],
        *,
        stage: str | None,
        suffix: str,
        allow_provider_alias: bool = False,
    ) -> str | None:
        if stage:
            prefix = _STAGE_ENV_PREFIXES.get(stage)
            if prefix is None:
                raise ValueError(f"Unsupported lexicon settings stage '{stage}'")
            stage_value = source.get(f"{prefix}{suffix}")
            if stage_value:
                return stage_value
            if allow_provider_alias:
                stage_provider_alias = source.get(f"{prefix}PROVIDER")
                if stage_provider_alias:
                    return stage_provider_alias
        generic_value = source.get(f"LEXICON_LLM_{suffix}")
        if generic_value:
            return generic_value
        if allow_provider_alias:
            return source.get("LEXICON_LLM_PROVIDER")
        return None

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None, *, stage: str | None = None) -> "LexiconSettings":
        source = dict(os.environ if env is None else env)
        output_root = Path(source.get("LEXICON_OUTPUT_ROOT", "data/lexicon"))
        llm_base_url = cls._resolve_stage_value(source, stage=stage, suffix="BASE_URL", allow_provider_alias=True)
        return cls(
            output_root=output_root,
            llm_base_url=llm_base_url,
            llm_model=cls._resolve_stage_value(source, stage=stage, suffix="MODEL"),
            llm_api_key=cls._resolve_stage_value(source, stage=stage, suffix="API_KEY"),
            llm_transport=cls._resolve_stage_value(source, stage=stage, suffix="TRANSPORT"),
            llm_reasoning_effort=_normalize_reasoning_effort(
                cls._resolve_stage_value(source, stage=stage, suffix="REASONING_EFFORT")
            ),
            llm_timeout_seconds=_normalize_positive_int(
                cls._resolve_stage_value(source, stage=stage, suffix="TIMEOUT_SECONDS"),
                field_name=(
                    f"{_STAGE_ENV_PREFIXES[stage]}TIMEOUT_SECONDS"
                    if stage in _STAGE_ENV_PREFIXES
                    else "LEXICON_LLM_TIMEOUT_SECONDS"
                ),
                default=_DEFAULT_LLM_TIMEOUT_SECONDS,
            ),
        )
