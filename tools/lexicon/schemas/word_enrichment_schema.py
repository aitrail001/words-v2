"""Word enrichment schema helpers."""

from __future__ import annotations

from typing import Any

from tools.lexicon.contracts import (
    ALLOWED_CEFR_LEVELS,
    ALLOWED_REGISTERS,
    ALLOWED_WORD_DECISIONS,
    ALLOWED_WORD_SENSE_KINDS,
    WORD_STRING_LIST_FIELDS,
    normalize_confidence,
    normalize_confusable_words,
    normalize_examples,
    normalize_forms,
    normalize_optional_enum,
    normalize_string_list_field,
    normalize_translation_payload,
    require_non_empty_string,
    REQUIRED_TRANSLATION_LOCALES,
)
from tools.lexicon.text_safety import validate_no_control_characters

_PHONETIC_ACCENTS = ("us", "uk", "au")


def _nullable_schema(inner: dict[str, Any]) -> dict[str, Any]:
    return {"anyOf": [inner, {"type": "null"}]}


def _phonetic_variant_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "ipa": {"type": "string"},
            "confidence": {"type": "number"},
        },
        "required": ["ipa", "confidence"],
        "additionalProperties": False,
    }


def _phonetics_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {accent: _phonetic_variant_schema() for accent in _PHONETIC_ACCENTS},
        "required": list(_PHONETIC_ACCENTS),
        "additionalProperties": False,
    }


def _base_enrichment_item_schema(*, include_translations: bool = True) -> dict[str, Any]:
    verb_forms_schema = {
        "type": "object",
        "properties": {
            "base": {"type": "string"},
            "third_person_singular": {"type": "string"},
            "past": {"type": "string"},
            "past_participle": {"type": "string"},
            "gerund": {"type": "string"},
        },
        "required": [
            "base",
            "third_person_singular",
            "past",
            "past_participle",
            "gerund",
        ],
        "additionalProperties": False,
    }

    example_schema = {
        "type": "object",
        "properties": {
            "sentence": {"type": "string"},
            "difficulty": {"type": "string", "enum": sorted(ALLOWED_CEFR_LEVELS)},
        },
        "required": ["sentence", "difficulty"],
        "additionalProperties": False,
    }
    translation_schema = {
        "type": "object",
        "properties": {
            "definition": {"type": "string"},
            "usage_note": {"type": "string"},
            "examples": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["definition", "usage_note", "examples"],
        "additionalProperties": False,
    }
    properties = {
        "definition": {"type": "string"},
        "examples": {"type": "array", "items": example_schema, "minItems": 1},
        "cefr_level": _nullable_schema({"type": "string", "enum": sorted(ALLOWED_CEFR_LEVELS)}),
        "primary_domain": _nullable_schema({"type": "string"}),
        "secondary_domains": _nullable_schema({"type": "array", "items": {"type": "string"}}),
        "register": _nullable_schema({"type": "string", "enum": sorted(ALLOWED_REGISTERS)}),
        "synonyms": _nullable_schema({"type": "array", "items": {"type": "string"}}),
        "antonyms": _nullable_schema({"type": "array", "items": {"type": "string"}}),
        "collocations": _nullable_schema({"type": "array", "items": {"type": "string"}}),
        "grammar_patterns": _nullable_schema({"type": "array", "items": {"type": "string"}}),
        "usage_note": _nullable_schema({"type": "string"}),
        "forms": _nullable_schema({
            "type": "object",
            "properties": {
                "plural_forms": {"type": "array", "items": {"type": "string"}},
                "verb_forms": verb_forms_schema,
                "comparative": _nullable_schema({"type": "string"}),
                "superlative": _nullable_schema({"type": "string"}),
                "derivations": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["plural_forms", "verb_forms", "comparative", "superlative", "derivations"],
            "additionalProperties": False,
        }),
        "confusable_words": _nullable_schema({
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "word": {"type": "string"},
                    "note": {"type": "string"},
                },
                "required": ["word", "note"],
                "additionalProperties": False,
            },
        }),
        "confidence": {"type": "number"},
    }
    if include_translations:
        properties["translations"] = {
            "type": "object",
            "properties": {
                locale: translation_schema for locale in REQUIRED_TRANSLATION_LOCALES
            },
            "required": list(REQUIRED_TRANSLATION_LOCALES),
            "additionalProperties": False,
        }
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties.keys()),
        "additionalProperties": False,
    }


def build_single_sense_response_schema(*, include_translations: bool = True) -> dict[str, Any]:
    return {
        "name": "lexicon_enrichment_single_sense",
        "strict": True,
        "schema": _base_enrichment_item_schema(include_translations=include_translations),
    }


def build_word_enrichment_response_schema(*, include_translations: bool = True) -> dict[str, Any]:
    item_schema = dict(_base_enrichment_item_schema(include_translations=include_translations))
    item_properties = dict(item_schema["properties"])
    item_properties["part_of_speech"] = {"type": "string"}
    item_properties["sense_kind"] = {"type": "string", "enum": sorted(ALLOWED_WORD_SENSE_KINDS)}
    item_required = ["part_of_speech", "sense_kind", *list(item_schema["properties"].keys())]
    item_schema["properties"] = item_properties
    item_schema["required"] = item_required
    return {
        "name": "lexicon_enrichment_word",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "decision": {"type": "string", "enum": sorted(ALLOWED_WORD_DECISIONS)},
                "discard_reason": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                "base_word": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                "phonetics": {"anyOf": [_phonetics_schema(), {"type": "null"}]},
                "senses": {
                    "type": "array",
                    "minItems": 0,
                    "items": item_schema,
                },
            },
            "required": ["decision", "discard_reason", "base_word", "phonetics", "senses"],
            "additionalProperties": False,
        },
    }


def normalize_phonetics_payload(value: Any) -> dict[str, dict[str, Any]] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise RuntimeError("OpenAI-compatible word enrichment payload field 'phonetics' must be an object or null")
    normalized: dict[str, dict[str, Any]] = {}
    for accent in _PHONETIC_ACCENTS:
        accent_payload = value.get(accent)
        if not isinstance(accent_payload, dict):
            raise RuntimeError(f"OpenAI-compatible word enrichment payload field 'phonetics.{accent}' must be an object")
        normalized[accent] = {
            "ipa": require_non_empty_string(accent_payload.get("ipa"), field=f"phonetics.{accent}.ipa"),
            "confidence": normalize_confidence(accent_payload.get("confidence")),
        }
    return normalized


def normalize_word_enrichment_payload(response: dict[str, Any], *, include_translations: bool = True) -> dict[str, Any]:
    if not isinstance(response, dict):
        raise RuntimeError("OpenAI-compatible endpoint returned a non-object enrichment payload")

    normalized = dict(response)
    normalized["definition"] = require_non_empty_string(response.get("definition"), field="definition")
    normalized["examples"] = normalize_examples(response.get("examples"))
    normalized["confidence"] = normalize_confidence(response.get("confidence"))
    normalized["cefr_level"] = normalize_optional_enum(response.get("cefr_level"), field="cefr_level", allowed=ALLOWED_CEFR_LEVELS)
    normalized["register"] = normalize_optional_enum(response.get("register"), field="register", allowed=ALLOWED_REGISTERS)
    for field in WORD_STRING_LIST_FIELDS:
        normalized[field] = normalize_string_list_field(response.get(field), field=field)
    normalized["forms"] = normalize_forms(response.get("forms"))
    normalized["confusable_words"] = normalize_confusable_words(response.get("confusable_words"))
    primary_domain = response.get("primary_domain")
    if primary_domain is not None and not isinstance(primary_domain, str):
        raise RuntimeError("OpenAI-compatible enrichment payload field 'primary_domain' must be a string or null")
    if isinstance(primary_domain, str):
        validate_no_control_characters(primary_domain, field="primary_domain")
    if include_translations:
        normalized["translations"] = normalize_translation_payload(
            response.get("translations"),
            example_count=len(normalized["examples"]),
        )
    else:
        normalized["translations"] = {}
    return normalized
