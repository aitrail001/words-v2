"""Reference-entry schema helpers."""

from __future__ import annotations

from typing import Any

from tools.lexicon.contracts import (
    ALLOWED_REFERENCE_TYPES,
    ALLOWED_TRANSLATION_MODES,
    normalize_confidence,
    normalize_optional_enum,
    require_non_empty_string,
)


def _nullable_schema(inner: dict[str, Any]) -> dict[str, Any]:
    return {"anyOf": [inner, {"type": "null"}]}


def _localized_text_map_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": {"type": "string"},
    }


def build_reference_entry_response_schema() -> dict[str, Any]:
    return {
        "name": "lexicon_reference_entry",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "reference_type": {"type": "string", "enum": sorted(ALLOWED_REFERENCE_TYPES)},
                "display_form": {"type": "string"},
                "translation_mode": {"type": "string", "enum": sorted(ALLOWED_TRANSLATION_MODES)},
                "brief_description": {"type": "string"},
                "pronunciation": {"type": "string"},
                "localized_display_form": _nullable_schema(_localized_text_map_schema()),
                "localized_brief_description": _nullable_schema(_localized_text_map_schema()),
                "learner_tip": _nullable_schema({"type": "string"}),
                "confidence": {"type": "number"},
            },
            "required": [
                "reference_type",
                "display_form",
                "translation_mode",
                "brief_description",
                "pronunciation",
                "localized_display_form",
                "localized_brief_description",
                "learner_tip",
                "confidence",
            ],
            "additionalProperties": False,
        },
    }


def normalize_reference_entry_payload(response: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(response, dict):
        raise RuntimeError("OpenAI-compatible endpoint returned a non-object reference payload")

    normalized = dict(response)
    normalized["reference_type"] = normalize_optional_enum(
        response.get("reference_type"),
        field="reference_type",
        allowed=ALLOWED_REFERENCE_TYPES,
    )
    if normalized["reference_type"] is None:
        raise RuntimeError("OpenAI-compatible enrichment payload field 'reference_type' must be a non-empty string")
    normalized["display_form"] = require_non_empty_string(response.get("display_form"), field="display_form")
    normalized["translation_mode"] = normalize_optional_enum(
        response.get("translation_mode"),
        field="translation_mode",
        allowed=ALLOWED_TRANSLATION_MODES,
    )
    if normalized["translation_mode"] is None:
        raise RuntimeError("OpenAI-compatible enrichment payload field 'translation_mode' must be a non-empty string")
    normalized["brief_description"] = require_non_empty_string(response.get("brief_description"), field="brief_description")
    normalized["pronunciation"] = require_non_empty_string(response.get("pronunciation"), field="pronunciation")
    normalized["localized_display_form"] = response.get("localized_display_form")
    normalized["localized_brief_description"] = response.get("localized_brief_description")
    if normalized["localized_display_form"] is not None and not isinstance(normalized["localized_display_form"], dict):
        raise RuntimeError("OpenAI-compatible enrichment payload field 'localized_display_form' must be an object or null")
    if normalized["localized_brief_description"] is not None and not isinstance(normalized["localized_brief_description"], dict):
        raise RuntimeError("OpenAI-compatible enrichment payload field 'localized_brief_description' must be an object or null")
    normalized["learner_tip"] = (
        require_non_empty_string(response.get("learner_tip"), field="learner_tip")
        if response.get("learner_tip") is not None
        else None
    )
    normalized["confidence"] = normalize_confidence(response.get("confidence"))
    return normalized
