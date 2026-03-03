import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.models.review import ReviewSession, ReviewCard


class TestReviewSessionModel:
    def test_session_has_required_fields(self):
        user_id = uuid.uuid4()
        session = ReviewSession(user_id=user_id)
        assert session.user_id == user_id
        assert session.started_at is not None
        assert session.completed_at is None
        assert session.cards_reviewed == 0

    def test_session_defaults(self):
        session = ReviewSession(user_id=uuid.uuid4())
        assert session.cards_reviewed == 0
        assert session.completed_at is None


class TestReviewCardModel:
    def test_card_has_required_fields(self):
        session_id = uuid.uuid4()
        word_id = uuid.uuid4()
        meaning_id = uuid.uuid4()
        card = ReviewCard(
            session_id=session_id,
            word_id=word_id,
            meaning_id=meaning_id,
            card_type="flashcard",
        )
        assert card.session_id == session_id
        assert card.word_id == word_id
        assert card.meaning_id == meaning_id
        assert card.card_type == "flashcard"
        assert card.quality_rating is None
        assert card.time_spent_ms is None

    def test_card_after_review(self):
        card = ReviewCard(
            session_id=uuid.uuid4(),
            word_id=uuid.uuid4(),
            meaning_id=uuid.uuid4(),
            card_type="flashcard",
            quality_rating=4,
            time_spent_ms=5000,
            ease_factor=2.5,
            interval_days=3,
        )
        assert card.quality_rating == 4
        assert card.time_spent_ms == 5000
        assert card.ease_factor == 2.5
        assert card.interval_days == 3
        assert card.next_review is not None

    def test_card_types_valid(self):
        for card_type in ["flashcard", "cloze", "listening"]:
            card = ReviewCard(
                session_id=uuid.uuid4(),
                word_id=uuid.uuid4(),
                meaning_id=uuid.uuid4(),
                card_type=card_type,
            )
            assert card.card_type == card_type
