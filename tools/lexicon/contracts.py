"""Shared contract constants and helpers for lexicon batch/scaffold work."""

from __future__ import annotations

import math
from typing import Any

from tools.lexicon.models import SenseExample

ALLOWED_CEFR_LEVELS = ("A1", "A2", "B1", "B2", "C1", "C2")
ALLOWED_REGISTERS = ("neutral", "formal", "informal")
REQUIRED_TRANSLATION_LOCALES = ("zh-Hans", "es", "ar", "pt-BR", "ja")
ALLOWED_WORD_DECISIONS = ("discard", "keep_derived_special", "keep_standard")
ALLOWED_WORD_SENSE_KINDS = ("standard_meaning", "base_form_reference", "special_meaning")
WORD_STRING_LIST_FIELDS = ("secondary_domains", "synonyms", "antonyms", "collocations", "grammar_patterns")
ALLOWED_PHRASE_KINDS = ("collocation", "idiom", "multiword_expression", "phrasal_verb")
ALLOWED_TRANSLATION_MODES = ("keep_original", "localized_display", "localized_translation")
ALLOWED_REFERENCE_TYPES = (
    "abbreviation",
    "country",
    "demonym",
    "fictional_character",
    "landmark",
    "name",
    "person",
    "place",
    "region",
    "title",
)
ALLOWED_QC_VERDICTS = ("accept", "needs_review", "reject", "repair")


def _payload_error(field: str, message: str) -> RuntimeError:
    return RuntimeError(f"OpenAI-compatible enrichment payload field '{field}' {message}")


def require_non_empty_string(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise _payload_error(field, "must be a non-empty string")
    return value.strip()


def normalize_optional_enum(value: Any, *, field: str, allowed: tuple[str, ...] | list[str] | set[str]) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise _payload_error(field, f"must be one of {sorted(allowed)}")
    normalized = value.strip()
    if normalized not in allowed:
        raise _payload_error(field, f"must be one of {sorted(allowed)}")
    return normalized


def normalize_string_list_field(value: Any, *, field: str) -> list[str] | None:
    if value is None:
        return None
    if not isinstance(value, list):
        raise _payload_error(field, "must be a list of non-empty strings")

    normalized: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str):
            raise _payload_error(f"{field}[{index}]", "must be a non-empty string")
        candidate = item.strip()
        if not candidate:
            continue
        normalized.append(candidate)
    return normalized


def normalize_examples(value: Any) -> list[SenseExample]:
    if not isinstance(value, list) or not value:
        raise _payload_error("examples", "must be a non-empty list")

    examples: list[SenseExample] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise _payload_error(f"examples[{index}]", "must be an object")

        sentence = require_non_empty_string(item.get("sentence"), field=f"examples[{index}].sentence")
        difficulty_value = item.get("difficulty")
        if difficulty_value is None:
            difficulty = "B1"
        elif isinstance(difficulty_value, str) and difficulty_value.strip():
            difficulty = difficulty_value.strip()
        else:
            raise _payload_error(f"examples[{index}].difficulty", "must be a non-empty string when provided")

        if difficulty not in ALLOWED_CEFR_LEVELS:
            raise _payload_error(f"examples[{index}].difficulty", f"must be one of {sorted(ALLOWED_CEFR_LEVELS)}")

        examples.append(SenseExample(sentence=sentence, difficulty=difficulty))

    return examples


def normalize_forms(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise _payload_error("forms", "must be an object")

    required_keys = {"plural_forms", "verb_forms", "comparative", "superlative", "derivations"}
    missing = sorted(required_keys - set(value.keys()))
    if missing:
        raise _payload_error("forms", f"is missing required keys {missing}")

    plural_forms = normalize_string_list_field(value.get("plural_forms"), field="forms.plural_forms")
    derivations = normalize_string_list_field(value.get("derivations"), field="forms.derivations")

    verb_forms = value.get("verb_forms")
    if not isinstance(verb_forms, dict):
        raise _payload_error("forms.verb_forms", "must be an object")
    normalized_verb_forms: dict[str, str] = {}
    for subfield, subvalue in verb_forms.items():
        if not isinstance(subfield, str) or not subfield.strip():
            raise _payload_error("forms.verb_forms", "must use non-empty string keys")
        if not isinstance(subvalue, str):
            raise _payload_error(f"forms.verb_forms.{subfield}", "must be a string")
        normalized_verb_forms[subfield] = subvalue.strip()

    comparative = value.get("comparative")
    if comparative is not None and not isinstance(comparative, str):
        raise _payload_error("forms.comparative", "must be a string or null")

    superlative = value.get("superlative")
    if superlative is not None and not isinstance(superlative, str):
        raise _payload_error("forms.superlative", "must be a string or null")

    return {
        "plural_forms": plural_forms or [],
        "verb_forms": normalized_verb_forms,
        "comparative": comparative.strip() if isinstance(comparative, str) else None,
        "superlative": superlative.strip() if isinstance(superlative, str) else None,
        "derivations": derivations or [],
    }


def normalize_confusable_words(value: Any) -> list[dict[str, str]] | None:
    if value is None:
        return None
    if not isinstance(value, list):
        raise _payload_error("confusable_words", "must be a list of objects")

    normalized: list[dict[str, str]] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise _payload_error(f"confusable_words[{index}]", "must be an object")
        word = require_non_empty_string(item.get("word"), field=f"confusable_words[{index}].word")
        note_value = item.get("note")
        if not isinstance(note_value, str):
            raise _payload_error(f"confusable_words[{index}].note", "must be a string")
        normalized.append({"word": word, "note": note_value.strip()})
    return normalized


def normalize_confidence(value: Any) -> float:
    if isinstance(value, str):
        stripped = value.strip()
        try:
            value = float(stripped)
        except ValueError as exc:
            raise _payload_error("confidence", "must be a numeric value between 0 and 1") from exc

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _payload_error("confidence", "must be a numeric value between 0 and 1")

    confidence = float(value)
    if not math.isfinite(confidence) or not 0.0 <= confidence <= 1.0:
        raise _payload_error("confidence", "must be a finite number between 0 and 1")

    return confidence


def normalize_translation_payload(value: Any, *, example_count: int) -> dict[str, dict[str, Any]]:
    if not isinstance(value, dict):
        raise _payload_error("translations", "must be an object keyed by locale")

    normalized: dict[str, dict[str, Any]] = {}
    for locale in REQUIRED_TRANSLATION_LOCALES:
        locale_payload = value.get(locale)
        if not isinstance(locale_payload, dict):
            raise RuntimeError(
                f"OpenAI-compatible enrichment payload field 'translations' must include required locale '{locale}'"
            )
        definition = require_non_empty_string(locale_payload.get("definition"), field=f"translations.{locale}.definition")
        usage_note = require_non_empty_string(locale_payload.get("usage_note"), field=f"translations.{locale}.usage_note")
        examples = locale_payload.get("examples")
        if not isinstance(examples, list) or not examples:
            raise _payload_error(f"translations.{locale}.examples", "must be a non-empty list of strings")
        normalized_examples: list[str] = []
        for index, item in enumerate(examples):
            if not isinstance(item, str) or not item.strip():
                raise _payload_error(f"translations.{locale}.examples[{index}]", "must be a non-empty string")
            normalized_examples.append(item.strip())
        if len(normalized_examples) != example_count:
            raise _payload_error(
                f"translations.{locale}.examples",
                f"must contain exactly {example_count} item(s) to align with the English examples",
            )
        normalized[locale] = {
            "definition": definition,
            "usage_note": usage_note,
            "examples": normalized_examples,
        }

    return normalized
