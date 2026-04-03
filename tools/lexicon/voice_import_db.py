from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterable
import json

from tools.lexicon.import_db import _ensure_backend_path

create_engine = None
Session = None
get_settings = None


@dataclass(frozen=True)
class VoiceImportSummary:
    created_assets: int = 0
    updated_assets: int = 0
    skipped_rows: int = 0
    missing_words: int = 0
    missing_meanings: int = 0
    missing_examples: int = 0
    failed_rows: int = 0


@dataclass(frozen=True)
class VoiceManifestGroup:
    entry_type: str
    lexical_text: str
    language: str
    rows: list[dict[str, Any]]


def _increment(summary: VoiceImportSummary, **changes: int) -> VoiceImportSummary:
    values = summary.__dict__.copy()
    for key, delta in changes.items():
        values[key] = values.get(key, 0) + delta
    return VoiceImportSummary(**values)


def _merge_summaries(left: VoiceImportSummary, right: VoiceImportSummary) -> VoiceImportSummary:
    values = left.__dict__.copy()
    for key, value in right.__dict__.items():
        values[key] = int(values.get(key, 0)) + int(value)
    return VoiceImportSummary(**values)


def load_voice_manifest_rows(path: str | Path) -> list[dict[str, Any]]:
    return list(iter_voice_manifest_rows(path))


def iter_voice_manifest_rows(path: str | Path) -> Iterable[dict[str, Any]]:
    with Path(path).open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            payload = json.loads(line)
            if isinstance(payload, dict):
                yield payload


def _group_sort_key(row: dict[str, Any], original_index: int) -> tuple[int, int]:
    scope_rank = {
        "word": 0,
        "definition": 1,
        "example": 2,
    }.get(str(row.get("content_scope") or "").strip().lower(), 99)
    return scope_rank, original_index


def group_voice_manifest_rows(rows: list[dict[str, Any]]) -> list[VoiceManifestGroup]:
    buckets: dict[tuple[str, str, str], list[tuple[int, dict[str, Any]]]] = {}
    for original_index, row in enumerate(rows):
        key = (
            str(row.get("entry_type") or "word").strip().lower() or "word",
            str(row.get("word") or "").strip().lower(),
            str(row.get("language") or "en").strip().lower() or "en",
        )
        buckets.setdefault(key, []).append((original_index, row))

    groups: list[VoiceManifestGroup] = []
    for (entry_type, lexical_text, language), indexed_rows in buckets.items():
        ordered_rows = [
            row
            for index, row in sorted(
                indexed_rows,
                key=lambda item: _group_sort_key(item[1], item[0]),
            )
        ]
        groups.append(
            VoiceManifestGroup(
                entry_type=entry_type,
                lexical_text=lexical_text,
                language=language,
                rows=ordered_rows,
            )
        )
    return groups


def _manifest_group_index_path(path: str | Path) -> Path:
    resolved = Path(path)
    return resolved.with_name(f"{resolved.name}.groups.index.json")


def _build_voice_manifest_group_index(path: str | Path) -> dict[str, Any]:
    resolved = Path(path).resolve()
    stat = resolved.stat()
    buckets: dict[tuple[str, str, str], list[tuple[int, int]]] = {}
    row_count = 0
    for original_index, row in enumerate(iter_voice_manifest_rows(resolved)):
        key = (
            str(row.get("entry_type") or "word").strip().lower() or "word",
            str(row.get("word") or "").strip().lower(),
            str(row.get("language") or "en").strip().lower() or "en",
        )
        scope_rank = {
            "word": 0,
            "definition": 1,
            "example": 2,
        }.get(str(row.get("content_scope") or "").strip().lower(), 99)
        buckets.setdefault(key, []).append((original_index, scope_rank))
        row_count += 1

    groups: list[dict[str, Any]] = []
    for (entry_type, lexical_text, language), indexed_rows in buckets.items():
        ordered_row_indices = [index for index, _rank in sorted(indexed_rows, key=lambda item: (item[1], item[0]))]
        groups.append(
            {
                "entry_type": entry_type,
                "lexical_text": lexical_text,
                "language": language,
                "row_indices": ordered_row_indices,
            }
        )

    return {
        "version": 1,
        "manifest_path": str(resolved),
        "manifest_size": int(stat.st_size),
        "manifest_mtime_ns": int(stat.st_mtime_ns),
        "row_count": int(row_count),
        "groups": groups,
    }


def _load_or_build_voice_manifest_group_index(path: str | Path) -> dict[str, Any]:
    resolved = Path(path).resolve()
    index_path = _manifest_group_index_path(resolved)
    stat = resolved.stat()
    if index_path.exists():
        try:
            payload = json.loads(index_path.read_text(encoding="utf-8"))
            if (
                isinstance(payload, dict)
                and int(payload.get("version") or 0) == 1
                and str(payload.get("manifest_path") or "") == str(resolved)
                and int(payload.get("manifest_size") or -1) == int(stat.st_size)
                and int(payload.get("manifest_mtime_ns") or -1) == int(stat.st_mtime_ns)
            ):
                return payload
        except Exception:
            pass

    payload = _build_voice_manifest_group_index(resolved)
    tmp_path = index_path.with_suffix(index_path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    tmp_path.replace(index_path)
    return payload


def _load_voice_manifest_rows_by_indices(path: str | Path, indices: list[int]) -> dict[int, dict[str, Any]]:
    if not indices:
        return {}
    target_indices = set(indices)
    rows_by_index: dict[int, dict[str, Any]] = {}
    for original_index, row in enumerate(iter_voice_manifest_rows(path)):
        if original_index in target_indices:
            rows_by_index[original_index] = row
            if len(rows_by_index) >= len(target_indices):
                break
    return rows_by_index


def summarize_voice_manifest_rows(rows: Iterable[dict[str, Any]]) -> dict[str, int]:
    summary = {
        "row_count": 0,
        "generated_count": 0,
        "existing_count": 0,
        "failed_count": 0,
    }
    for row in rows:
        summary["row_count"] += 1
        status = str(row.get("status") or "").strip().lower()
        if status == "generated":
            summary["generated_count"] += 1
        elif status == "existing":
            summary["existing_count"] += 1
        elif status == "failed":
            summary["failed_count"] += 1
    return summary


def summarize_voice_manifest_rows_from_path(path: str | Path) -> dict[str, int]:
    return summarize_voice_manifest_rows(iter_voice_manifest_rows(path))


def _row_label(row: dict[str, Any]) -> str:
    for key in ("_progress_label", "word", "source_text", "entry_id"):
        value = row.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return "voice row"


def _emit_progress(
    progress_callback: Callable[..., None] | None,
    *,
    row: dict[str, Any],
    completed_rows: int,
    total_rows: int,
    label: str | None = None,
) -> None:
    if progress_callback is None:
        return
    payload = dict(row)
    if label:
        payload["_progress_label"] = label
    progress_callback(row=payload, completed_rows=completed_rows, total_rows=total_rows)


def _ensure_runtime_dependencies() -> tuple[Any, Any, Any]:
    global create_engine, Session, get_settings
    if create_engine is None or Session is None or get_settings is None:
        _ensure_backend_path()
        from sqlalchemy import create_engine as runtime_create_engine
        from sqlalchemy.orm import Session as runtime_session
        from app.core.config import get_settings as runtime_get_settings

        create_engine = runtime_create_engine
        Session = runtime_session
        get_settings = runtime_get_settings
    return create_engine, Session, get_settings


def _validate_voice_manifest_row(row: dict[str, Any], *, default_language: str) -> list[str]:
    errors: list[str] = []
    status = str(row.get("status") or "").strip().lower()
    if status not in {"generated", "existing", "failed"}:
        errors.append("status must be one of generated, existing, or failed")
    entry_type = str(row.get("entry_type") or "word").strip().lower()
    if entry_type not in {"word", "phrase"}:
        errors.append("entry_type must be word or phrase")
    content_scope = str(row.get("content_scope") or "").strip()
    if content_scope not in {"word", "definition", "example"}:
        errors.append("content_scope must be word, definition, or example")
    if not str(row.get("word") or "").strip():
        errors.append("word must be a non-empty string")
    language = str(row.get("language") or default_language or "en").strip()
    if not language:
        errors.append("language must be a non-empty string")
    if status in {"generated", "existing"}:
        for key in ("locale", "voice_role", "provider", "family", "voice_id", "profile_key", "audio_format"):
            if not str(row.get(key) or "").strip():
                errors.append(f"{key} must be a non-empty string")
    return errors


def _dry_run_voice_manifest_rows(
    rows: list[dict[str, Any]],
    *,
    default_language: str = "en",
    progress_callback: Callable[..., None] | None = None,
    error_samples_sink: list[dict[str, str]] | None = None,
    completed_rows_offset: int = 0,
    total_rows: int | None = None,
) -> dict[str, int | bool]:
    summary = summarize_voice_manifest_rows(rows)
    failed_rows = 0
    resolved_total_rows = total_rows if total_rows is not None and total_rows > 0 else len(rows)
    for index, row in enumerate(rows, start=1):
        completed_rows = completed_rows_offset + index
        label = f"Validating {completed_rows}/{resolved_total_rows}: {_row_label(row)}"
        _emit_progress(progress_callback, row=row, completed_rows=completed_rows, total_rows=resolved_total_rows, label=label)
        errors = _validate_voice_manifest_row(row, default_language=default_language)
        if not errors:
            continue
        failed_rows += 1
        if error_samples_sink is not None:
            error_samples_sink.append({"entry": _row_label(row), "error": "; ".join(errors)})
    return {
        **summary,
        "dry_run": True,
        "failed_rows": failed_rows,
        "skipped_rows": 0,
    }


def _parse_timestamp(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _find_word(session: Any, word_model: type, *, word: str, language: str) -> Any | None:
    from sqlalchemy import select

    return session.execute(
        select(word_model).where(word_model.word == word, word_model.language == language)
    ).scalar_one_or_none()


def _find_meaning(session: Any, meaning_model: type, *, word_id: Any, source_reference: str, order_index: int | None) -> Any | None:
    from sqlalchemy import select

    if source_reference:
        result = session.execute(
            select(meaning_model).where(meaning_model.word_id == word_id, meaning_model.source_reference == source_reference)
        ).scalar_one_or_none()
        if result is not None:
            return result
    if order_index is None:
        return None
    return session.execute(
        select(meaning_model).where(meaning_model.word_id == word_id, meaning_model.order_index == int(order_index))
    ).scalar_one_or_none()


def _find_phrase_entry(session: Any, phrase_entry_model: type, *, phrase_text: str, language: str) -> Any | None:
    from sqlalchemy import select

    return session.execute(
        select(phrase_entry_model).where(phrase_entry_model.phrase_text == phrase_text, phrase_entry_model.language == language)
    ).scalar_one_or_none()


def _find_phrase_sense(
    session: Any,
    phrase_sense_model: type,
    *,
    phrase_entry_id: Any,
    definition: str,
    order_index: int | None,
) -> Any | None:
    from sqlalchemy import select

    if definition:
        result = session.execute(
            select(phrase_sense_model).where(
                phrase_sense_model.phrase_entry_id == phrase_entry_id,
                phrase_sense_model.definition == definition,
            )
        ).scalar_one_or_none()
        if result is not None:
            return result
    if order_index is None:
        return None
    return session.execute(
        select(phrase_sense_model).where(
            phrase_sense_model.phrase_entry_id == phrase_entry_id,
            phrase_sense_model.order_index == int(order_index),
        )
    ).scalar_one_or_none()


def _find_phrase_example(
    session: Any,
    phrase_example_model: type,
    *,
    phrase_sense_id: Any,
    sentence: str,
    order_index: int | None,
) -> Any | None:
    from sqlalchemy import select

    if sentence:
        result = session.execute(
            select(phrase_example_model).where(
                phrase_example_model.phrase_sense_id == phrase_sense_id,
                phrase_example_model.sentence == sentence,
            )
        ).scalar_one_or_none()
        if result is not None:
            return result
    if order_index is None:
        return None
    return session.execute(
        select(phrase_example_model).where(
            phrase_example_model.phrase_sense_id == phrase_sense_id,
            phrase_example_model.order_index == int(order_index),
        )
    ).scalar_one_or_none()


def _find_example(session: Any, example_model: type, *, meaning_id: Any, sentence: str, order_index: int | None) -> Any | None:
    from sqlalchemy import select

    if sentence:
        result = session.execute(
            select(example_model).where(example_model.meaning_id == meaning_id, example_model.sentence == sentence)
        ).scalar_one_or_none()
        if result is not None:
            return result
    if order_index is None:
        return None
    return session.execute(
        select(example_model).where(example_model.meaning_id == meaning_id, example_model.order_index == int(order_index))
    ).scalar_one_or_none()


def _find_voice_asset(
    session: Any,
    voice_asset_model: type,
    *,
    content_scope: str,
    word_id: Any | None,
    meaning_id: Any | None,
    meaning_example_id: Any | None,
    phrase_entry_id: Any | None,
    phrase_sense_id: Any | None,
    phrase_sense_example_id: Any | None,
    locale: str,
    voice_role: str,
    provider: str,
    family: str,
    voice_id: str,
    profile_key: str,
    audio_format: str,
) -> Any | None:
    from sqlalchemy import select

    clauses = [
        voice_asset_model.content_scope == content_scope,
        voice_asset_model.locale == locale,
        voice_asset_model.voice_role == voice_role,
        voice_asset_model.provider == provider,
        voice_asset_model.family == family,
        voice_asset_model.voice_id == voice_id,
        voice_asset_model.profile_key == profile_key,
        voice_asset_model.audio_format == audio_format,
    ]
    clauses.append(voice_asset_model.word_id.is_(None) if word_id is None else voice_asset_model.word_id == word_id)
    clauses.append(voice_asset_model.meaning_id.is_(None) if meaning_id is None else voice_asset_model.meaning_id == meaning_id)
    clauses.append(
        voice_asset_model.meaning_example_id.is_(None)
        if meaning_example_id is None
        else voice_asset_model.meaning_example_id == meaning_example_id
    )
    clauses.append(
        voice_asset_model.phrase_entry_id.is_(None)
        if phrase_entry_id is None
        else voice_asset_model.phrase_entry_id == phrase_entry_id
    )
    clauses.append(
        voice_asset_model.phrase_sense_id.is_(None)
        if phrase_sense_id is None
        else voice_asset_model.phrase_sense_id == phrase_sense_id
    )
    clauses.append(
        voice_asset_model.phrase_sense_example_id.is_(None)
        if phrase_sense_example_id is None
        else voice_asset_model.phrase_sense_example_id == phrase_sense_example_id
    )
    return session.execute(select(voice_asset_model).where(*clauses)).scalar_one_or_none()


def _voice_asset_lookup_key(
    *,
    content_scope: str,
    word_id: Any | None,
    meaning_id: Any | None,
    meaning_example_id: Any | None,
    phrase_entry_id: Any | None,
    phrase_sense_id: Any | None,
    phrase_sense_example_id: Any | None,
    locale: str,
    voice_role: str,
    provider: str,
    family: str,
    voice_id: str,
    profile_key: str,
    audio_format: str,
) -> tuple[Any, ...]:
    return (
        content_scope,
        word_id,
        meaning_id,
        meaning_example_id,
        phrase_entry_id,
        phrase_sense_id,
        phrase_sense_example_id,
        locale,
        voice_role,
        provider,
        family,
        voice_id,
        profile_key,
        audio_format,
    )


def _row_language_key(row: dict[str, Any], *, default_language: str) -> str:
    return str(row.get("language") or default_language or "en").strip().lower() or "en"


def _row_word_key(row: dict[str, Any]) -> str:
    return str(row.get("word") or "").strip().lower()


def _preload_voice_import_maps(
    session: Any,
    rows: list[dict[str, Any]],
    *,
    default_language: str,
    word_model: type,
    meaning_model: type,
    meaning_example_model: type,
    phrase_entry_model: type,
    phrase_sense_model: type,
    phrase_example_model: type,
    voice_asset_model: type,
) -> tuple[
    dict[tuple[str, str], Any],
    dict[tuple[str, str], Any],
    dict[tuple[Any, str], Any],
    dict[tuple[Any, int], Any],
    dict[tuple[Any, str], Any],
    dict[tuple[Any, int], Any],
    dict[tuple[Any, str], Any],
    dict[tuple[Any, int], Any],
    dict[tuple[Any, str], Any],
    dict[tuple[Any, int], Any],
    dict[tuple[Any, ...], Any],
]:
    from sqlalchemy import func, or_, select

    word_pairs = {
        (_row_word_key(row), _row_language_key(row, default_language=default_language))
        for row in rows
        if str(row.get("entry_type") or "word").strip().lower() != "phrase" and _row_word_key(row)
    }
    phrase_pairs = {
        (_row_word_key(row), _row_language_key(row, default_language=default_language))
        for row in rows
        if str(row.get("entry_type") or "word").strip().lower() == "phrase" and _row_word_key(row)
    }

    words_by_key: dict[tuple[str, str], Any] = {}
    phrase_entries_by_key: dict[tuple[str, str], Any] = {}

    if word_pairs:
        word_texts = sorted({word for word, _language in word_pairs})
        languages = sorted({language for _word, language in word_pairs})
        word_rows = session.execute(
            select(word_model).where(
                func.lower(word_model.word).in_(word_texts),
                func.lower(word_model.language).in_(languages),
            )
        ).scalars().all()
        for word in word_rows:
            words_by_key[(str(getattr(word, "word", "")).strip().lower(), str(getattr(word, "language", "")).strip().lower())] = word

    if phrase_pairs:
        phrase_texts = sorted({phrase for phrase, _language in phrase_pairs})
        languages = sorted({language for _phrase, language in phrase_pairs})
        phrase_rows = session.execute(
            select(phrase_entry_model).where(
                func.lower(phrase_entry_model.phrase_text).in_(phrase_texts),
                func.lower(phrase_entry_model.language).in_(languages),
            )
        ).scalars().all()
        for phrase in phrase_rows:
            phrase_entries_by_key[(str(getattr(phrase, "phrase_text", "")).strip().lower(), str(getattr(phrase, "language", "")).strip().lower())] = phrase

    word_ids = sorted({getattr(word, "id") for word in words_by_key.values()})
    phrase_entry_ids = sorted({getattr(entry, "id") for entry in phrase_entries_by_key.values()})

    meanings_by_source: dict[tuple[Any, str], Any] = {}
    meanings_by_order: dict[tuple[Any, int], Any] = {}
    if word_ids:
        meaning_rows = session.execute(select(meaning_model).where(meaning_model.word_id.in_(word_ids))).scalars().all()
        for meaning in meaning_rows:
            word_id = getattr(meaning, "word_id")
            source_reference = str(getattr(meaning, "source_reference", "") or "").strip()
            if source_reference:
                meanings_by_source[(word_id, source_reference)] = meaning
            order_index = getattr(meaning, "order_index", None)
            if order_index is not None:
                meanings_by_order[(word_id, int(order_index))] = meaning

    phrase_senses_by_definition: dict[tuple[Any, str], Any] = {}
    phrase_senses_by_order: dict[tuple[Any, int], Any] = {}
    if phrase_entry_ids:
        phrase_sense_rows = session.execute(
            select(phrase_sense_model).where(phrase_sense_model.phrase_entry_id.in_(phrase_entry_ids))
        ).scalars().all()
        for phrase_sense in phrase_sense_rows:
            phrase_entry_id = getattr(phrase_sense, "phrase_entry_id")
            definition = str(getattr(phrase_sense, "definition", "") or "").strip()
            if definition:
                phrase_senses_by_definition[(phrase_entry_id, definition)] = phrase_sense
            order_index = getattr(phrase_sense, "order_index", None)
            if order_index is not None:
                phrase_senses_by_order[(phrase_entry_id, int(order_index))] = phrase_sense

    meaning_ids = sorted({getattr(meaning, "id") for meaning in meanings_by_source.values()} | {getattr(meaning, "id") for meaning in meanings_by_order.values()})
    phrase_sense_ids = sorted({getattr(sense, "id") for sense in phrase_senses_by_definition.values()} | {getattr(sense, "id") for sense in phrase_senses_by_order.values()})

    examples_by_sentence: dict[tuple[Any, str], Any] = {}
    examples_by_order: dict[tuple[Any, int], Any] = {}
    if meaning_ids:
        example_rows = session.execute(select(meaning_example_model).where(meaning_example_model.meaning_id.in_(meaning_ids))).scalars().all()
        for example in example_rows:
            meaning_id = getattr(example, "meaning_id")
            sentence = str(getattr(example, "sentence", "") or "").strip()
            if sentence:
                examples_by_sentence[(meaning_id, sentence)] = example
            order_index = getattr(example, "order_index", None)
            if order_index is not None:
                examples_by_order[(meaning_id, int(order_index))] = example

    phrase_examples_by_sentence: dict[tuple[Any, str], Any] = {}
    phrase_examples_by_order: dict[tuple[Any, int], Any] = {}
    if phrase_sense_ids:
        phrase_example_rows = session.execute(
            select(phrase_example_model).where(phrase_example_model.phrase_sense_id.in_(phrase_sense_ids))
        ).scalars().all()
        for phrase_example in phrase_example_rows:
            phrase_sense_id = getattr(phrase_example, "phrase_sense_id")
            sentence = str(getattr(phrase_example, "sentence", "") or "").strip()
            if sentence:
                phrase_examples_by_sentence[(phrase_sense_id, sentence)] = phrase_example
            order_index = getattr(phrase_example, "order_index", None)
            if order_index is not None:
                phrase_examples_by_order[(phrase_sense_id, int(order_index))] = phrase_example

    voice_assets_by_key: dict[tuple[Any, ...], Any] = {}
    voice_asset_rows: list[Any] = []

    if word_ids or phrase_entry_ids:
        word_clauses = []
        if word_ids:
            word_clauses.append(voice_asset_model.word_id.in_(word_ids))
        if phrase_entry_ids:
            word_clauses.append(voice_asset_model.phrase_entry_id.in_(phrase_entry_ids))
        voice_asset_rows.extend(
            session.execute(
                select(voice_asset_model).where(voice_asset_model.content_scope == "word", or_(*word_clauses))
            ).scalars().all()
        )

    if meaning_ids or phrase_sense_ids:
        definition_clauses = []
        if meaning_ids:
            definition_clauses.append(voice_asset_model.meaning_id.in_(meaning_ids))
        if phrase_sense_ids:
            definition_clauses.append(voice_asset_model.phrase_sense_id.in_(phrase_sense_ids))
        voice_asset_rows.extend(
            session.execute(
                select(voice_asset_model).where(voice_asset_model.content_scope == "definition", or_(*definition_clauses))
            ).scalars().all()
        )

    example_ids = sorted({getattr(example, "id") for example in examples_by_sentence.values()} | {getattr(example, "id") for example in examples_by_order.values()})
    phrase_example_ids = sorted({getattr(example, "id") for example in phrase_examples_by_sentence.values()} | {getattr(example, "id") for example in phrase_examples_by_order.values()})
    if example_ids or phrase_example_ids:
        example_clauses = []
        if example_ids:
            example_clauses.append(voice_asset_model.meaning_example_id.in_(example_ids))
        if phrase_example_ids:
            example_clauses.append(voice_asset_model.phrase_sense_example_id.in_(phrase_example_ids))
        voice_asset_rows.extend(
            session.execute(
                select(voice_asset_model).where(voice_asset_model.content_scope == "example", or_(*example_clauses))
            ).scalars().all()
        )

    for voice_asset in voice_asset_rows:
        voice_assets_by_key[_voice_asset_lookup_key(
            content_scope=str(getattr(voice_asset, "content_scope", "")).strip(),
            word_id=getattr(voice_asset, "word_id", None),
            meaning_id=getattr(voice_asset, "meaning_id", None),
            meaning_example_id=getattr(voice_asset, "meaning_example_id", None),
            phrase_entry_id=getattr(voice_asset, "phrase_entry_id", None),
            phrase_sense_id=getattr(voice_asset, "phrase_sense_id", None),
            phrase_sense_example_id=getattr(voice_asset, "phrase_sense_example_id", None),
            locale=str(getattr(voice_asset, "locale", "")).strip(),
            voice_role=str(getattr(voice_asset, "voice_role", "")).strip(),
            provider=str(getattr(voice_asset, "provider", "")).strip(),
            family=str(getattr(voice_asset, "family", "")).strip(),
            voice_id=str(getattr(voice_asset, "voice_id", "")).strip(),
            profile_key=str(getattr(voice_asset, "profile_key", "")).strip(),
            audio_format=str(getattr(voice_asset, "audio_format", "")).strip(),
        )] = voice_asset

    return (
        words_by_key,
        phrase_entries_by_key,
        meanings_by_source,
        meanings_by_order,
        phrase_senses_by_definition,
        phrase_senses_by_order,
        examples_by_sentence,
        examples_by_order,
        phrase_examples_by_sentence,
        phrase_examples_by_order,
        voice_assets_by_key,
    )


def _find_or_create_storage_policy(
    session: Any,
    storage_policy_model: type,
    *,
    source_reference: str,
    content_scope: str,
    provider: str,
    family: str,
    locale: str,
    primary_storage_kind: str,
    primary_storage_base: str,
    fallback_storage_kind: str | None = None,
    fallback_storage_base: str | None = None,
) -> Any:
    from sqlalchemy import select

    policy_key = {
        "word": "word_default",
        "definition": "definition_default",
        "example": "example_default",
    }[content_scope]
    existing = session.execute(
        select(storage_policy_model).where(storage_policy_model.policy_key == policy_key)
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    created = storage_policy_model(
        policy_key=policy_key,
        source_reference="global",
        content_scope=content_scope,
        provider="default",
        family="default",
        locale="all",
        primary_storage_kind=primary_storage_kind,
        primary_storage_base=primary_storage_base,
        fallback_storage_kind=fallback_storage_kind,
        fallback_storage_base=fallback_storage_base,
    )
    session.add(created)
    session.flush()
    return created


def import_voice_manifest_group(
    session: Any,
    rows: list[dict[str, Any]],
    *,
    default_language: str = "en",
    conflict_mode: str = "upsert",
    error_mode: str = "continue",
    progress_callback: Callable[..., None] | None = None,
    completed_rows: int = 0,
    total_rows: int | None = None,
    error_samples_sink: list[dict[str, str]] | None = None,
) -> VoiceImportSummary:
    total = total_rows if total_rows is not None else completed_rows + len(rows)
    try:
        return import_voice_manifest_rows(
            session,
            rows,
            default_language=default_language,
            conflict_mode=conflict_mode,
            progress_callback=progress_callback,
            completed_rows=completed_rows,
            total_rows=total,
        )
    except RuntimeError:
        if error_mode == "fail_fast":
            raise

    summary = VoiceImportSummary()
    for offset, row in enumerate(rows, start=1):
        try:
            row_summary = import_voice_manifest_rows(
                session,
                [row],
                default_language=default_language,
                conflict_mode=conflict_mode,
                progress_callback=progress_callback,
                completed_rows=completed_rows + offset - 1,
                total_rows=total,
            )
        except RuntimeError as exc:
            summary = _increment(summary, failed_rows=1)
            if error_samples_sink is not None:
                error_samples_sink.append({"entry": _row_label(row), "error": str(exc)})
            _emit_progress(
                progress_callback,
                row=row,
                completed_rows=completed_rows + offset,
                total_rows=total,
                label=f"Failed {completed_rows + offset}/{total}: {_row_label(row)}",
            )
            continue
        summary = _merge_summaries(summary, row_summary)
    return summary


def import_voice_manifest_rows(
    session: Any,
    rows: list[dict[str, Any]],
    *,
    default_language: str = "en",
    conflict_mode: str = "upsert",
    progress_callback: Callable[..., None] | None = None,
    completed_rows: int = 0,
    total_rows: int | None = None,
) -> VoiceImportSummary:
    _ensure_backend_path()
    from app.models.lexicon_voice_asset import LexiconVoiceAsset
    from app.models.lexicon_voice_storage_policy import LexiconVoiceStoragePolicy
    from app.models.meaning import Meaning
    from app.models.meaning_example import MeaningExample
    from app.models.phrase_entry import PhraseEntry
    from app.models.phrase_sense import PhraseSense
    from app.models.phrase_sense_example import PhraseSenseExample
    from app.models.word import Word

    (
        words_by_key,
        phrase_entries_by_key,
        meanings_by_source,
        meanings_by_order,
        phrase_senses_by_definition,
        phrase_senses_by_order,
        examples_by_sentence,
        examples_by_order,
        phrase_examples_by_sentence,
        phrase_examples_by_order,
        voice_assets_by_key,
    ) = _preload_voice_import_maps(
        session,
        rows,
        default_language=default_language,
        word_model=Word,
        meaning_model=Meaning,
        meaning_example_model=MeaningExample,
        phrase_entry_model=PhraseEntry,
        phrase_sense_model=PhraseSense,
        phrase_example_model=PhraseSenseExample,
        voice_asset_model=LexiconVoiceAsset,
    )

    storage_policy_by_scope: dict[str, Any] = {}

    summary = VoiceImportSummary()
    total = total_rows if total_rows is not None else completed_rows + len(rows)
    for offset, row in enumerate(rows, start=1):
        processed_rows = completed_rows + offset
        status = str(row.get("status") or "").strip().lower()
        if status not in {"generated", "existing"}:
            summary = _increment(summary, skipped_rows=1)
            _emit_progress(
                progress_callback,
                row=row,
                completed_rows=processed_rows,
                total_rows=total,
                label=f"Skipping manifest row {processed_rows}/{total}: {_row_label(row)}",
            )
            continue

        language = str(row.get("language") or default_language or "en").strip() or "en"
        language_key = language.lower()
        word_value = str(row.get("word") or "").strip()
        word_key = word_value.lower()
        content_scope = str(row.get("content_scope") or "").strip()
        source_reference = str(row.get("source_reference") or "").strip()
        sense_id = str(row.get("sense_id") or "").strip()
        meaning_index = row.get("meaning_index")
        example_index = row.get("example_index")
        source_text = str(row.get("source_text") or "").strip()
        entry_type = str(row.get("entry_type") or "word").strip().lower() or "word"

        word = None
        meaning = None
        example = None
        phrase_entry = None
        phrase_sense = None
        phrase_example = None

        if entry_type == "phrase":
            phrase_entry = phrase_entries_by_key.get((word_key, language_key))
            if phrase_entry is None:
                phrase_entry = session.execute(
                    select(PhraseEntry).where(
                        PhraseEntry.phrase_text == word_value,
                        PhraseEntry.language == language,
                    )
                ).scalar_one_or_none()
                if phrase_entry is not None:
                    phrase_entries_by_key[(word_key, language_key)] = phrase_entry
            if phrase_entry is None:
                summary = _increment(summary, missing_words=1)
                continue
            if content_scope in {"definition", "example"}:
                resolved_phrase_order_index = int(meaning_index) if meaning_index is not None else None
                if content_scope == "definition" and source_text:
                    phrase_sense = phrase_senses_by_definition.get((phrase_entry.id, source_text))
                else:
                    phrase_sense = None
                if phrase_sense is None and resolved_phrase_order_index is not None:
                    phrase_sense = phrase_senses_by_order.get((phrase_entry.id, resolved_phrase_order_index))
                if phrase_sense is None:
                    summary = _increment(summary, missing_meanings=1)
                    continue
            if content_scope == "example":
                resolved_example_order_index = int(example_index) if example_index is not None else None
                phrase_example = phrase_examples_by_sentence.get((phrase_sense.id, source_text)) if source_text else None
                if phrase_example is None and resolved_example_order_index is not None:
                    phrase_example = phrase_examples_by_order.get((phrase_sense.id, resolved_example_order_index))
                if phrase_example is None:
                    summary = _increment(summary, missing_examples=1)
                    continue
        else:
            word = words_by_key.get((word_key, language_key))
            if word is None:
                word = session.execute(
                    select(Word).where(
                        Word.word == word_value,
                        Word.language == language,
                    )
                ).scalar_one_or_none()
                if word is not None:
                    words_by_key[(word_key, language_key)] = word
            if word is None:
                summary = _increment(summary, missing_words=1)
                continue

            if content_scope in {"definition", "example"}:
                meaning_source_reference = f"{source_reference}:{sense_id}" if source_reference and sense_id else ""
                resolved_meaning_order_index = int(meaning_index) if meaning_index is not None else None
                meaning = meanings_by_source.get((word.id, meaning_source_reference)) if meaning_source_reference else None
                if meaning is None and resolved_meaning_order_index is not None:
                    meaning = meanings_by_order.get((word.id, resolved_meaning_order_index))
                if meaning is None:
                    summary = _increment(summary, missing_meanings=1)
                    continue

            if content_scope == "example":
                resolved_example_order_index = int(example_index) if example_index is not None else None
                example = examples_by_sentence.get((meaning.id, source_text)) if source_text else None
                if example is None and resolved_example_order_index is not None:
                    example = examples_by_order.get((meaning.id, resolved_example_order_index))
                if example is None:
                    summary = _increment(summary, missing_examples=1)
                    continue

        voice_asset_key = _voice_asset_lookup_key(
            content_scope=content_scope,
            word_id=word.id if content_scope == "word" and word is not None else None,
            meaning_id=meaning.id if content_scope == "definition" and meaning is not None else None,
            meaning_example_id=example.id if content_scope == "example" and example is not None else None,
            phrase_entry_id=phrase_entry.id if content_scope == "word" and phrase_entry is not None else None,
            phrase_sense_id=phrase_sense.id if content_scope == "definition" and phrase_sense is not None else None,
            phrase_sense_example_id=phrase_example.id if content_scope == "example" and phrase_example is not None else None,
            locale=str(row.get("locale") or "").strip(),
            voice_role=str(row.get("voice_role") or "").strip(),
            provider=str(row.get("provider") or "").strip(),
            family=str(row.get("family") or "").strip(),
            voice_id=str(row.get("voice_id") or "").strip(),
            profile_key=str(row.get("profile_key") or "").strip(),
            audio_format=str(row.get("audio_format") or "").strip(),
        )
        existing = voice_assets_by_key.get(voice_asset_key)
        storage_policy = None
        if existing is None or getattr(existing, "storage_policy_id", None) is None:
            storage_policy = storage_policy_by_scope.get(content_scope)
            if storage_policy is None:
                storage_policy = _find_or_create_storage_policy(
                    session,
                    LexiconVoiceStoragePolicy,
                    source_reference=source_reference or "legacy-voice",
                    content_scope=content_scope,
                    provider=str(row.get("provider") or "").strip(),
                    family=str(row.get("family") or "").strip(),
                    locale=str(row.get("locale") or "").strip(),
                    primary_storage_kind=str(row.get("storage_kind") or "").strip() or "local",
                    primary_storage_base=str(row.get("storage_base") or "").strip(),
                )
                storage_policy_by_scope[content_scope] = storage_policy
        if existing is None:
            existing = LexiconVoiceAsset(
                word_id=word.id if content_scope == "word" and word is not None else None,
                meaning_id=meaning.id if content_scope == "definition" and meaning is not None else None,
                meaning_example_id=example.id if content_scope == "example" and example is not None else None,
                phrase_entry_id=phrase_entry.id if content_scope == "word" and phrase_entry is not None else None,
                phrase_sense_id=phrase_sense.id if content_scope == "definition" and phrase_sense is not None else None,
                phrase_sense_example_id=phrase_example.id if content_scope == "example" and phrase_example is not None else None,
                storage_policy_id=storage_policy.id,
                content_scope=content_scope,
                locale=str(row.get("locale") or "").strip(),
                voice_role=str(row.get("voice_role") or "").strip(),
                provider=str(row.get("provider") or "").strip(),
                family=str(row.get("family") or "").strip(),
                voice_id=str(row.get("voice_id") or "").strip(),
                profile_key=str(row.get("profile_key") or "").strip(),
                audio_format=str(row.get("audio_format") or "").strip(),
            )
            session.add(existing)
            voice_assets_by_key[voice_asset_key] = existing
            summary = _increment(summary, created_assets=1)
        else:
            if conflict_mode == "skip":
                summary = _increment(summary, skipped_rows=1)
                _emit_progress(
                    progress_callback,
                    row=row,
                    completed_rows=processed_rows,
                    total_rows=total,
                    label=f"Skipping existing {entry_type}: {_row_label(row)}",
                )
                continue
            if conflict_mode == "fail":
                raise RuntimeError(f"voice asset already exists for {_row_label(row)}")
            summary = _increment(summary, updated_assets=1)
        if storage_policy is not None and getattr(existing, "storage_policy_id", None) is None:
            existing.storage_policy_id = storage_policy.id
        existing.mime_type = str(row.get("mime_type") or "").strip() or None
        existing.speaking_rate = float(row.get("speaking_rate") or 0.0) or None
        existing.pitch_semitones = float(row.get("pitch_semitones") or 0.0) if row.get("pitch_semitones") is not None else None
        existing.lead_ms = int(row.get("lead_ms") or 0)
        existing.tail_ms = int(row.get("tail_ms") or 0)
        existing.effects_profile_id = str(row.get("effects_profile_id") or "").strip() or None
        existing.relative_path = str(row.get("relative_path") or "").strip()
        existing.source_text = source_text
        existing.source_text_hash = str(row.get("source_text_hash") or "").strip()
        existing.status = status
        existing.generation_error = str(row.get("generation_error") or "").strip() or None
        existing.generated_at = _parse_timestamp(row.get("generated_at"))
        _emit_progress(
            progress_callback,
            row=row,
            completed_rows=processed_rows,
            total_rows=total,
            label=f"Importing {processed_rows}/{total}: {_row_label(row)}",
        )
    return summary


def run_voice_import_file(
    path: str | Path,
    *,
    language: str | None = None,
    default_language: str | None = None,
    source_type: str | None = None,
    source_reference: str | None = None,
    conflict_mode: str = "upsert",
    error_mode: str = "fail_fast",
    dry_run: bool = False,
    rows: list[dict[str, Any]] | None = None,
    preflight_progress_callback: Callable[..., None] | None = None,
    progress_callback: Callable[..., None] | None = None,
    import_started_callback: Callable[[], None] | None = None,
    error_samples_sink: list[dict[str, str]] | None = None,
    start_group_index: int = 0,
    max_group_count: int | None = None,
) -> dict[str, int | bool]:
    from sqlalchemy.exc import IntegrityError

    del source_type, source_reference
    resolved_language = str(language or default_language or "en").strip() or "en"
    if rows is None:
        group_index = _load_or_build_voice_manifest_group_index(path)
        indexed_groups = list(group_index.get("groups") or [])
        total_group_count = len(indexed_groups)
        total_rows = int(group_index.get("row_count") or 0)
        resolved_start_group_index = max(start_group_index, 0)
        selected_indexed_groups = indexed_groups[resolved_start_group_index:]
        if max_group_count is not None and max_group_count > 0:
            selected_indexed_groups = selected_indexed_groups[:max_group_count]

        row_offset = sum(len(list(group.get("row_indices") or [])) for group in indexed_groups[:resolved_start_group_index])
        selected_row_indices: list[int] = []
        for group in selected_indexed_groups:
            selected_row_indices.extend([int(index) for index in list(group.get("row_indices") or [])])
        rows_by_index = _load_voice_manifest_rows_by_indices(path, selected_row_indices)

        selected_groups: list[VoiceManifestGroup] = []
        for group in selected_indexed_groups:
            ordered_indices = [int(index) for index in list(group.get("row_indices") or [])]
            group_rows = [rows_by_index[index] for index in ordered_indices if index in rows_by_index]
            selected_groups.append(
                VoiceManifestGroup(
                    entry_type=str(group.get("entry_type") or "word"),
                    lexical_text=str(group.get("lexical_text") or ""),
                    language=str(group.get("language") or "en"),
                    rows=group_rows,
                )
            )
        selected_rows = [row for group in selected_groups for row in group.rows]
    else:
        loaded_rows = rows
        grouped_rows = group_voice_manifest_rows(loaded_rows)
        total_group_count = len(grouped_rows)
        resolved_start_group_index = max(start_group_index, 0)
        selected_groups = grouped_rows[resolved_start_group_index:]
        if max_group_count is not None and max_group_count > 0:
            selected_groups = selected_groups[:max_group_count]
        row_offset = sum(len(group.rows) for group in grouped_rows[:resolved_start_group_index])
        selected_rows = [row for group in selected_groups for row in group.rows]
        total_rows = len(loaded_rows)
    if dry_run:
        return _dry_run_voice_manifest_rows(
            selected_rows,
            default_language=resolved_language,
            progress_callback=preflight_progress_callback or progress_callback,
            error_samples_sink=error_samples_sink,
            completed_rows_offset=row_offset,
            total_rows=total_rows,
        )

    run_preflight = resolved_start_group_index == 0
    if run_preflight:
        preflight_rows = (
            load_voice_manifest_rows(path) if rows is None else loaded_rows
        )
        preflight_summary = _dry_run_voice_manifest_rows(
            preflight_rows,
            default_language=resolved_language,
            progress_callback=preflight_progress_callback,
            error_samples_sink=error_samples_sink,
            completed_rows_offset=0,
            total_rows=total_rows,
        )
        if int(preflight_summary.get("failed_rows") or 0) > 0:
            if error_samples_sink:
                first_error = error_samples_sink[0]
                raise RuntimeError(f"{first_error.get('entry')}: {first_error.get('error')}")
            raise RuntimeError("Voice import preflight failed")

    runtime_create_engine, runtime_session, runtime_get_settings = _ensure_runtime_dependencies()
    settings = runtime_get_settings()
    engine = runtime_create_engine(settings.database_url_sync)
    try:
        summary = VoiceImportSummary()
        if import_started_callback is not None and selected_groups:
            import_started_callback()
        completed_rows = row_offset
        for group in selected_groups:
            with runtime_session(engine) as session:
                try:
                    group_summary = import_voice_manifest_group(
                        session,
                        group.rows,
                        default_language=resolved_language,
                        conflict_mode=conflict_mode,
                        error_mode=error_mode,
                        progress_callback=progress_callback,
                        completed_rows=completed_rows,
                        total_rows=total_rows,
                        error_samples_sink=error_samples_sink,
                    )
                except RuntimeError:
                    session.rollback()
                    raise
                try:
                    session.commit()
                except IntegrityError as exc:
                    session.rollback()
                    if error_mode == "fail_fast":
                        raise RuntimeError(str(exc)) from exc
                    group_summary = VoiceImportSummary()
                    for row_offset_in_group, row in enumerate(group.rows, start=1):
                        row_completed_base = completed_rows + row_offset_in_group - 1
                        with runtime_session(engine) as row_session:
                            try:
                                row_summary = import_voice_manifest_group(
                                    row_session,
                                    [row],
                                    default_language=resolved_language,
                                    conflict_mode=conflict_mode,
                                    error_mode=error_mode,
                                    progress_callback=progress_callback,
                                    completed_rows=row_completed_base,
                                    total_rows=total_rows,
                                    error_samples_sink=error_samples_sink,
                                )
                                row_session.commit()
                            except RuntimeError as row_exc:
                                row_session.rollback()
                                row_summary = VoiceImportSummary(failed_rows=1)
                                if error_samples_sink is not None and len(error_samples_sink) < 10:
                                    error_samples_sink.append({"entry": _row_label(row), "error": str(row_exc)})
                            except IntegrityError as row_integrity_exc:
                                row_session.rollback()
                                row_summary = VoiceImportSummary(failed_rows=1)
                                if error_samples_sink is not None and len(error_samples_sink) < 10:
                                    error_samples_sink.append({"entry": _row_label(row), "error": str(row_integrity_exc)})
                        group_summary = _merge_summaries(group_summary, row_summary)
            completed_rows += len(group.rows)
            summary = _merge_summaries(summary, group_summary)
        next_group_index = resolved_start_group_index + len(selected_groups)
        result = summary.__dict__.copy()
        result["processed_group_count"] = len(selected_groups)
        result["next_group_index"] = next_group_index
        result["total_group_count"] = total_group_count
        result["all_groups_completed"] = next_group_index >= total_group_count
        result["rows_completed"] = completed_rows
        result["row_count"] = total_rows
        return result
    finally:
        engine.dispose()


def run_voice_storage_sync(
    *,
    source_reference: str,
    storage_kind: str,
    storage_base: str,
    fallback_storage_kind: str | None = None,
    fallback_storage_base: str | None = None,
    provider: str | None = None,
    family: str | None = None,
    locale: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    _ensure_backend_path()
    from sqlalchemy import create_engine, or_, select
    from sqlalchemy.orm import Session
    from app.core.config import get_settings
    from app.models.lexicon_voice_asset import LexiconVoiceAsset
    from app.models.lexicon_voice_storage_policy import LexiconVoiceStoragePolicy
    from app.models.meaning import Meaning
    from app.models.meaning_example import MeaningExample
    from app.models.word import Word

    normalized_source_reference = str(source_reference).strip()
    normalized_storage_kind = str(storage_kind).strip()
    normalized_storage_base = str(storage_base).strip()
    normalized_fallback_storage_kind = str(fallback_storage_kind or "").strip()
    normalized_fallback_storage_base = str(fallback_storage_base or "").strip()
    normalized_provider = str(provider or "").strip()
    normalized_family = str(family or "").strip()
    normalized_locale = str(locale or "").strip()

    if not normalized_source_reference:
        raise RuntimeError("source_reference is required")
    if not normalized_storage_kind:
        raise RuntimeError("storage_kind is required")
    if not normalized_storage_base:
        raise RuntimeError("storage_base is required")
    if normalized_fallback_storage_kind and not normalized_fallback_storage_base:
        raise RuntimeError("fallback_storage_base is required when fallback_storage_kind is provided")
    if normalized_fallback_storage_base and not normalized_fallback_storage_kind:
        raise RuntimeError("fallback_storage_kind is required when fallback_storage_base is provided")

    settings = get_settings()
    engine = create_engine(settings.database_url_sync)
    try:
        with Session(engine) as session:
            meaning_word = Word.__table__.alias("meaning_word")
            example_meaning = Meaning.__table__.alias("example_meaning")
            example_word = Word.__table__.alias("example_word")
            query = (
                select(LexiconVoiceAsset)
                .outerjoin(Word, LexiconVoiceAsset.word_id == Word.id)
                .outerjoin(Meaning, LexiconVoiceAsset.meaning_id == Meaning.id)
                .outerjoin(meaning_word, Meaning.word_id == meaning_word.c.id)
                .outerjoin(MeaningExample, LexiconVoiceAsset.meaning_example_id == MeaningExample.id)
                .outerjoin(example_meaning, MeaningExample.meaning_id == example_meaning.c.id)
                .outerjoin(example_word, example_meaning.c.word_id == example_word.c.id)
                .where(
                    or_(
                        Word.source_reference == normalized_source_reference,
                        meaning_word.c.source_reference == normalized_source_reference,
                        example_word.c.source_reference == normalized_source_reference,
                    )
                )
            )
            if normalized_provider:
                query = query.where(LexiconVoiceAsset.provider == normalized_provider)
            if normalized_family:
                query = query.where(LexiconVoiceAsset.family == normalized_family)
            if normalized_locale:
                query = query.where(LexiconVoiceAsset.locale == normalized_locale)
            assets = list(session.execute(query).scalars().all())
            if not dry_run:
                policy_ids = {asset.storage_policy_id for asset in assets}
                if policy_ids:
                    policies = list(
                        session.execute(
                            select(LexiconVoiceStoragePolicy).where(LexiconVoiceStoragePolicy.id.in_(policy_ids))
                        ).scalars().all()
                    )
                    for policy in policies:
                        policy.primary_storage_kind = normalized_storage_kind
                        policy.primary_storage_base = normalized_storage_base
                        policy.fallback_storage_kind = normalized_fallback_storage_kind or None
                        policy.fallback_storage_base = normalized_fallback_storage_base or None
                session.commit()
            return {
                "matched_count": len(assets),
                "updated_count": 0 if dry_run else len(assets),
                "dry_run": bool(dry_run),
                "storage_kind": normalized_storage_kind,
                "storage_base": normalized_storage_base,
                "fallback_storage_kind": normalized_fallback_storage_kind or None,
                "fallback_storage_base": normalized_fallback_storage_base or None,
            }
    finally:
        engine.dispose()
