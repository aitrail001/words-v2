import uuid

from sqlalchemy import UniqueConstraint

from app.models.entry_review import EntryReviewState
from app.models.review import (
    LearningQueueItem,
    ReviewCard,
    ReviewHistory,
    ReviewSession,
)


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


class TestLearningQueueItemModel:
    def test_queue_item_has_required_fields(self):
        user_id = uuid.uuid4()
        meaning_id = uuid.uuid4()
        item = LearningQueueItem(user_id=user_id, meaning_id=meaning_id)
        assert item.user_id == user_id
        assert item.meaning_id == meaning_id
        assert item.priority == 0
        assert item.review_count == 0
        assert item.last_reviewed_at is None
        assert item.created_at is not None

    def test_queue_item_has_user_meaning_unique_constraint(self):
        constraints = [
            constraint
            for constraint in LearningQueueItem.__table__.constraints
            if isinstance(constraint, UniqueConstraint)
        ]
        assert any(
            constraint.name == "uq_learning_queue_user_meaning"
            and {column.name for column in constraint.columns} == {"user_id", "meaning_id"}
            for constraint in constraints
        )


class TestReviewHistoryModel:
    def test_review_history_has_required_fields(self):
        user_id = uuid.uuid4()
        meaning_id = uuid.uuid4()
        history = ReviewHistory(
            user_id=user_id,
            meaning_id=meaning_id,
            card_type="flashcard",
            quality_rating=4,
        )
        assert history.user_id == user_id
        assert history.meaning_id == meaning_id
        assert history.card_type == "flashcard"
        assert history.quality_rating == 4
        assert history.time_spent_ms is None
        assert history.created_at is not None


class TestEntryReviewStateModel:
    def test_state_can_track_target_identity_separately_from_parent_entry(self):
        user_id = uuid.uuid4()
        parent_entry_id = uuid.uuid4()
        target_id = uuid.uuid4()

        state = EntryReviewState(
            user_id=user_id,
            entry_type="word",
            entry_id=parent_entry_id,
            target_type="meaning",
            target_id=target_id,
        )

        assert state.user_id == user_id
        assert state.entry_type == "word"
        assert state.entry_id == parent_entry_id
        assert state.target_type == "meaning"
        assert state.target_id == target_id
