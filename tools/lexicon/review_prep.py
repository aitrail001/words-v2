"""Shared review-preparation helpers for realtime and batch lexicon artifacts."""

from __future__ import annotations

from typing import Any, Iterable

from tools.lexicon.validate import validate_compiled_record


def _warning_labels(row: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    if not row.get("source_provenance"):
        warnings.append("missing_source_provenance")

    entry_type = str(row.get("entry_type") or "").strip().lower()
    senses = row.get("senses")
    if entry_type in {"word", "phrase"} and isinstance(senses, list) and senses:
        if all(not (sense.get("examples") or []) for sense in senses if isinstance(sense, dict)):
            warnings.append("missing_examples")

    if entry_type == "reference" and row.get("translation_mode") == "localized":
        if not row.get("localizations"):
            warnings.append("missing_localizations")
    return warnings


def _review_summary(row: dict[str, Any]) -> dict[str, Any]:
    senses = row.get("senses")
    forms = row.get("forms")
    confusable_words = row.get("confusable_words")
    provenance = row.get("source_provenance")
    return {
        "sense_count": len(senses) if isinstance(senses, list) else 0,
        "form_variant_count": _form_variant_count(forms if isinstance(forms, dict) else {}),
        "confusable_count": len(confusable_words) if isinstance(confusable_words, list) else 0,
        "provenance_sources": _provenance_sources(provenance if isinstance(provenance, list) else []),
        "primary_definition": _primary_definition(senses if isinstance(senses, list) else []),
        "primary_example": _primary_example(senses if isinstance(senses, list) else []),
    }


def _form_variant_count(forms: dict[str, Any]) -> int:
    count = 0
    plural_forms = forms.get("plural_forms")
    if isinstance(plural_forms, list):
        count += len(plural_forms)

    verb_forms = forms.get("verb_forms")
    if isinstance(verb_forms, dict):
        for value in verb_forms.values():
            if isinstance(value, list):
                count += len(value)
            elif value:
                count += 1

    derivations = forms.get("derivations")
    if isinstance(derivations, list):
        count += len(derivations)

    if forms.get("comparative"):
        count += 1
    if forms.get("superlative"):
        count += 1
    return count


def _provenance_sources(source_provenance: list[Any]) -> list[str]:
    sources: list[str] = []
    for item in source_provenance:
        if isinstance(item, dict):
            value = str(item.get("source") or "").strip()
        else:
            value = str(item or "").strip()
        if value:
            sources.append(value)
    return sources


def _primary_definition(senses: list[Any]) -> str | None:
    for sense in senses:
        if not isinstance(sense, dict):
            continue
        for key in ("definition", "gloss", "summary"):
            value = str(sense.get(key) or "").strip()
            if value:
                return value
    return None


def _primary_example(senses: list[Any]) -> str | None:
    for sense in senses:
        if not isinstance(sense, dict):
            continue
        examples = sense.get("examples")
        if not isinstance(examples, list):
            continue
        for example in examples:
            if isinstance(example, dict):
                value = str(example.get("sentence") or example.get("text") or "").strip()
            else:
                value = str(example or "").strip()
            if value:
                return value
    return None


def _compiled_payload_from_row(row: dict[str, Any]) -> dict[str, Any] | None:
    payload = row.get("compiled_payload")
    if isinstance(payload, dict):
        return payload
    if "schema_version" in row and "entry_id" in row and "entry_type" in row:
        return row
    return None


def _resolve_entry_type(row: dict[str, Any], compiled_payload: dict[str, Any] | None) -> str | None:
    entry_type = row.get("entry_type") or row.get("entry_kind")
    if entry_type is None and compiled_payload is not None:
        entry_type = compiled_payload.get("entry_type")
    normalized = str(entry_type or "").strip().lower()
    return normalized or None


def build_review_prep_rows(rows: Iterable[dict[str, Any]], *, origin: str) -> list[dict[str, Any]]:
    prepared_rows: list[dict[str, Any]] = []
    for raw_row in rows:
        row = dict(raw_row)
        compiled_payload = _compiled_payload_from_row(row)
        entry_type = _resolve_entry_type(row, compiled_payload)
        entry_id = str(row.get("entry_id") or (compiled_payload or {}).get("entry_id") or "").strip()

        warning_labels: list[str] = []
        validation_errors: list[str] = []
        review_summary = {
            "sense_count": 0,
            "form_variant_count": 0,
            "provenance_sources": [],
            "primary_definition": None,
        }
        if compiled_payload is not None:
            validation_errors = validate_compiled_record(compiled_payload)
            warning_labels = _warning_labels(compiled_payload)
            review_summary = _review_summary(compiled_payload)

        status_value = str(row.get("status") or "").strip().lower()
        validation_status_value = str(row.get("validation_status") or "").strip().lower()
        status_reasons: list[str] = []
        if status_value and status_value != "accepted":
            status_reasons.append(f"status={status_value}")
        if validation_status_value and validation_status_value != "valid":
            status_reasons.append(f"validation_status={validation_status_value}")

        reasons = [*validation_errors, *status_reasons]
        verdict = "fail" if reasons or warning_labels else "pass"
        review_notes = row.get("error_detail")
        if review_notes is None and validation_errors:
            review_notes = validation_errors[0]
        review_priority = 200 if verdict == "fail" else 100

        prepared_rows.append(
            {
                "custom_id": row.get("custom_id"),
                "entry_kind": row.get("entry_kind") or entry_type,
                "entry_type": entry_type,
                "entry_id": entry_id,
                "normalized_form": row.get("normalized_form") or (compiled_payload or {}).get("normalized_form"),
                "origin": origin,
                "verdict": verdict,
                "confidence": 1.0 if verdict == "pass" else 0.0,
                "reasons": reasons,
                "review_notes": review_notes,
                "review_priority": review_priority,
                "warning_labels": warning_labels,
                "warning_count": len(warning_labels),
                "review_summary": review_summary,
                "compiled_payload": compiled_payload,
            }
        )
    return prepared_rows


def build_review_queue_rows(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    queue_rows: list[dict[str, Any]] = []
    for row in rows:
        verdict = str(row.get("verdict") or "").strip().lower()
        if verdict == "pass":
            continue
        queue_rows.append(
            {
                "custom_id": row.get("custom_id"),
                "entry_kind": row.get("entry_kind") or row.get("entry_type"),
                "entry_id": row.get("entry_id"),
                "review_status": "needs_review",
                "review_notes": row.get("review_notes"),
                "review_priority": row.get("review_priority", 200),
                "warning_labels": row.get("warning_labels") or [],
            }
        )
    return queue_rows


def summarize_review_prep_rows(rows: Iterable[dict[str, Any]]) -> dict[str, int]:
    summary = {"total": 0, "pass": 0, "fail": 0, "warning": 0}
    for row in rows:
        summary["total"] += 1
        verdict = str(row.get("verdict") or "").strip().lower()
        if verdict in {"pass", "fail"}:
            summary[verdict] += 1
        if row.get("warning_labels"):
            summary["warning"] += 1
    return summary
