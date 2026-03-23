from fastapi import APIRouter, Depends
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.models.user_preference import UserPreference
from app.services.knowledge_map import DEFAULT_ACCENT, DEFAULT_TRANSLATION_LOCALE, DEFAULT_VIEW

router = APIRouter()
DEFAULT_SHOW_TRANSLATIONS = True


class UserPreferencesResponse(BaseModel):
    accent_preference: str
    translation_locale: str
    knowledge_view_preference: str
    show_translations_by_default: bool


class UserPreferencesUpdateRequest(BaseModel):
    accent_preference: str
    translation_locale: str
    knowledge_view_preference: str
    show_translations_by_default: bool

    @field_validator("accent_preference")
    @classmethod
    def validate_accent(cls, value: str) -> str:
        if value not in {"us", "uk", "au"}:
            raise ValueError("Unsupported accent preference")
        return value

    @field_validator("knowledge_view_preference")
    @classmethod
    def validate_view(cls, value: str) -> str:
        if value not in {"cards", "tags", "list"}:
            raise ValueError("Unsupported knowledge view preference")
        return value


def _response(row: UserPreference | None) -> UserPreferencesResponse:
    if row is None:
        return UserPreferencesResponse(
            accent_preference=DEFAULT_ACCENT,
            translation_locale=DEFAULT_TRANSLATION_LOCALE,
            knowledge_view_preference=DEFAULT_VIEW,
            show_translations_by_default=DEFAULT_SHOW_TRANSLATIONS,
        )
    return UserPreferencesResponse(
        accent_preference=row.accent_preference,
        translation_locale=row.translation_locale,
        knowledge_view_preference=row.knowledge_view_preference,
        show_translations_by_default=row.show_translations_by_default,
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
    if row is None:
        row = UserPreference(
            user_id=current_user.id,
            accent_preference=payload.accent_preference,
            translation_locale=payload.translation_locale,
            knowledge_view_preference=payload.knowledge_view_preference,
            show_translations_by_default=payload.show_translations_by_default,
        )
        db.add(row)
    else:
        row.accent_preference = payload.accent_preference
        row.translation_locale = payload.translation_locale
        row.knowledge_view_preference = payload.knowledge_view_preference
        row.show_translations_by_default = payload.show_translations_by_default
    await db.commit()
    return _response(row)
