"""Phrase enrichment schema helpers."""

from __future__ import annotations

from typing import Any

from tools.lexicon.contracts import (
    ALLOWED_CEFR_LEVELS,
    ALLOWED_REGISTERS,
    normalize_confidence,
    normalize_examples,
    normalize_optional_enum,
    normalize_string_list_field,
    normalize_translation_payload,
    require_non_empty_string,
    REQUIRED_TRANSLATION_LOCALES,
)

ALLOWED_PHRASE_KINDS = ("collocation", "idiom", "multiword_expression", "phrasal_verb")


def _nullable_schema(inner: dict[str, Any]) -> dict[str, Any]:
    return {"anyOf": [inner, {"type": "null"}]}


def _phrase_example_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "sentence": {"type": "string"},
            "difficulty": {"type": "string", "enum": sorted(ALLOWED_CEFR_LEVELS)},
        },
        "required": ["sentence", "difficulty"],
        "additionalProperties": False,
    }


def _translation_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "definition": {"type": "string"},
            "usage_note": {"type": "string"},
            "examples": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["definition", "usage_note", "examples"],
        "additionalProperties": False,
    }


def build_phrase_enrichment_response_schema() -> dict[str, Any]:
    return {
        "name": "lexicon_enrichment_phrase",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "phrase_kind": {"type": "string", "enum": sorted(ALLOWED_PHRASE_KINDS)},
                "definition": {"type": "string"},
                "examples": {"type": "array", "items": _phrase_example_schema(), "minItems": 1},
                "cefr_level": _nullable_schema({"type": "string", "enum": sorted(ALLOWED_CEFR_LEVELS)}),
                "register": _nullable_schema({"type": "string", "enum": sorted(ALLOWED_REGISTERS)}),
                "grammar_patterns": _nullable_schema({"type": "array", "items": {"type": "string"}}),
                "usage_note": _nullable_schema({"type": "string"}),
                "translations": {
                    "type": "object",
                    "properties": {locale: _translation_schema() for locale in REQUIRED_TRANSLATION_LOCALES},
                    "required": list(REQUIRED_TRANSLATION_LOCALES),
                    "additionalProperties": False,
                },
                "confidence": {"type": "number"},
            },
            "required": [
                "phrase_kind",
                "definition",
                "examples",
                "cefr_level",
                "register",
                "grammar_patterns",
                "usage_note",
                "translations",
                "confidence",
            ],
            "additionalProperties": False,
        },
    }


def normalize_phrase_enrichment_payload(response: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(response, dict):
        raise RuntimeError("OpenAI-compatible endpoint returned a non-object phrase enrichment payload")

    normalized = dict(response)
    normalized["phrase_kind"] = require_non_empty_string(response.get("phrase_kind"), field="phrase_kind")
    if normalized["phrase_kind"] not in ALLOWED_PHRASE_KINDS:
        raise RuntimeError(f"OpenAI-compatible enrichment payload field 'phrase_kind' must be one of {sorted(ALLOWED_PHRASE_KINDS)}")
    normalized["definition"] = require_non_empty_string(response.get("definition"), field="definition")
    normalized["examples"] = normalize_examples(response.get("examples"))
    normalized["cefr_level"] = normalize_optional_enum(response.get("cefr_level"), field="cefr_level", allowed=ALLOWED_CEFR_LEVELS)
    normalized["register"] = normalize_optional_enum(response.get("register"), field="register", allowed=ALLOWED_REGISTERS)
    normalized["grammar_patterns"] = normalize_string_list_field(response.get("grammar_patterns"), field="grammar_patterns")
    normalized["usage_note"] = (
        require_non_empty_string(response.get("usage_note"), field="usage_note")
        if response.get("usage_note") is not None
        else None
    )
    normalized["confidence"] = normalize_confidence(response.get("confidence"))
    normalized["translations"] = normalize_translation_payload(
        response.get("translations"),
        example_count=len(normalized["examples"]),
    )
    return normalized
