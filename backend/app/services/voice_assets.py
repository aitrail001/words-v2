from __future__ import annotations

from pathlib import Path
import uuid

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.lexicon_voice_asset import LexiconVoiceAsset


async def load_word_voice_assets(
    db: AsyncSession,
    *,
    word_id: uuid.UUID,
    meaning_ids: list[uuid.UUID],
    example_ids: list[uuid.UUID],
) -> list[LexiconVoiceAsset]:
    clauses = [LexiconVoiceAsset.word_id == word_id]
    if meaning_ids:
        clauses.append(LexiconVoiceAsset.meaning_id.in_(meaning_ids))
    if example_ids:
        clauses.append(LexiconVoiceAsset.meaning_example_id.in_(example_ids))
    result = await db.execute(
        select(LexiconVoiceAsset)
        .options(selectinload(LexiconVoiceAsset.storage_policy))
        .where(or_(*clauses))
        .order_by(
            LexiconVoiceAsset.content_scope.asc(),
            LexiconVoiceAsset.locale.asc(),
            LexiconVoiceAsset.voice_role.asc(),
            LexiconVoiceAsset.profile_key.asc(),
        )
    )
    return list(result.scalars().all())


async def load_phrase_voice_assets(
    db: AsyncSession,
    *,
    phrase_entry_id: uuid.UUID,
    phrase_sense_ids: list[uuid.UUID],
    phrase_example_ids: list[uuid.UUID],
) -> list[LexiconVoiceAsset]:
    clauses = [LexiconVoiceAsset.phrase_entry_id == phrase_entry_id]
    if phrase_sense_ids:
        clauses.append(LexiconVoiceAsset.phrase_sense_id.in_(phrase_sense_ids))
    if phrase_example_ids:
        clauses.append(LexiconVoiceAsset.phrase_sense_example_id.in_(phrase_example_ids))
    result = await db.execute(
        select(LexiconVoiceAsset)
        .options(selectinload(LexiconVoiceAsset.storage_policy))
        .where(or_(*clauses))
        .order_by(
            LexiconVoiceAsset.content_scope.asc(),
            LexiconVoiceAsset.locale.asc(),
            LexiconVoiceAsset.voice_role.asc(),
            LexiconVoiceAsset.profile_key.asc(),
        )
    )
    return list(result.scalars().all())


def build_voice_asset_playback_url(asset: LexiconVoiceAsset) -> str:
    return f"/api/words/voice-assets/{asset.id}/content"


def build_storage_target_url(asset: LexiconVoiceAsset) -> str | None:
    if (asset.storage_policy.primary_storage_kind or "").strip().lower() == "local":
        return None
    base = (asset.storage_policy.primary_storage_base or "").strip()
    relative_path = (asset.relative_path or "").lstrip("/")
    if not base:
        return None
    return f"{base.rstrip('/')}/{relative_path}"


def build_local_storage_path(asset: LexiconVoiceAsset) -> Path:
    base = Path((asset.storage_policy.primary_storage_base or "").strip()).expanduser()
    target = (base / (asset.relative_path or "")).resolve()
    try:
        base_resolved = base.resolve()
    except FileNotFoundError:
        base_resolved = base.absolute()
    if target != base_resolved and base_resolved not in target.parents:
        raise FileNotFoundError("Voice asset path escapes configured storage base")
    return target


def build_fallback_storage_target_url(asset: LexiconVoiceAsset) -> str | None:
    if not asset.storage_policy.fallback_storage_kind or not asset.storage_policy.fallback_storage_base:
        return None
    if asset.storage_policy.fallback_storage_kind.strip().lower() == "local":
        return None
    base = (asset.storage_policy.fallback_storage_base or "").strip()
    relative_path = (asset.relative_path or "").lstrip("/")
    if not base:
        return None
    return f"{base.rstrip('/')}/{relative_path}"


def build_fallback_local_storage_path(asset: LexiconVoiceAsset) -> Path:
    if not asset.storage_policy.fallback_storage_base:
        raise FileNotFoundError("Voice asset fallback storage root is not configured")
    base = Path((asset.storage_policy.fallback_storage_base or "").strip()).expanduser()
    target = (base / (asset.relative_path or "")).resolve()
    try:
        base_resolved = base.resolve()
    except FileNotFoundError:
        base_resolved = base.absolute()
    if target != base_resolved and base_resolved not in target.parents:
        raise FileNotFoundError("Voice asset path escapes configured fallback storage base")
    return target
