import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.core.database import get_db
from app.core.logging import get_logger
from app.models.meaning import Meaning
from app.models.user import User
from app.models.word import Word

logger = get_logger(__name__)
router = APIRouter()


# Schemas
class MeaningResponse(BaseModel):
    id: str
    definition: str
    part_of_speech: str | None
    example_sentence: str | None
    order_index: int


class WordResponse(BaseModel):
    id: str
    word: str
    language: str
    phonetic: str | None
    frequency_rank: int | None


class WordDetailResponse(WordResponse):
    meanings: list[MeaningResponse]


class LookupRequest(BaseModel):
    word: str

    @field_validator("word")
    @classmethod
    def word_not_empty(cls, v: str) -> str:
        v = v.strip().lower()
        if not v:
            raise ValueError("Word must not be empty")
        return v


@router.get("/search", response_model=list[WordResponse])
async def search_words(
    q: str = Query(..., min_length=1),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[WordResponse]:
    result = await db.execute(
        select(Word)
        .where(Word.word.ilike(f"{q}%"))
        .order_by(Word.frequency_rank.asc().nullslast())
        .limit(20)
    )
    words = result.scalars().all()

    return [
        WordResponse(
            id=str(w.id),
            word=w.word,
            language=w.language,
            phonetic=w.phonetic,
            frequency_rank=w.frequency_rank,
        )
        for w in words
    ]


@router.get("/{word_id}", response_model=WordDetailResponse)
async def get_word(
    word_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> WordDetailResponse:
    result = await db.execute(select(Word).where(Word.id == word_id))
    word = result.scalar_one_or_none()

    if word is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Word not found",
        )

    meanings_result = await db.execute(
        select(Meaning)
        .where(Meaning.word_id == word_id)
        .order_by(Meaning.order_index)
    )
    meanings = meanings_result.scalars().all()

    return WordDetailResponse(
        id=str(word.id),
        word=word.word,
        language=word.language,
        phonetic=word.phonetic,
        frequency_rank=word.frequency_rank,
        meanings=[
            MeaningResponse(
                id=str(m.id),
                definition=m.definition,
                part_of_speech=m.part_of_speech,
                example_sentence=m.example_sentence,
                order_index=m.order_index,
            )
            for m in meanings
        ],
    )


@router.post("/lookup", response_model=WordDetailResponse)
async def lookup_word(
    request: LookupRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> WordDetailResponse:
    # Check local DB first
    result = await db.execute(
        select(Word).where(Word.word == request.word, Word.language == "en")
    )
    word = result.scalar_one_or_none()

    if word is not None:
        meanings_result = await db.execute(
            select(Meaning)
            .where(Meaning.word_id == word.id)
            .order_by(Meaning.order_index)
        )
        meanings = meanings_result.scalars().all()

        return WordDetailResponse(
            id=str(word.id),
            word=word.word,
            language=word.language,
            phonetic=word.phonetic,
            frequency_rank=word.frequency_rank,
            meanings=[
                MeaningResponse(
                    id=str(m.id),
                    definition=m.definition,
                    part_of_speech=m.part_of_speech,
                    example_sentence=m.example_sentence,
                    order_index=m.order_index,
                )
                for m in meanings
            ],
        )

    # Not found locally — return 404 for now
    # Dictionary API integration will be added as a service
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Word '{request.word}' not found",
    )
