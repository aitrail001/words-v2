"""Phrase enrichment schema helpers."""

from __future__ import annotations

from typing import Any

from tools.lexicon.contracts import (
    ALLOWED_CEFR_LEVELS,
    normalize_confidence,
    normalize_examples,
    normalize_string_list_field,
    require_non_empty_string,
    REQUIRED_TRANSLATION_LOCALES,
)
from tools.lexicon.text_safety import validate_no_control_characters

ALLOWED_PHRASE_KINDS = ("idiom", "multiword_expression", "phrasal_verb")


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


def _sense_schema(*, include_translations: bool = True) -> dict[str, Any]:
    properties: dict[str, Any] = {
        "definition": {"type": "string"},
        "part_of_speech": {"type": "string"},
        "examples": {"type": "array", "items": _phrase_example_schema(), "minItems": 1},
        "grammar_patterns": _nullable_schema({"type": "array", "items": {"type": "string"}}),
        "usage_note": _nullable_schema({"type": "string"}),
    }
    required = [
        "definition",
        "part_of_speech",
        "examples",
        "grammar_patterns",
        "usage_note",
    ]
    if include_translations:
        properties["translations"] = {
            "type": "object",
            "properties": {locale: _translation_schema() for locale in REQUIRED_TRANSLATION_LOCALES},
            "required": list(REQUIRED_TRANSLATION_LOCALES),
            "additionalProperties": False,
        }
        required.append("translations")
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


def _normalize_phrase_translation_payload(
    value: Any,
    *,
    example_count: int,
    source_usage_note: Any,
) -> dict[str, dict[str, Any]]:
    if not isinstance(value, dict):
        raise RuntimeError("OpenAI-compatible enrichment payload field 'translations' must be an object keyed by locale")

    normalized: dict[str, dict[str, Any]] = {}
    for locale in REQUIRED_TRANSLATION_LOCALES:
        locale_payload = value.get(locale)
        if not isinstance(locale_payload, dict):
            raise RuntimeError(
                f"OpenAI-compatible enrichment payload field 'translations' must include required locale '{locale}'"
            )
        definition = require_non_empty_string(locale_payload.get("definition"), field=f"translations.{locale}.definition")
        examples = locale_payload.get("examples")
        if not isinstance(examples, list) or not examples:
            raise RuntimeError(
                f"OpenAI-compatible enrichment payload field 'translations.{locale}.examples' must be a non-empty list of strings"
            )
        normalized_examples = [
            require_non_empty_string(example, field=f"translations.{locale}.examples[{index}]")
            for index, example in enumerate(examples)
        ]
        if len(normalized_examples) < example_count:
            normalized_examples.extend([normalized_examples[-1]] * (example_count - len(normalized_examples)))
        elif len(normalized_examples) > example_count:
            normalized_examples = normalized_examples[:example_count]
        normalized[locale] = {
            "definition": definition,
            "usage_note": _normalize_phrase_translation_usage_note(
                source_usage_note=source_usage_note,
                translated_usage_note=locale_payload.get("usage_note"),
                locale=locale,
            ),
            "examples": normalized_examples,
        }
    return normalized


def build_phrase_enrichment_response_schema(*, include_translations: bool = True) -> dict[str, Any]:
    return {
        "name": "lexicon_enrichment_phrase",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "phrase_kind": {"type": "string", "enum": sorted(ALLOWED_PHRASE_KINDS)},
                "senses": {"type": "array", "items": _sense_schema(include_translations=include_translations), "minItems": 1, "maxItems": 2},
                "confidence": {"type": "number"},
            },
            "required": [
                "phrase_kind",
                "senses",
                "confidence",
            ],
            "additionalProperties": False,
        },
    }


def _normalize_phrase_translation_usage_note(*, source_usage_note: Any, translated_usage_note: Any, locale: str) -> str:
    source_has_usage_note = isinstance(source_usage_note, str) and bool(source_usage_note.strip())
    if not source_has_usage_note:
        if translated_usage_note is None:
            return ""
        if isinstance(translated_usage_note, str):
            return validate_no_control_characters(
                translated_usage_note.strip(),
                field=f"translations.{locale}.usage_note",
            )
        raise RuntimeError(
            f"OpenAI-compatible enrichment payload field 'translations.{locale}.usage_note' must be a string or null"
        )

    if not isinstance(translated_usage_note, str) or not translated_usage_note.strip():
        raise RuntimeError(
            "OpenAI-compatible enrichment payload field "
            f"'translations.{locale}.usage_note' missing_translated_usage_note_with_source_note_present"
        )
    return validate_no_control_characters(
        translated_usage_note.strip(),
        field=f"translations.{locale}.usage_note",
    )


def normalize_phrase_enrichment_payload(response: dict[str, Any], *, include_translations: bool = True) -> dict[str, Any]:
    if not isinstance(response, dict):
        raise RuntimeError("OpenAI-compatible endpoint returned a non-object phrase enrichment payload")

    normalized = dict(response)
    normalized["phrase_kind"] = require_non_empty_string(response.get("phrase_kind"), field="phrase_kind")
    if normalized["phrase_kind"] not in ALLOWED_PHRASE_KINDS:
        raise RuntimeError(f"OpenAI-compatible enrichment payload field 'phrase_kind' must be one of {sorted(ALLOWED_PHRASE_KINDS)}")
    normalized["confidence"] = normalize_confidence(response.get("confidence"))
    senses = response.get("senses")
    if not isinstance(senses, list) or not senses:
        raise RuntimeError("OpenAI-compatible enrichment payload field 'senses' must be a non-empty list")
    if len(senses) > 2:
        raise RuntimeError("OpenAI-compatible enrichment payload field 'senses' must include at most 2 sense items")
    normalized_senses: list[dict[str, Any]] = []
    for index, sense in enumerate(senses):
        if not isinstance(sense, dict):
            raise RuntimeError(f"OpenAI-compatible enrichment payload field 'senses[{index}]' must be an object")
        examples = normalize_examples(sense.get("examples"))
        source_usage_note = sense.get("usage_note")
        normalized_senses.append(
            {
                "definition": require_non_empty_string(sense.get("definition"), field=f"senses[{index}].definition"),
                "part_of_speech": require_non_empty_string(sense.get("part_of_speech"), field=f"senses[{index}].part_of_speech"),
                "examples": examples,
                "grammar_patterns": normalize_string_list_field(
                    sense.get("grammar_patterns"),
                    field=f"senses[{index}].grammar_patterns",
                ),
                "usage_note": (
                    require_non_empty_string(sense.get("usage_note"), field=f"senses[{index}].usage_note")
                    if sense.get("usage_note") is not None
                    else None
                ),
                "translations": (
                    _normalize_phrase_translation_payload(
                        sense.get("translations"),
                        example_count=len(examples),
                        source_usage_note=source_usage_note,
                    )
                    if include_translations
                    else {}
                ),
            }
        )
    normalized["senses"] = normalized_senses
    return normalized
