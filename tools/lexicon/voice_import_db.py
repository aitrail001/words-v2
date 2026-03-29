from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
import json

from tools.lexicon.import_db import _ensure_backend_path


@dataclass(frozen=True)
class VoiceImportSummary:
    created_assets: int = 0
    updated_assets: int = 0
    skipped_rows: int = 0
    missing_words: int = 0
    missing_meanings: int = 0
    missing_examples: int = 0


def _increment(summary: VoiceImportSummary, **changes: int) -> VoiceImportSummary:
    values = summary.__dict__.copy()
    for key, delta in changes.items():
        values[key] = values.get(key, 0) + delta
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
        existing.policy_key = policy_key
        existing.source_reference = "global"
        existing.provider = "default"
        existing.family = "default"
        existing.locale = "all"
        existing.primary_storage_kind = primary_storage_kind
        existing.primary_storage_base = primary_storage_base
        existing.fallback_storage_kind = fallback_storage_kind
        existing.fallback_storage_base = fallback_storage_base
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


def import_voice_manifest_rows(
    session: Any,
    rows: list[dict[str, Any]],
    *,
    default_language: str = "en",
) -> VoiceImportSummary:
    _ensure_backend_path()
    from app.models.lexicon_voice_asset import LexiconVoiceAsset
    from app.models.lexicon_voice_storage_policy import LexiconVoiceStoragePolicy
    from app.models.meaning import Meaning
    from app.models.meaning_example import MeaningExample
    from app.models.word import Word

    summary = VoiceImportSummary()
    for row in rows:
        status = str(row.get("status") or "").strip().lower()
        if status not in {"generated", "existing"}:
            summary = _increment(summary, skipped_rows=1)
            continue

        language = str(row.get("language") or default_language or "en").strip() or "en"
        word_value = str(row.get("word") or "").strip()
        content_scope = str(row.get("content_scope") or "").strip()
        source_reference = str(row.get("source_reference") or "").strip()
        sense_id = str(row.get("sense_id") or "").strip()
        meaning_index = row.get("meaning_index")
        example_index = row.get("example_index")
        source_text = str(row.get("source_text") or "").strip()

        word = _find_word(session, Word, word=word_value, language=language)
        if word is None:
            summary = _increment(summary, missing_words=1)
            continue

        meaning = None
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

        example = None
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
            word_id=word.id if content_scope == "word" else None,
            meaning_id=meaning.id if content_scope == "definition" else None,
            meaning_example_id=example.id if content_scope == "example" else None,
            locale=str(row.get("locale") or "").strip(),
            voice_role=str(row.get("voice_role") or "").strip(),
            provider=str(row.get("provider") or "").strip(),
            family=str(row.get("family") or "").strip(),
            voice_id=str(row.get("voice_id") or "").strip(),
            profile_key=str(row.get("profile_key") or "").strip(),
            audio_format=str(row.get("audio_format") or "").strip(),
        )
        if existing is None:
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
            existing = LexiconVoiceAsset(
                word_id=word.id if content_scope == "word" else None,
                meaning_id=meaning.id if content_scope == "definition" else None,
                meaning_example_id=example.id if content_scope == "example" else None,
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
            summary = _increment(summary, updated_assets=1)

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
    return summary


def run_voice_import_file(path: str | Path, *, default_language: str = "en") -> dict[str, int]:
    _ensure_backend_path()
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from app.core.config import get_settings

    rows = load_voice_manifest_rows(path)
    settings = get_settings()
    engine = create_engine(settings.database_url_sync)
    try:
        with Session(engine) as session:
            summary = import_voice_manifest_rows(session, rows, default_language=default_language)
            session.commit()
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
