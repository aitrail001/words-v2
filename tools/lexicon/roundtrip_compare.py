from __future__ import annotations

from copy import deepcopy
from typing import Any, Iterable


def row_identity_key(row: dict[str, Any]) -> str:
    entry_type = str(row.get("entry_type") or "word").strip() or "word"
    language = str(row.get("language") or "en").strip() or "en"
    if entry_type == "word":
        token = str(row.get("word") or "").strip().lower()
        return f"word:{token}:{language}"
    if entry_type in {"phrase", "reference"}:
        token = str(row.get("normalized_form") or row.get("word") or "").strip().lower()
        return f"{entry_type}:{token}:{language}"
    token = str(row.get("normalized_form") or row.get("word") or "").strip().lower()
    return f"{entry_type}:{token}:{language}"


def normalize_roundtrip_row(row: dict[str, Any]) -> dict[str, Any]:
    normalized = deepcopy(row)
    forms = normalized.get("forms")
    if isinstance(forms, dict):
        verb_forms = forms.get("verb_forms")
        if isinstance(verb_forms, dict):
            forms["verb_forms"] = {
                key: value
                for key, value in verb_forms.items()
                if str(value or "").strip()
            }
    return normalized


def _translation_stats(row: dict[str, Any]) -> dict[str, int]:
    translation_definition_count = 0
    translation_example_count = 0
    translation_example_sense_count = 0
    for sense in row.get("senses") or []:
        translations = (sense or {}).get("translations") or {}
        sense_has_examples = False
        for payload in translations.values():
            if not isinstance(payload, dict):
                continue
            definition = str(payload.get("definition") or "").strip()
            if definition:
                translation_definition_count += 1
            translated_examples = [
                str(item or "").strip()
                for item in (payload.get("examples") or [])
                if str(item or "").strip()
            ]
            translation_example_count += len(translated_examples)
            if translated_examples:
                sense_has_examples = True
        if sense_has_examples:
            translation_example_sense_count += 1
    return {
        "translation_definition_count": translation_definition_count,
        "translation_example_count": translation_example_count,
        "translation_example_sense_count": translation_example_sense_count,
    }


def _translation_stats_for_rows(rows: Iterable[dict[str, Any]]) -> dict[str, int]:
    totals = {
        "translation_definition_count": 0,
        "translation_example_count": 0,
        "translation_example_sense_count": 0,
    }
    for row in rows:
        stats = _translation_stats(row)
        for key, value in stats.items():
            totals[key] += value
    return totals


def compare_compiled_rows(expected_rows: Iterable[dict[str, Any]], actual_rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    expected_map = {row_identity_key(row): normalize_roundtrip_row(row) for row in expected_rows}
    actual_map = {row_identity_key(row): normalize_roundtrip_row(row) for row in actual_rows}

    missing_row_ids = sorted(set(expected_map) - set(actual_map))
    added_row_ids = sorted(set(actual_map) - set(expected_map))
    shared_row_ids = sorted(set(expected_map) & set(actual_map))

    missing_top_level_keys: dict[str, list[str]] = {}
    added_top_level_keys: dict[str, list[str]] = {}
    mismatched_rows: list[str] = []
    translation_definition_diffs: list[str] = []
    translation_example_diffs: list[str] = []
    translation_missing_locales: list[str] = []
    translation_added_locales: list[str] = []

    for row_id in shared_row_ids:
        expected_row = expected_map[row_id]
        actual_row = actual_map[row_id]
        expected_keys = set(expected_row.keys())
        actual_keys = set(actual_row.keys())
        if expected_keys - actual_keys:
            missing_top_level_keys[row_id] = sorted(expected_keys - actual_keys)
        if actual_keys - expected_keys:
            added_top_level_keys[row_id] = sorted(actual_keys - expected_keys)
        if expected_row != actual_row:
            mismatched_rows.append(row_id)

        expected_senses = expected_row.get("senses") or []
        actual_senses = actual_row.get("senses") or []
        for index, expected_sense in enumerate(expected_senses):
            actual_sense = actual_senses[index] if index < len(actual_senses) else {}
            expected_translations = (expected_sense or {}).get("translations") or {}
            actual_translations = (actual_sense or {}).get("translations") or {}
            expected_locales = set(expected_translations.keys())
            actual_locales = set(actual_translations.keys())
            for locale in sorted(expected_locales - actual_locales):
                translation_missing_locales.append(f"{row_id}:sense[{index}]:{locale}")
            for locale in sorted(actual_locales - expected_locales):
                translation_added_locales.append(f"{row_id}:sense[{index}]:{locale}")
            for locale in sorted(expected_locales & actual_locales):
                expected_payload = expected_translations.get(locale) or {}
                actual_payload = actual_translations.get(locale) or {}
                if str(expected_payload.get("definition") or "").strip() != str(actual_payload.get("definition") or "").strip():
                    translation_definition_diffs.append(f"{row_id}:sense[{index}]:{locale}")
                expected_examples = [
                    str(item or "").strip()
                    for item in (expected_payload.get("examples") or [])
                    if str(item or "").strip()
                ]
                actual_examples = [
                    str(item or "").strip()
                    for item in (actual_payload.get("examples") or [])
                    if str(item or "").strip()
                ]
                if expected_examples != actual_examples:
                    translation_example_diffs.append(f"{row_id}:sense[{index}]:{locale}")

    expected_stats = _translation_stats_for_rows(expected_map.values())
    actual_stats = _translation_stats_for_rows(actual_map.values())

    return {
        "row_count": len(expected_map),
        "exported_row_count": len(actual_map),
        "missing_row_ids": missing_row_ids,
        "added_row_ids": added_row_ids,
        "missing_top_level_keys": missing_top_level_keys,
        "added_top_level_keys": added_top_level_keys,
        "mismatched_rows": mismatched_rows,
        "translation_missing_locales": translation_missing_locales,
        "translation_added_locales": translation_added_locales,
        "translation_definition_diffs": translation_definition_diffs,
        "translation_example_diffs": translation_example_diffs,
        **expected_stats,
        **{f"exported_{key}": value for key, value in actual_stats.items()},
    }
