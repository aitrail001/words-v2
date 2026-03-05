import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.review import ReviewService
from app.models.review import ReviewSession, ReviewCard
from app.models.word import Word
from app.models.meaning import Meaning


@pytest.fixture
def mock_db():
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.add = MagicMock()
    return session


@pytest.fixture
def review_service(mock_db):
    return ReviewService(mock_db)


class TestCreateSession:
    @pytest.mark.asyncio
    async def test_create_session(self, review_service, mock_db):
        user_id = uuid.uuid4()
        session = await review_service.create_session(user_id)

        assert session.user_id == user_id
        assert session.started_at is not None
        assert session.completed_at is None
        assert session.cards_reviewed == 0
        mock_db.add.assert_called_once()


class TestGetDueCards:
    @pytest.mark.asyncio
    async def test_get_due_cards_returns_overdue(self, review_service, mock_db):
        user_id = uuid.uuid4()
        word = Word(id=uuid.uuid4(), word="test", language="en")
        meaning = Meaning(id=uuid.uuid4(), word_id=word.id, definition="A test")

        # Mock: card is overdue (next_review in the past)
        overdue_card = ReviewCard(
            id=uuid.uuid4(),
            session_id=uuid.uuid4(),
            word_id=word.id,
            meaning_id=meaning.id,
            card_type="flashcard",
            next_review=datetime.now(timezone.utc) - timedelta(days=1),
        )

        result = MagicMock()
        result.scalars.return_value.all.return_value = [overdue_card]
        mock_db.execute.return_value = result

        cards = await review_service.get_due_cards(user_id, limit=10)
        assert len(cards) == 1
        assert cards[0].id == overdue_card.id

    @pytest.mark.asyncio
    async def test_get_due_cards_excludes_future(self, review_service, mock_db):
        user_id = uuid.uuid4()

        # Mock: no cards due
        result = MagicMock()
        result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = result

        cards = await review_service.get_due_cards(user_id, limit=10)
        assert len(cards) == 0


class TestSubmitReview:
    @pytest.mark.asyncio
    async def test_submit_review_updates_card(self, review_service, mock_db):
        card_id = uuid.uuid4()
        user_id = uuid.uuid4()
        card = ReviewCard(
            id=card_id,
            session_id=uuid.uuid4(),
            word_id=uuid.uuid4(),
            meaning_id=uuid.uuid4(),
            card_type="flashcard",
            ease_factor=2.5,
            interval_days=1,
            repetitions=1,  # Second review
        )

        result = MagicMock()
        result.scalar_one_or_none.return_value = card
        mock_db.execute.return_value = result

        updated = await review_service.submit_review(
            card_id=card_id,
            quality=5,  # Perfect recall increases ease factor
            time_spent_ms=5000,
            user_id=user_id,
        )

        assert updated.quality_rating == 5
        assert updated.time_spent_ms == 5000
        assert updated.ease_factor > 2.5  # SM-2 increases ease for quality 5
        assert updated.interval_days > 1
        assert updated.next_review is not None

        executed_query = mock_db.execute.call_args.args[0]
        assert "review_sessions.user_id" in str(executed_query)
        assert user_id in executed_query.compile().params.values()

    @pytest.mark.asyncio
    async def test_submit_review_quality_0_resets(self, review_service, mock_db):
        card = ReviewCard(
            id=uuid.uuid4(),
            session_id=uuid.uuid4(),
            word_id=uuid.uuid4(),
            meaning_id=uuid.uuid4(),
            card_type="flashcard",
            ease_factor=2.5,
            interval_days=10,
        )

        result = MagicMock()
        result.scalar_one_or_none.return_value = card
        mock_db.execute.return_value = result

        updated = await review_service.submit_review(
            card_id=card.id,
            quality=0,
            time_spent_ms=3000,
            user_id=uuid.uuid4(),
        )

        assert updated.quality_rating == 0
        assert updated.interval_days == 1  # SM-2 resets to 1 day for quality < 3

    @pytest.mark.asyncio
    async def test_submit_review_raises_when_card_not_found_for_user_scope(
        self, review_service, mock_db
    ):
        card_id = uuid.uuid4()
        user_id = uuid.uuid4()

        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = result

        with pytest.raises(ValueError, match=f"Review card {card_id} not found"):
            await review_service.submit_review(
                card_id=card_id,
                quality=4,
                time_spent_ms=2500,
                user_id=user_id,
            )


class TestCompleteSession:
    @pytest.mark.asyncio
    async def test_complete_session(self, review_service, mock_db):
        session_id = uuid.uuid4()
        session = ReviewSession(id=session_id, user_id=uuid.uuid4())

        result = MagicMock()
        result.scalar_one_or_none.return_value = session
        mock_db.execute.return_value = result

        completed = await review_service.complete_session(session_id, session.user_id)

        assert completed.completed_at is not None
        mock_db.commit.assert_called()

    @pytest.mark.asyncio
    async def test_complete_session_raises_when_session_not_found_for_user_scope(
        self, review_service, mock_db
    ):
        session_id = uuid.uuid4()
        user_id = uuid.uuid4()

        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = result

        with pytest.raises(ValueError, match=f"Review session {session_id} not found"):
            await review_service.complete_session(session_id, user_id)
