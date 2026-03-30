from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable
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
    rows: list[dict[str, Any]] = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            payload = json.loads(line)
            if isinstance(payload, dict):
                rows.append(payload)
    return rows


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
    return sorted(groups, key=lambda group: (group.entry_type, group.lexical_text, group.language))


def summarize_voice_manifest_rows(rows: list[dict[str, Any]]) -> dict[str, int]:
    summary = {
        "row_count": len(rows),
        "generated_count": 0,
        "existing_count": 0,
        "failed_count": 0,
    }
    for row in rows:
        status = str(row.get("status") or "").strip().lower()
        if status == "generated":
            summary["generated_count"] += 1
        elif status == "existing":
            summary["existing_count"] += 1
        elif status == "failed":
            summary["failed_count"] += 1
    return summary


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
) -> dict[str, int | bool]:
    summary = summarize_voice_manifest_rows(rows)
    failed_rows = 0
    for index, row in enumerate(rows, start=1):
        label = f"Validating {index}/{len(rows)}: {_row_label(row)}"
        _emit_progress(progress_callback, row=row, completed_rows=index, total_rows=len(rows), label=label)
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
    raise RuntimeError(f"missing default voice storage policy for content_scope={content_scope}")


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
    summary = VoiceImportSummary()
    total = total_rows if total_rows is not None else completed_rows + len(rows)
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
            if error_mode == "fail_fast":
                raise
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
        word_value = str(row.get("word") or "").strip()
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
            phrase_entry = _find_phrase_entry(session, PhraseEntry, phrase_text=word_value, language=language)
            if phrase_entry is None:
                summary = _increment(summary, missing_words=1)
                continue
            if content_scope in {"definition", "example"}:
                phrase_sense = _find_phrase_sense(
                    session,
                    PhraseSense,
                    phrase_entry_id=phrase_entry.id,
                    definition=source_text if content_scope == "definition" else "",
                    order_index=int(meaning_index) if meaning_index is not None else None,
                )
                if phrase_sense is None:
                    summary = _increment(summary, missing_meanings=1)
                    continue
            if content_scope == "example":
                phrase_example = _find_phrase_example(
                    session,
                    PhraseSenseExample,
                    phrase_sense_id=phrase_sense.id,
                    sentence=source_text,
                    order_index=int(example_index) if example_index is not None else None,
                )
                if phrase_example is None:
                    summary = _increment(summary, missing_examples=1)
                    continue
        else:
            word = _find_word(session, Word, word=word_value, language=language)
            if word is None:
                summary = _increment(summary, missing_words=1)
                continue

            if content_scope in {"definition", "example"}:
                meaning_source_reference = f"{source_reference}:{sense_id}" if source_reference and sense_id else ""
                meaning = _find_meaning(
                    session,
                    Meaning,
                    word_id=word.id,
                    source_reference=meaning_source_reference,
                    order_index=int(meaning_index) if meaning_index is not None else None,
                )
                if meaning is None:
                    summary = _increment(summary, missing_meanings=1)
                    continue

            if content_scope == "example":
                example = _find_example(
                    session,
                    MeaningExample,
                    meaning_id=meaning.id,
                    sentence=source_text,
                    order_index=int(example_index) if example_index is not None else None,
                )
                if example is None:
                    summary = _increment(summary, missing_examples=1)
                    continue

        existing = _find_voice_asset(
            session,
            LexiconVoiceAsset,
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
        storage_policy = None
        if existing is None or getattr(existing, "storage_policy_id", None) is None:
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
    error_samples_sink: list[dict[str, str]] | None = None,
) -> dict[str, int | bool]:
    del source_type, source_reference
    resolved_language = str(language or default_language or "en").strip() or "en"
    loaded_rows = rows if rows is not None else load_voice_manifest_rows(path)
    if dry_run:
        return _dry_run_voice_manifest_rows(
            loaded_rows,
            default_language=resolved_language,
            progress_callback=preflight_progress_callback or progress_callback,
            error_samples_sink=error_samples_sink,
        )

    preflight_summary = _dry_run_voice_manifest_rows(
        loaded_rows,
        default_language=resolved_language,
        progress_callback=preflight_progress_callback,
        error_samples_sink=error_samples_sink,
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
        total_rows = len(loaded_rows)
        completed_rows = 0
        for group in group_voice_manifest_rows(loaded_rows):
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
                session.commit()
            completed_rows += len(group.rows)
            summary = _merge_summaries(summary, group_summary)
        return summary.__dict__.copy()
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
