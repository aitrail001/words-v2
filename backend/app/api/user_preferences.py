from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.models.user_preference import UserPreference
from app.services.knowledge_map import (
    DEFAULT_ACCENT,
    DEFAULT_TRANSLATION_LOCALE,
    DEFAULT_VIEW,
    SUPPORTED_TRANSLATION_LOCALES,
)

router = APIRouter()
DEFAULT_SHOW_TRANSLATIONS = True


class UserPreferencesResponse(BaseModel):
    accent_preference: str
    translation_locale: str
    knowledge_view_preference: str
    show_translations_by_default: bool
    review_depth_preset: str
    timezone: str
    enable_confidence_check: bool
    enable_word_spelling: bool
    enable_audio_spelling: bool
    show_pictures_in_questions: bool


class UserPreferencesUpdateRequest(BaseModel):
    accent_preference: str
    translation_locale: str
    knowledge_view_preference: str
    show_translations_by_default: bool
    review_depth_preset: str
    timezone: str | None = None
    enable_confidence_check: bool
    enable_word_spelling: bool
    enable_audio_spelling: bool
    show_pictures_in_questions: bool

    @field_validator("accent_preference")
    @classmethod
    def validate_accent(cls, value: str) -> str:
        if value not in {"us", "uk", "au"}:
            raise ValueError("Unsupported accent preference")
        return value

    @field_validator("translation_locale")
    @classmethod
    def validate_translation_locale(cls, value: str) -> str:
        if value not in SUPPORTED_TRANSLATION_LOCALES:
            raise ValueError("Unsupported translation locale")
        return value

    @field_validator("knowledge_view_preference")
    @classmethod
    def validate_view(cls, value: str) -> str:
        if value not in {"cards", "tags", "list"}:
            raise ValueError("Unsupported knowledge view preference")
        return value

    @field_validator("review_depth_preset")
    @classmethod
    def validate_review_depth_preset(cls, value: str) -> str:
        if value not in {"gentle", "balanced", "deep"}:
            raise ValueError("Unsupported review depth preset")
        return value

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str | None) -> str | None:
        if value is None:
            return value
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("Unsupported timezone") from exc
        return value


def _response(row: UserPreference | None) -> UserPreferencesResponse:
    if row is None:
        return UserPreferencesResponse(
            accent_preference=DEFAULT_ACCENT,
            translation_locale=DEFAULT_TRANSLATION_LOCALE,
            knowledge_view_preference=DEFAULT_VIEW,
            show_translations_by_default=DEFAULT_SHOW_TRANSLATIONS,
            review_depth_preset="balanced",
            timezone="UTC",
            enable_confidence_check=True,
            enable_word_spelling=True,
            enable_audio_spelling=False,
            show_pictures_in_questions=False,
        )
    return UserPreferencesResponse(
        accent_preference=row.accent_preference,
        translation_locale=row.translation_locale,
        knowledge_view_preference=row.knowledge_view_preference,
        show_translations_by_default=row.show_translations_by_default,
        review_depth_preset=row.review_depth_preset,
        timezone=row.timezone,
        enable_confidence_check=row.enable_confidence_check,
        enable_word_spelling=row.enable_word_spelling,
        enable_audio_spelling=row.enable_audio_spelling,
        show_pictures_in_questions=row.show_pictures_in_questions,
    )


@router.get("", response_model=UserPreferencesResponse)
async def get_user_preferences(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(UserPreference).where(UserPreference.user_id == current_user.id))
    return _response(result.scalar_one_or_none())


@router.put("", response_model=UserPreferencesResponse)
async def put_user_preferences(
    payload: UserPreferencesUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(UserPreference).where(UserPreference.user_id == current_user.id))
    row = result.scalar_one_or_none()
    resolved_timezone = payload.timezone or (row.timezone if row is not None else "UTC")
    if row is None:
        row = UserPreference(
            user_id=current_user.id,
            accent_preference=payload.accent_preference,
            translation_locale=payload.translation_locale,
            knowledge_view_preference=payload.knowledge_view_preference,
            show_translations_by_default=payload.show_translations_by_default,
            review_depth_preset=payload.review_depth_preset,
            timezone=resolved_timezone,
            enable_confidence_check=payload.enable_confidence_check,
            enable_word_spelling=payload.enable_word_spelling,
            enable_audio_spelling=payload.enable_audio_spelling,
            show_pictures_in_questions=payload.show_pictures_in_questions,
        )
        db.add(row)
    else:
        row.accent_preference = payload.accent_preference
        row.translation_locale = payload.translation_locale
        row.knowledge_view_preference = payload.knowledge_view_preference
        row.show_translations_by_default = payload.show_translations_by_default
        row.review_depth_preset = payload.review_depth_preset
        row.timezone = resolved_timezone
        row.enable_confidence_check = payload.enable_confidence_check
        row.enable_word_spelling = payload.enable_word_spelling
        row.enable_audio_spelling = payload.enable_audio_spelling
        row.show_pictures_in_questions = payload.show_pictures_in_questions
    await db.commit()
    return _response(row)
