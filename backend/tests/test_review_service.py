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


class TestQueueAdd:
    @pytest.mark.asyncio
    async def test_add_to_queue_is_idempotent_per_user_and_meaning(
        self, review_service, mock_db
    ):
        user_id = uuid.uuid4()
        existing_card = ReviewCard(
            id=uuid.uuid4(),
            session_id=uuid.uuid4(),
            word_id=uuid.uuid4(),
            meaning_id=uuid.uuid4(),
            card_type="flashcard",
        )

        result = MagicMock()
        result.scalar_one_or_none.return_value = existing_card
        mock_db.execute.return_value = result

        created = await review_service.add_to_queue(user_id, existing_card.meaning_id)

        assert created.id == existing_card.id
        mock_db.add.assert_not_called()
        mock_db.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_add_to_queue_creates_item_when_missing(self, review_service, mock_db):
        user_id = uuid.uuid4()
        word_id = uuid.uuid4()
        meaning = Meaning(id=uuid.uuid4(), word_id=word_id, definition="queue meaning")
        session = ReviewSession(id=uuid.uuid4(), user_id=user_id)

        existing_result = MagicMock()
        existing_result.scalar_one_or_none.return_value = None
        meaning_result = MagicMock()
        meaning_result.scalar_one_or_none.return_value = meaning
        session_result = MagicMock()
        session_result.scalar_one_or_none.return_value = session
        mock_db.execute.side_effect = [existing_result, meaning_result, session_result]

        created = await review_service.add_to_queue(user_id, meaning.id)

        assert created.meaning_id == meaning.id
        if hasattr(created, "word_id"):
            assert created.word_id == word_id
        assert created.card_type == "flashcard"
        mock_db.add.assert_called_once()
        mock_db.commit.assert_awaited_once()


class TestQueueDue:
    @pytest.mark.asyncio
    async def test_get_due_queue_items_includes_prompt_metadata(
        self, review_service, mock_db
    ):
        user_id = uuid.uuid4()
        card = ReviewCard(
            id=uuid.uuid4(),
            session_id=uuid.uuid4(),
            word_id=uuid.uuid4(),
            meaning_id=uuid.uuid4(),
            card_type="flashcard",
            next_review=datetime.now(timezone.utc) - timedelta(hours=1),
        )

        result = MagicMock()
        result.all.return_value = [(card, "serendipity", "lucky chance")]
        mock_db.execute.return_value = result

        due_items = await review_service.get_due_queue_items(user_id=user_id, limit=10)

        assert len(due_items) == 1
        assert due_items[0]["id"] == card.id
        assert due_items[0]["word"] == "serendipity"
        assert due_items[0]["definition"] == "lucky chance"


class TestQueueSubmit:
    @pytest.mark.asyncio
    async def test_submit_queue_review_applies_sm2_and_increments_counters(
        self, review_service, mock_db
    ):
        user_id = uuid.uuid4()
        card = ReviewCard(
            id=uuid.uuid4(),
            session_id=uuid.uuid4(),
            word_id=uuid.uuid4(),
            meaning_id=uuid.uuid4(),
            card_type="flashcard",
            ease_factor=2.5,
            interval_days=1,
            repetitions=1,
        )
        card.review_count = 2
        card.correct_count = 1

        class FakeHistory:
            def __init__(self, **kwargs):
                self.payload = kwargs

        review_service.history_model = FakeHistory

        card_result = MagicMock()
        card_result.scalar_one_or_none.return_value = card
        mock_db.execute.return_value = card_result

        updated = await review_service.submit_queue_review(
            item_id=card.id,
            quality=5,
            time_spent_ms=1500,
            user_id=user_id,
            card_type="listening",
        )

        assert updated.ease_factor > 2.5
        assert updated.interval_days > 1
        assert updated.repetitions == 2
        assert updated.review_count == 3
        assert updated.correct_count == 2
        assert updated.card_type == "listening"
        mock_db.commit.assert_awaited_once()
        assert any(
            isinstance(call.args[0], FakeHistory) for call in mock_db.add.call_args_list
        )

    @pytest.mark.asyncio
    async def test_submit_queue_review_raises_when_item_not_found_for_user(
        self, review_service, mock_db
    ):
        item_id = uuid.uuid4()
        user_id = uuid.uuid4()

        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = result

        with pytest.raises(ValueError, match=f"Queue item {item_id} not found"):
            await review_service.submit_queue_review(
                item_id=item_id,
                quality=4,
                time_spent_ms=1000,
                user_id=user_id,
            )


class TestQueueStats:
    @pytest.mark.asyncio
    async def test_get_queue_stats_returns_counts_and_accuracy(self, review_service, mock_db):
        user_id = uuid.uuid4()

        total_result = MagicMock()
        total_result.scalar_one.return_value = 5
        due_result = MagicMock()
        due_result.scalar_one.return_value = 2
        aggregate_result = MagicMock()
        aggregate_result.one.return_value = (10, 7)
        mock_db.execute.side_effect = [total_result, due_result, aggregate_result]

        stats = await review_service.get_queue_stats(user_id=user_id)

        assert stats["total_items"] == 5
        assert stats["due_items"] == 2
        assert stats["review_count"] == 10
        assert stats["correct_count"] == 7
        assert stats["accuracy"] == 0.7


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
