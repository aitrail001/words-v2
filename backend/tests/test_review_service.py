import uuid
from importlib import util
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

import app.services.review as review_module
import app.services.review_submission as review_submission_module
from app.services.review import ReviewService
from app.core.database import Base
from app.models.entry_review import EntryReviewEvent, EntryReviewState
from app.models.learner_entry_status import LearnerEntryStatus
from app.models.user_preference import UserPreference
from app.models.word import Word
from app.models.meaning import Meaning
from app.spaced_repetition import calculate_next_review
from app.services.review_schedule import effective_review_date, due_review_date_for_bucket, min_due_at_for_bucket


@pytest.fixture
def mock_db():
    class AsyncNullContext:
        async def __aenter__(self):
            return None

        async def __aexit__(self, exc_type, exc, tb):
            return False

    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.add = MagicMock()
    session.begin_nested = MagicMock(return_value=AsyncNullContext())
    return session


@pytest.fixture
def review_service(mock_db):
    service = ReviewService(mock_db)
    service._get_user_review_preferences = AsyncMock(
        return_value=MagicMock(
            timezone="UTC",
            review_depth_preset="balanced",
            enable_confidence_check=True,
        )
    )
    return service


def _load_timezone_safe_migration():
    migration_path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "051_timezone_safe_review_sched.py"
    )
    spec = util.spec_from_file_location("migration_051_timezone_safe_review_sched", migration_path)
    assert spec is not None and spec.loader is not None
    module = util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _frozen_datetime_class(fixed_now: datetime):
    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            if tz is None:
                return fixed_now.replace(tzinfo=None) if fixed_now.tzinfo is not None else fixed_now
            return fixed_now.astimezone(tz)

    return FrozenDateTime


def _set_canonical_schedule(
    state: EntryReviewState,
    due_at: datetime | None,
    *,
    user_timezone: str = "UTC",
) -> None:
    state.min_due_at_utc = due_at
    state.due_review_date = (
        effective_review_date(instant_utc=due_at, user_timezone=user_timezone)
        if due_at is not None
        else None
    )


class TestQueueAdd:
    @pytest.mark.asyncio
    async def test_add_to_queue_is_idempotent_per_user_and_meaning(
        self, review_service, mock_db
    ):
        user_id = uuid.uuid4()
        word_id = uuid.uuid4()
        meaning = Meaning(
            id=uuid.uuid4(),
            word_id=word_id,
            definition="queue meaning",
        )
        existing_state = EntryReviewState(
            id=uuid.uuid4(),
            user_id=user_id,
            entry_type="word",
            entry_id=word_id,
            target_type="meaning",
            target_id=meaning.id,
            stability=0.3,
            difficulty=0.5,
        )
        _set_canonical_schedule(existing_state, datetime.now(timezone.utc) + timedelta(days=1))

        meaning_result = MagicMock()
        meaning_result.scalar_one_or_none.return_value = meaning

        mock_db.execute.side_effect = [meaning_result]
        review_service._ensure_target_review_state = AsyncMock(return_value=existing_state)

        created = await review_service.add_to_queue(user_id, meaning.id)

        assert created.id == existing_state.id
        assert created.meaning_id == meaning.id
        assert created.word_id == word_id
        assert created.card_type == "flashcard"
        mock_db.add.assert_not_called()
        mock_db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_add_to_queue_creates_item_when_missing(self, review_service, mock_db):
        user_id = uuid.uuid4()
        word_id = uuid.uuid4()
        meaning = Meaning(id=uuid.uuid4(), word_id=word_id, definition="queue meaning")
        meaning_result = MagicMock()
        meaning_result.scalar_one_or_none.return_value = meaning
        created_state = EntryReviewState(
            id=uuid.uuid4(),
            user_id=user_id,
            entry_type="word",
            entry_id=word_id,
            target_type="meaning",
            target_id=meaning.id,
            stability=0.3,
            difficulty=0.5,
        )
        mock_db.execute.side_effect = [meaning_result]
        review_service._ensure_target_review_state = AsyncMock(return_value=created_state)

        created = await review_service.add_to_queue(user_id, meaning.id)

        assert created.meaning_id == meaning.id
        assert created.word_id == word_id
        assert created.card_type == "flashcard"
        mock_db.add.assert_not_called()
        mock_db.commit.assert_awaited_once()


class TestEntryQueueSchedule:
    def test_entry_review_state_persists_timezone_safe_schedule_fields_through_orm(self):
        engine = create_engine("sqlite:///:memory:", future=True)
        try:
            Base.metadata.create_all(engine, tables=[EntryReviewState.__table__])

            due_review_date = date(2026, 4, 11)
            min_due_at_utc = datetime(2026, 4, 10, 18, 0, tzinfo=timezone.utc)
            state = EntryReviewState(
                id=uuid.uuid4(),
                user_id=uuid.uuid4(),
                entry_type="word",
                entry_id=uuid.uuid4(),
                stability=0.3,
                difficulty=0.5,
                due_review_date=due_review_date,
                min_due_at_utc=min_due_at_utc,
            )
            state.created_at = datetime(2026, 4, 10, 18, 0, tzinfo=timezone.utc)
            state.updated_at = datetime(2026, 4, 10, 18, 0, tzinfo=timezone.utc)

            with Session(engine) as session:
                session.add(state)
                session.commit()
                session.expire_all()

                persisted = session.execute(
                    select(EntryReviewState).where(EntryReviewState.id == state.id)
                ).scalar_one()

                assert persisted.due_review_date == due_review_date
                assert persisted.min_due_at_utc is not None
                assert persisted.min_due_at_utc.replace(tzinfo=timezone.utc) == min_due_at_utc
        finally:
            engine.dispose()

    def test_timezone_safe_migration_derives_backfill_from_next_due_at(self):
        migration = _load_timezone_safe_migration()
        next_due_at = datetime(2026, 4, 9, 18, 0, tzinfo=timezone.utc)

        assert migration._effective_review_date(
            instant_utc=next_due_at,
            user_timezone="Australia/Melbourne",
        ) == date(2026, 4, 10)
        assert migration._effective_review_date(
            instant_utc=next_due_at,
            user_timezone="UTC",
        ) == date(2026, 4, 9)

    def test_entry_review_state_accepts_timezone_safe_schedule_fields(self):
        due_review_date = date(2026, 4, 11)
        min_due_at_utc = datetime(2026, 4, 10, 18, 0, tzinfo=timezone.utc)

        state = EntryReviewState(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            entry_type="word",
            entry_id=uuid.uuid4(),
            stability=0.3,
            difficulty=0.5,
            due_review_date=due_review_date,
            min_due_at_utc=min_due_at_utc,
        )

        assert state.due_review_date == due_review_date
        assert state.min_due_at_utc == min_due_at_utc

    @pytest.mark.asyncio
    async def test_get_entry_queue_schedule_returns_canonical_schedule_for_created_learning_entry(
        self, review_service, mock_db
    ):
        user_id = uuid.uuid4()
        entry_id = uuid.uuid4()
        empty_state_result = MagicMock()
        empty_state_result.scalar_one_or_none.return_value = None
        learner_status = LearnerEntryStatus(
            user_id=user_id,
            entry_type="word",
            entry_id=entry_id,
            status="learning",
        )
        learner_status_result = MagicMock()
        learner_status_result.scalar_one_or_none.return_value = learner_status
        created_state = EntryReviewState(
            id=uuid.uuid4(),
            user_id=user_id,
            entry_type="word",
            entry_id=entry_id,
            stability=0.3,
            difficulty=0.5,
        )
        canonical_due_at = datetime.now(timezone.utc) + timedelta(days=1)
        _set_canonical_schedule(created_state, canonical_due_at)
        created_state.recheck_due_at = None
        mock_db.execute.side_effect = [learner_status_result, empty_state_result]
        review_service._ensure_entry_review_state = AsyncMock(return_value=created_state)

        payload = await review_service.get_entry_queue_schedule(
            user_id=user_id,
            entry_type="word",
            entry_id=entry_id,
        )

        assert created_state.min_due_at_utc == canonical_due_at
        assert payload == {
            "queue_item_id": str(created_state.id),
            "due_review_date": created_state.due_review_date.isoformat(),
            "min_due_at_utc": canonical_due_at.isoformat(),
            "recheck_due_at": None,
            "current_schedule_value": "1d",
            "current_schedule_label": "Tomorrow",
            "schedule_options": [
                {"value": "1d", "label": "Tomorrow", "is_default": True},
                {"value": "2d", "label": "In 2 days", "is_default": False},
                {"value": "3d", "label": "In 3 days", "is_default": False},
                {"value": "5d", "label": "In 5 days", "is_default": False},
                {"value": "7d", "label": "In 1 week", "is_default": False},
                {"value": "14d", "label": "In 2 weeks", "is_default": False},
                {"value": "30d", "label": "In 1 month", "is_default": False},
                {"value": "90d", "label": "In 3 months", "is_default": False},
                {"value": "180d", "label": "In 6 months", "is_default": False},
                {"value": "known", "label": "Known", "is_default": False},
            ],
        }
        review_service._ensure_entry_review_state.assert_awaited_once_with(
            user_id=user_id,
            entry_type="word",
            entry_id=entry_id,
        )
        mock_db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_entry_queue_schedule_hides_controls_for_to_learn_entries(
        self, review_service, mock_db
    ):
        user_id = uuid.uuid4()
        entry_id = uuid.uuid4()
        state = EntryReviewState(
            id=uuid.uuid4(),
            user_id=user_id,
            entry_type="word",
            entry_id=entry_id,
            stability=3,
            difficulty=0.5,
        )
        state_result = MagicMock()
        state_result.scalar_one_or_none.return_value = state
        learner_status = LearnerEntryStatus(
            user_id=user_id,
            entry_type="word",
            entry_id=entry_id,
            status="to_learn",
        )
        learner_status_result = MagicMock()
        learner_status_result.scalar_one_or_none.return_value = learner_status
        mock_db.execute.side_effect = [learner_status_result, state_result]

        payload = await review_service.get_entry_queue_schedule(
            user_id=user_id,
            entry_type="word",
            entry_id=entry_id,
        )

        assert payload is None


class TestQueueDue:
    @pytest.mark.asyncio
    async def test_get_due_queue_items_excludes_to_learn_entries(
        self, review_service, mock_db
    ):
        user_id = uuid.uuid4()
        state_result = MagicMock()
        state_result.scalars.return_value.all.return_value = []
        mock_db.execute.side_effect = [state_result]

        due_items = await review_service.get_due_queue_items(user_id=user_id, limit=10)

        assert due_items == []

    @pytest.mark.asyncio
    async def test_get_due_queue_items_includes_prompt_metadata(
        self, review_service, mock_db
    ):
        user_id = uuid.uuid4()
        word_id = uuid.uuid4()
        meaning_id = uuid.uuid4()
        state = EntryReviewState(
            id=uuid.uuid4(),
            user_id=user_id,
            entry_type="word",
            entry_id=word_id,
            target_type="meaning",
            target_id=meaning_id,
            stability=3,
            difficulty=0.5,
        )
        _set_canonical_schedule(state, datetime.now(timezone.utc) - timedelta(hours=1))
        word = Word(id=word_id, word="serendipity", language="en")
        meanings = [Meaning(id=meaning_id, word_id=word_id, definition="lucky chance")]

        state_result = MagicMock()
        state_result.scalars.return_value.all.return_value = [state]
        word_result = MagicMock()
        word_result.scalars.return_value.all.return_value = [word]
        meanings_result = MagicMock()
        meanings_result.scalars.return_value.all.return_value = meanings
        mock_db.execute.side_effect = [state_result, word_result, meanings_result]
        review_service._get_user_accent_preference = AsyncMock(return_value="us")
        review_service._fetch_first_meaning_sentence_map = AsyncMock(return_value={meaning_id: None})
        review_service._fetch_history_count_by_word_id = AsyncMock(return_value={word_id: 0})
        review_service._build_card_prompt = AsyncMock(return_value={"prompt_type": "definition_to_entry"})
        review_service._build_word_detail_payload = AsyncMock(
            return_value={"entry_type": "word", "entry_id": str(word_id), "display_text": "serendipity"}
        )

        due_items = await review_service.get_due_queue_items(user_id=user_id, limit=10)

        assert len(due_items) == 1
        assert due_items[0]["id"] == state.id
        assert due_items[0]["word"] == "serendipity"
        assert due_items[0]["definition"] == "lucky chance"

    @pytest.mark.asyncio
    async def test_get_due_queue_items_does_not_unlock_future_official_schedule_after_eastward_timezone_change(
        self, review_service, mock_db, monkeypatch
    ):
        now = datetime(2026, 4, 10, 10, 0, tzinfo=timezone.utc)
        user_id = uuid.uuid4()
        word_id = uuid.uuid4()
        meaning_id = uuid.uuid4()
        state = EntryReviewState(
            id=uuid.uuid4(),
            user_id=user_id,
            entry_type="word",
            entry_id=word_id,
            target_type="meaning",
            target_id=meaning_id,
            stability=3,
            difficulty=0.5,
        )
        _set_canonical_schedule(state, datetime(2026, 4, 10, 18, 0, tzinfo=timezone.utc), user_timezone="Asia/Tokyo")
        word = Word(id=word_id, word="candidate", language="en")
        meanings = [Meaning(id=meaning_id, word_id=word_id, definition="A person under consideration.")]

        state_result = MagicMock()
        state_result.scalars.return_value.all.return_value = [state]
        word_result = MagicMock()
        word_result.scalars.return_value.all.return_value = [word]
        meanings_result = MagicMock()
        meanings_result.scalars.return_value.all.return_value = meanings
        mock_db.execute.side_effect = [state_result, word_result, meanings_result]
        review_service._get_user_review_preferences = AsyncMock(
            return_value=MagicMock(
                review_depth_preset="balanced",
                enable_confidence_check=True,
                timezone="Asia/Tokyo",
            )
        )
        review_service._get_user_accent_preference = AsyncMock(return_value="us")
        review_service._fetch_first_meaning_sentence_map = AsyncMock(return_value={meaning_id: None})
        review_service._fetch_history_count_by_word_id = AsyncMock(return_value={word_id: 0})
        review_service._build_card_prompt = AsyncMock(return_value={"prompt_type": "definition_to_entry"})
        review_service._build_word_detail_payload = AsyncMock(
            return_value={"entry_type": "word", "entry_id": str(word_id), "display_text": "candidate"}
        )
        monkeypatch.setattr(
            review_module,
            "datetime",
            _frozen_datetime_class(now),
        )

        due_items = await review_service.get_due_queue_items(user_id=user_id, limit=10)

        assert due_items == []

    @pytest.mark.asyncio
    async def test_get_due_queue_items_includes_card_at_min_due_boundary_after_westward_timezone_change(
        self, review_service, mock_db, monkeypatch
    ):
        now = datetime(2026, 4, 10, 18, 0, tzinfo=timezone.utc)
        user_id = uuid.uuid4()
        word_id = uuid.uuid4()
        meaning_id = uuid.uuid4()
        state = EntryReviewState(
            id=uuid.uuid4(),
            user_id=user_id,
            entry_type="word",
            entry_id=word_id,
            target_type="meaning",
            target_id=meaning_id,
            stability=3,
            difficulty=0.5,
        )
        _set_canonical_schedule(state, now, user_timezone="America/Los_Angeles")
        word = Word(id=word_id, word="candidate", language="en")
        meanings = [Meaning(id=meaning_id, word_id=word_id, definition="A person under consideration.")]

        state_result = MagicMock()
        state_result.scalars.return_value.all.return_value = [state]
        word_result = MagicMock()
        word_result.scalars.return_value.all.return_value = [word]
        meanings_result = MagicMock()
        meanings_result.scalars.return_value.all.return_value = meanings
        mock_db.execute.side_effect = [state_result, word_result, meanings_result]
        review_service._get_user_review_preferences = AsyncMock(
            return_value=MagicMock(
                review_depth_preset="balanced",
                enable_confidence_check=True,
                timezone="America/Los_Angeles",
            )
        )
        review_service._get_user_accent_preference = AsyncMock(return_value="us")
        review_service._fetch_first_meaning_sentence_map = AsyncMock(return_value={meaning_id: None})
        review_service._fetch_history_count_by_word_id = AsyncMock(return_value={word_id: 0})
        review_service._build_card_prompt = AsyncMock(return_value={"prompt_type": "definition_to_entry"})
        review_service._build_word_detail_payload = AsyncMock(
            return_value={"entry_type": "word", "entry_id": str(word_id), "display_text": "candidate"}
        )
        monkeypatch.setattr(review_module, "datetime", _frozen_datetime_class(now))

        due_items = await review_service.get_due_queue_items(user_id=user_id, limit=10)

        assert len(due_items) == 1
        assert due_items[0]["id"] == state.id

    @pytest.mark.asyncio
    async def test_get_queue_stats_matches_due_queue_at_min_due_boundary_after_westward_timezone_change(
        self, review_service, mock_db, monkeypatch
    ):
        now = datetime(2026, 4, 10, 18, 0, tzinfo=timezone.utc)
        user_id = uuid.uuid4()
        word_id = uuid.uuid4()
        meaning_id = uuid.uuid4()
        state = EntryReviewState(
            id=uuid.uuid4(),
            user_id=user_id,
            entry_type="word",
            entry_id=word_id,
            target_type="meaning",
            target_id=meaning_id,
            stability=3,
            difficulty=0.5,
        )
        _set_canonical_schedule(state, now, user_timezone="America/Los_Angeles")
        word = Word(id=word_id, word="candidate", language="en")
        meanings = [Meaning(id=meaning_id, word_id=word_id, definition="A person under consideration.")]

        state_result = MagicMock()
        state_result.scalars.return_value.all.return_value = [state]
        word_result = MagicMock()
        word_result.scalars.return_value.all.return_value = [word]
        meanings_result = MagicMock()
        meanings_result.scalars.return_value.all.return_value = meanings
        aggregate_result = MagicMock()
        aggregate_result.one.return_value = (0, 0)
        mock_db.execute.side_effect = [
            state_result,
            word_result,
            meanings_result,
            aggregate_result,
        ]
        review_service._get_user_review_preferences = AsyncMock(
            return_value=MagicMock(
                review_depth_preset="balanced",
                enable_confidence_check=True,
                timezone="America/Los_Angeles",
            )
        )
        review_service._get_user_accent_preference = AsyncMock(return_value="us")
        review_service._fetch_first_meaning_sentence_map = AsyncMock(return_value={meaning_id: None})
        review_service._fetch_history_count_by_word_id = AsyncMock(return_value={word_id: 0})
        review_service._build_card_prompt = AsyncMock(return_value={"prompt_type": "definition_to_entry"})
        review_service._build_word_detail_payload = AsyncMock(
            return_value={"entry_type": "word", "entry_id": str(word_id), "display_text": "candidate"}
        )
        monkeypatch.setattr(review_module, "datetime", _frozen_datetime_class(now))

        due_items = await review_service.get_due_queue_items(user_id=user_id, limit=10)
        review_service._list_active_queue_states = AsyncMock(return_value=[state])
        mock_db.execute.side_effect = [aggregate_result]
        stats = await review_service.get_queue_stats(user_id)

        assert len(due_items) == stats["due_items"] == 1


class TestGroupedReviewQueue:
    @pytest.mark.asyncio
    async def test_get_grouped_review_queue_summary_keeps_already_due_card_due_after_timezone_change(
        self, review_service
    ):
        now = datetime(2026, 4, 10, 20, 0, tzinfo=timezone.utc)
        user_id = uuid.uuid4()
        state = EntryReviewState(
            id=uuid.uuid4(),
            user_id=user_id,
            entry_type="word",
            entry_id=uuid.uuid4(),
            target_type="meaning",
            target_id=uuid.uuid4(),
            stability=3,
            difficulty=0.5,
        )
        _set_canonical_schedule(state, datetime(2026, 4, 10, 18, 0, tzinfo=timezone.utc), user_timezone="America/Los_Angeles")
        state.entry_text = "candidate"
        state.learner_status = "learning"

        review_service._list_active_queue_states = AsyncMock(return_value=[state])
        review_service._get_user_review_preferences = AsyncMock(
            return_value=MagicMock(timezone="America/Los_Angeles")
        )

        payload = await review_service.get_grouped_review_queue_summary(user_id=user_id, now=now)

        assert payload == {
            "generated_at": now.isoformat(),
            "total_count": 1,
            "groups": [
                {"bucket": "3d", "count": 1, "has_due_now": True},
            ],
        }

    @pytest.mark.asyncio
    async def test_get_grouped_review_queue_bucket_detail_includes_progress_and_history(
        self, review_service, mock_db
    ):
        user_id = uuid.uuid4()
        entry_id = uuid.uuid4()
        state = EntryReviewState(
            id=uuid.uuid4(),
            user_id=user_id,
            entry_type="word",
            entry_id=entry_id,
            target_type="meaning",
            target_id=uuid.uuid4(),
            stability=3,
            difficulty=0.5,
            success_streak=3,
            lapse_count=1,
            exposure_count=5,
            times_remembered=4,
        )
        _set_canonical_schedule(state, datetime(2026, 4, 5, 12, 0, tzinfo=timezone.utc))
        state.last_reviewed_at = datetime(2026, 4, 4, 9, 0, tzinfo=timezone.utc)
        state.created_at = datetime(2026, 4, 1, 9, 0, tzinfo=timezone.utc)
        state.srs_bucket = "3d"
        state.cadence_step = 2

        state_result = MagicMock()
        state_result.all.return_value = [(state, "learning")]
        word_result = MagicMock()
        word_result.all.return_value = [(entry_id, "candidate")]
        event_one = EntryReviewEvent(
            id=uuid.uuid4(),
            user_id=user_id,
            review_state_id=state.id,
            entry_type="word",
            entry_id=entry_id,
            prompt_type="confidence_check",
            prompt_family="recognition",
            outcome="correct_tested",
            scheduled_interval_days=30,
            scheduled_by="recommended",
        )
        event_one.created_at = datetime(2026, 4, 4, 9, 0, tzinfo=timezone.utc)
        event_two = EntryReviewEvent(
            id=uuid.uuid4(),
            user_id=user_id,
            review_state_id=state.id,
            entry_type="word",
            entry_id=entry_id,
            prompt_type="typed_recall",
            prompt_family="production",
            outcome="failed",
            scheduled_interval_days=1,
            scheduled_by="manual_override",
        )
        event_two.created_at = datetime(2026, 4, 2, 8, 0, tzinfo=timezone.utc)
        event_result = MagicMock()
        event_result.scalars.return_value.all.return_value = [event_one, event_two]
        mock_db.execute.side_effect = [state_result, word_result, event_result]

        payload = await review_service.get_grouped_review_queue_bucket_detail(
            user_id=user_id,
            now=datetime(2026, 4, 5, 9, 0, tzinfo=timezone.utc),
            bucket="3d",
        )

        assert payload["count"] == 1
        item = payload["items"][0]
        assert item["text"] == "candidate"
        assert item["success_streak"] == 3
        assert item["lapse_count"] == 1
        assert item["times_remembered"] == 4
        assert item["exposure_count"] == 5
        assert item["history"] == [
            {
                "id": str(event_one.id),
                "reviewed_at": "2026-04-04T09:00:00+00:00",
                "outcome": "correct_tested",
                "prompt_type": "confidence_check",
                "prompt_family": "recognition",
                "scheduled_by": "recommended",
                "scheduled_interval_days": 30,
            },
            {
                "id": str(event_two.id),
                "reviewed_at": "2026-04-02T08:00:00+00:00",
                "outcome": "failed",
                "prompt_type": "typed_recall",
                "prompt_family": "production",
                "scheduled_by": "manual_override",
                "scheduled_interval_days": 1,
            },
        ]

    @pytest.mark.asyncio
    async def test_get_due_queue_items_prefers_entry_review_state(
        self, review_service, mock_db
    ):
        user_id = uuid.uuid4()
        word_id = uuid.uuid4()
        meaning_id = uuid.uuid4()
        state = EntryReviewState(
            id=uuid.uuid4(),
            user_id=user_id,
            entry_type="word",
            entry_id=word_id,
            stability=6,
            difficulty=0.5,
        )
        _set_canonical_schedule(state, datetime.now(timezone.utc) - timedelta(minutes=5))
        word = Word(id=word_id, word="jump the gun", language="en")
        meanings = [
            Meaning(id=meaning_id, word_id=word_id, definition="To do something too soon."),
            Meaning(id=uuid.uuid4(), word_id=word_id, definition="To act before the proper time."),
        ]

        state_result = MagicMock()
        state_result.scalars.return_value.all.return_value = [state]
        word_result = MagicMock()
        word_result.scalars.return_value.all.return_value = [word]
        meanings_result = MagicMock()
        meanings_result.scalars.return_value.all.return_value = meanings
        mock_db.execute.side_effect = [state_result, word_result, meanings_result]
        review_service._get_user_review_preferences = AsyncMock(
            return_value=MagicMock(
                review_depth_preset="balanced",
                enable_confidence_check=True,
                enable_audio_spelling=False,
            )
        )
        review_service._get_user_accent_preference = AsyncMock(return_value="us")
        review_service._fetch_first_meaning_sentence_map = AsyncMock(
            return_value={meaning_id: "They jumped the gun and announced it early."}
        )
        review_service._fetch_history_count_by_word_id = AsyncMock(return_value={word_id: 3})
        review_service._build_card_prompt = AsyncMock(
            return_value={"prompt_type": "entry_to_definition", "mode": "mcq"}
        )
        review_service._build_word_detail_payload = AsyncMock(
            return_value={"entry_type": "word", "entry_id": str(word_id), "display_text": "jump the gun"}
        )

        due_items = await review_service.get_due_queue_items(user_id=user_id, limit=10)

        assert len(due_items) == 1
        assert due_items[0]["source_entry_id"] == str(word_id)
        assert due_items[0]["detail"]["display_text"] == "jump the gun"
        assert due_items[0]["prompt"]["prompt_type"] in {
            "confidence_check",
            "definition_to_entry",
            "entry_to_definition",
            "audio_to_definition",
            "sentence_gap",
            "typed_recall",
        }

    @pytest.mark.asyncio
    async def test_get_due_queue_items_honors_manual_prompt_type_override(
        self, review_service, mock_db
    ):
        user_id = uuid.uuid4()
        word_id = uuid.uuid4()
        meaning_id = uuid.uuid4()
        state = EntryReviewState(
            id=uuid.uuid4(),
            user_id=user_id,
            entry_type="word",
            entry_id=word_id,
            target_type="meaning",
            target_id=meaning_id,
            stability=3,
            difficulty=0.5,
            last_submission_prompt_id="manual_prompt_type:speak_recall",
        )
        _set_canonical_schedule(state, datetime.now(timezone.utc) - timedelta(hours=1))
        word = Word(id=word_id, word="candidate", language="en")
        meanings = [Meaning(id=meaning_id, word_id=word_id, definition="A person who applies for a role.")]

        state_result = MagicMock()
        state_result.scalars.return_value.all.return_value = [state]
        word_result = MagicMock()
        word_result.scalars.return_value.all.return_value = [word]
        meanings_result = MagicMock()
        meanings_result.scalars.return_value.all.return_value = meanings
        mock_db.execute.side_effect = [state_result, word_result, meanings_result]
        review_service._get_user_accent_preference = AsyncMock(return_value="us")
        review_service._fetch_first_meaning_sentence_map = AsyncMock(return_value={meaning_id: None})
        review_service._fetch_history_count_by_word_id = AsyncMock(return_value={word_id: 0})
        review_service._build_word_detail_payload = AsyncMock(
            return_value={"entry_type": "word", "entry_id": str(word_id), "display_text": "candidate"}
        )
        review_service._build_card_prompt = AsyncMock(
            return_value={"prompt_type": "speak_recall", "audio_state": "ready"}
        )

        due_items = await review_service.get_due_queue_items(user_id=user_id, limit=10)

        assert len(due_items) == 1
        assert due_items[0]["review_mode"] == "mcq"
        review_service._build_card_prompt.assert_awaited_once()
        kwargs = review_service._build_card_prompt.await_args.kwargs
        assert kwargs["forced_prompt_type"] == "speak_recall"


class TestGroupedQueue:
    @pytest.mark.asyncio
    async def test_group_queue_items_buckets_states_by_due_window(self, review_service):
        now = datetime(2026, 4, 5, 9, 0, tzinfo=timezone.utc)
        user_id = uuid.uuid4()

        overdue = EntryReviewState(
            id=uuid.uuid4(),
            user_id=user_id,
            entry_type="word",
            entry_id=uuid.uuid4(),
            target_type="meaning",
            target_id=uuid.uuid4(),
            stability=3,
            difficulty=0.5,
        )
        _set_canonical_schedule(overdue, now - timedelta(hours=2))
        overdue.last_reviewed_at = now - timedelta(days=1)
        overdue.entry_text = "alpha"
        overdue.learner_status = "learning"
        overdue.srs_bucket = "1d"

        tomorrow = EntryReviewState(
            id=uuid.uuid4(),
            user_id=user_id,
            entry_type="phrase",
            entry_id=uuid.uuid4(),
            target_type="phrase_sense",
            target_id=uuid.uuid4(),
            stability=14,
            difficulty=0.5,
        )
        _set_canonical_schedule(tomorrow, now + timedelta(days=1, hours=1))
        tomorrow.last_reviewed_at = None
        tomorrow.entry_text = "break down"
        tomorrow.learner_status = "learning"
        tomorrow.srs_bucket = "7d"

        review_service._list_active_queue_states = AsyncMock(return_value=[overdue, tomorrow])

        payload = await review_service.get_grouped_review_queue(user_id=user_id, now=now)

        assert payload == {
            "generated_at": now.isoformat(),
            "total_count": 2,
            "groups": [
                {
                    "bucket": "1d",
                    "count": 1,
                    "items": [
                        {
                            "queue_item_id": str(overdue.id),
                            "entry_id": str(overdue.entry_id),
                            "entry_type": "word",
                            "text": "alpha",
                            "status": "learning",
                            "next_review_at": overdue.min_due_at_utc.isoformat(),
                            "due_review_date": overdue.due_review_date.isoformat(),
                            "min_due_at_utc": overdue.min_due_at_utc.isoformat(),
                            "last_reviewed_at": overdue.last_reviewed_at.isoformat(),
                            "bucket": "1d",
                        }
                    ],
                },
                {
                    "bucket": "7d",
                    "count": 1,
                    "items": [
                        {
                            "queue_item_id": str(tomorrow.id),
                            "entry_id": str(tomorrow.entry_id),
                            "entry_type": "phrase",
                            "text": "break down",
                            "status": "learning",
                            "next_review_at": tomorrow.min_due_at_utc.isoformat(),
                            "due_review_date": tomorrow.due_review_date.isoformat(),
                            "min_due_at_utc": tomorrow.min_due_at_utc.isoformat(),
                            "last_reviewed_at": None,
                            "bucket": "7d",
                        }
                    ],
                },
            ],
        }

    @pytest.mark.asyncio
    async def test_group_queue_items_excludes_known_and_to_learn_entries(
        self, review_service, mock_db
    ):
        now = datetime(2026, 4, 5, 9, 0, tzinfo=timezone.utc)
        user_id = uuid.uuid4()

        learning_state = EntryReviewState(
            id=uuid.uuid4(),
            user_id=user_id,
            entry_type="word",
            entry_id=uuid.uuid4(),
            target_type="meaning",
            target_id=uuid.uuid4(),
            stability=3,
            difficulty=0.5,
        )
        _set_canonical_schedule(learning_state, now + timedelta(hours=3))
        learning_state.last_reviewed_at = now - timedelta(days=1)
        learning_state.srs_bucket = "1d"

        known_state = EntryReviewState(
            id=uuid.uuid4(),
            user_id=user_id,
            entry_type="word",
            entry_id=uuid.uuid4(),
            target_type="meaning",
            target_id=uuid.uuid4(),
            stability=3,
            difficulty=0.5,
        )
        _set_canonical_schedule(known_state, now + timedelta(days=1))
        known_state.srs_bucket = "180d"

        to_learn_state = EntryReviewState(
            id=uuid.uuid4(),
            user_id=user_id,
            entry_type="word",
            entry_id=uuid.uuid4(),
            target_type="meaning",
            target_id=uuid.uuid4(),
            stability=3,
            difficulty=0.5,
        )
        _set_canonical_schedule(to_learn_state, now + timedelta(days=2))
        to_learn_state.srs_bucket = "2d"

        learning_status = LearnerEntryStatus(
            user_id=user_id,
            entry_type="word",
            entry_id=learning_state.entry_id,
            status="learning",
        )
        known_status = LearnerEntryStatus(
            user_id=user_id,
            entry_type="word",
            entry_id=known_state.entry_id,
            status="known",
        )
        to_learn_status = LearnerEntryStatus(
            user_id=user_id,
            entry_type="word",
            entry_id=to_learn_state.entry_id,
            status="to_learn",
        )

        state_result = MagicMock()
        state_result.all.return_value = [
            (learning_state, learning_status.status),
            (known_state, known_status.status),
            (to_learn_state, to_learn_status.status),
        ]
        state_result.scalars.return_value.all.return_value = [
            learning_state,
            known_state,
            to_learn_state,
        ]
        word_result = MagicMock()
        word_result.all.return_value = [
            (learning_state.entry_id, "alpha"),
            (known_state.entry_id, "bravo"),
            (to_learn_state.entry_id, "charlie"),
        ]
        mock_db.execute.side_effect = [state_result, word_result]

        payload = await review_service.get_grouped_review_queue(user_id=user_id, now=now)

        assert payload["generated_at"] == now.isoformat()
        assert payload["total_count"] == 1
        assert payload["groups"] == [
            {
                "bucket": "1d",
                "count": 1,
                "items": [
                    {
                        "queue_item_id": str(learning_state.id),
                        "entry_id": str(learning_state.entry_id),
                        "entry_type": "word",
                        "text": "alpha",
                        "status": "learning",
                        "next_review_at": learning_state.min_due_at_utc.isoformat(),
                        "due_review_date": learning_state.due_review_date.isoformat(),
                        "min_due_at_utc": learning_state.min_due_at_utc.isoformat(),
                        "last_reviewed_at": learning_state.last_reviewed_at.isoformat(),
                        "bucket": "1d",
                    }
                ],
            }
        ]
        included_ids = {
            item["queue_item_id"]
            for group in payload["groups"]
            for item in group["items"]
        }
        assert str(learning_state.id) in included_ids
        assert str(known_state.id) not in included_ids
        assert str(to_learn_state.id) not in included_ids

    @pytest.mark.asyncio
    async def test_group_queue_items_buries_sibling_targets_for_same_entry(
        self, review_service, mock_db
    ):
        now = datetime(2026, 4, 5, 9, 0, tzinfo=timezone.utc)
        user_id = uuid.uuid4()
        shared_entry_id = uuid.uuid4()

        first_sibling = EntryReviewState(
            id=uuid.uuid4(),
            user_id=user_id,
            entry_type="word",
            entry_id=shared_entry_id,
            target_type="meaning",
            target_id=uuid.uuid4(),
            stability=3,
            difficulty=0.5,
        )
        _set_canonical_schedule(first_sibling, now + timedelta(hours=1))

        second_sibling = EntryReviewState(
            id=uuid.uuid4(),
            user_id=user_id,
            entry_type="word",
            entry_id=shared_entry_id,
            target_type="meaning",
            target_id=uuid.uuid4(),
            stability=3,
            difficulty=0.5,
        )
        _set_canonical_schedule(second_sibling, now + timedelta(hours=2))

        other_entry = EntryReviewState(
            id=uuid.uuid4(),
            user_id=user_id,
            entry_type="word",
            entry_id=uuid.uuid4(),
            target_type="meaning",
            target_id=uuid.uuid4(),
            stability=3,
            difficulty=0.5,
        )
        _set_canonical_schedule(other_entry, now + timedelta(days=1))

        state_result = MagicMock()
        state_result.all.return_value = [
            (first_sibling, "learning"),
            (second_sibling, "learning"),
            (other_entry, "learning"),
        ]
        word_result = MagicMock()
        word_result.all.return_value = [
            (shared_entry_id, "alpha"),
            (other_entry.entry_id, "bravo"),
        ]
        mock_db.execute.side_effect = [state_result, word_result]

        payload = await review_service.get_grouped_review_queue(user_id=user_id, now=now)

        assert payload["total_count"] == 2
        item_ids = [
            item["queue_item_id"]
            for group in payload["groups"]
            for item in group["items"]
        ]
        assert str(first_sibling.id) in item_ids
        assert str(second_sibling.id) not in item_ids
        assert str(other_entry.id) in item_ids

    @pytest.mark.asyncio
    async def test_group_queue_items_skips_states_without_source_entry(
        self, review_service, mock_db
    ):
        now = datetime(2026, 4, 5, 9, 0, tzinfo=timezone.utc)
        user_id = uuid.uuid4()

        valid_state = EntryReviewState(
            id=uuid.uuid4(),
            user_id=user_id,
            entry_type="word",
            entry_id=uuid.uuid4(),
            target_type="meaning",
            target_id=uuid.uuid4(),
            stability=3,
            difficulty=0.5,
        )
        _set_canonical_schedule(valid_state, now + timedelta(hours=1))
        valid_state.srs_bucket = "1d"

        missing_state = EntryReviewState(
            id=uuid.uuid4(),
            user_id=user_id,
            entry_type="word",
            entry_id=uuid.uuid4(),
            target_type="meaning",
            target_id=uuid.uuid4(),
            stability=3,
            difficulty=0.5,
        )
        _set_canonical_schedule(missing_state, now + timedelta(hours=2))
        missing_state.srs_bucket = "2d"

        state_result = MagicMock()
        state_result.all.return_value = [
            (valid_state, "learning"),
            (missing_state, "learning"),
        ]
        word_result = MagicMock()
        word_result.all.return_value = [
            (valid_state.entry_id, "alpha"),
        ]
        mock_db.execute.side_effect = [state_result, word_result]

        payload = await review_service.get_grouped_review_queue(user_id=user_id, now=now)

        assert payload["total_count"] == 1
        assert payload["groups"] == [
            {
                "bucket": "1d",
                "count": 1,
                "items": [
                    {
                        "queue_item_id": str(valid_state.id),
                        "entry_id": str(valid_state.entry_id),
                        "entry_type": "word",
                        "text": "alpha",
                        "status": "learning",
                        "next_review_at": valid_state.min_due_at_utc.isoformat(),
                        "due_review_date": valid_state.due_review_date.isoformat(),
                        "min_due_at_utc": valid_state.min_due_at_utc.isoformat(),
                        "last_reviewed_at": None,
                        "bucket": "1d",
                    }
                ],
            }
        ]

    @pytest.mark.parametrize(
        ("due_at", "expected_bucket"),
        [
            (datetime(2026, 4, 5, 8, 59, 59, tzinfo=timezone.utc), "overdue"),
            (datetime(2026, 4, 5, 9, 0, 0, tzinfo=timezone.utc), "due_now"),
            (datetime(2026, 4, 5, 9, 0, 1, tzinfo=timezone.utc), "later_today"),
            (datetime(2026, 4, 6, 9, 0, 0, tzinfo=timezone.utc), "tomorrow"),
            (datetime(2026, 4, 12, 9, 0, 0, tzinfo=timezone.utc), "this_week"),
            (datetime(2026, 5, 6, 9, 0, 0, tzinfo=timezone.utc), "this_month"),
            (datetime(2026, 7, 6, 9, 0, 0, tzinfo=timezone.utc), "one_to_three_months"),
            (datetime(2026, 7, 9, 9, 0, 0, tzinfo=timezone.utc), "three_to_six_months"),
            (datetime(2026, 10, 6, 9, 0, 0, tzinfo=timezone.utc), "six_plus_months"),
        ],
    )
    def test_classify_review_bucket_handles_exact_boundaries(self, due_at, expected_bucket):
        now = datetime(2026, 4, 5, 9, 0, tzinfo=timezone.utc)

        assert ReviewService.classify_review_bucket(due_at, now) == expected_bucket

    def test_classify_review_bucket_uses_review_day_before_local_release_cutoff(self):
        now = datetime(2026, 4, 10, 14, 30, tzinfo=timezone.utc)
        due_at = datetime(2026, 4, 10, 18, 0, tzinfo=timezone.utc)

        assert (
            ReviewService.classify_review_bucket(
                due_at,
                now,
                due_review_date=date(2026, 4, 11),
                min_due_at_utc=due_at,
                user_timezone="Australia/Melbourne",
            )
            == "tomorrow"
        )

    @pytest.mark.asyncio
    async def test_get_grouped_review_queue_summary_returns_bucket_cards(self, review_service):
        now = datetime(2026, 4, 5, 9, 0, tzinfo=timezone.utc)
        user_id = uuid.uuid4()

        overdue = EntryReviewState(
            id=uuid.uuid4(),
            user_id=user_id,
            entry_type="word",
            entry_id=uuid.uuid4(),
            target_type="meaning",
            target_id=uuid.uuid4(),
            stability=3,
            difficulty=0.5,
        )
        _set_canonical_schedule(overdue, now - timedelta(hours=2))
        overdue.entry_text = "alpha"
        overdue.learner_status = "learning"
        overdue.srs_bucket = "1d"

        tomorrow = EntryReviewState(
            id=uuid.uuid4(),
            user_id=user_id,
            entry_type="phrase",
            entry_id=uuid.uuid4(),
            target_type="phrase_sense",
            target_id=uuid.uuid4(),
            stability=14,
            difficulty=0.5,
        )
        _set_canonical_schedule(tomorrow, now + timedelta(days=1, hours=1))
        tomorrow.entry_text = "break down"
        tomorrow.learner_status = "learning"
        tomorrow.srs_bucket = "7d"

        review_service._list_active_queue_states = AsyncMock(return_value=[overdue, tomorrow])

        payload = await review_service.get_grouped_review_queue_summary(user_id=user_id, now=now)

        assert payload == {
            "generated_at": now.isoformat(),
            "total_count": 2,
            "groups": [
                {"bucket": "1d", "count": 1, "has_due_now": True},
                {"bucket": "7d", "count": 1, "has_due_now": False},
            ],
        }

    @pytest.mark.asyncio
    async def test_get_grouped_review_queue_summary_excludes_items_missing_canonical_schedule(
        self, review_service
    ):
        now = datetime(2026, 4, 5, 9, 0, tzinfo=timezone.utc)
        user_id = uuid.uuid4()

        unscheduled = EntryReviewState(
            id=uuid.uuid4(),
            user_id=user_id,
            entry_type="word",
            entry_id=uuid.uuid4(),
            target_type="meaning",
            target_id=uuid.uuid4(),
            stability=1,
            difficulty=0.5,
        )
        _set_canonical_schedule(unscheduled, None)
        unscheduled.entry_text = "alpha"
        unscheduled.learner_status = "learning"
        unscheduled.srs_bucket = "1d"

        review_service._list_active_queue_states = AsyncMock(return_value=[unscheduled])

        payload = await review_service.get_grouped_review_queue_summary(user_id=user_id, now=now)

        assert payload["total_count"] == 0
        assert payload["groups"] == []

    @pytest.mark.asyncio
    async def test_get_grouped_review_queue_by_due_excludes_items_missing_canonical_schedule(
        self, review_service
    ):
        now = datetime(2026, 4, 5, 9, 0, tzinfo=timezone.utc)
        user_id = uuid.uuid4()

        due_now_state = EntryReviewState(
            id=uuid.uuid4(),
            user_id=user_id,
            entry_type="word",
            entry_id=uuid.uuid4(),
            target_type="meaning",
            target_id=uuid.uuid4(),
            stability=1,
            difficulty=0.5,
        )
        _set_canonical_schedule(due_now_state, None)
        due_now_state.entry_text = "persistence"
        due_now_state.learner_status = "learning"
        due_now_state.srs_bucket = "1d"

        future_state = EntryReviewState(
            id=uuid.uuid4(),
            user_id=user_id,
            entry_type="phrase",
            entry_id=uuid.uuid4(),
            target_type="phrase_sense",
            target_id=uuid.uuid4(),
            stability=3,
            difficulty=0.5,
        )
        _set_canonical_schedule(future_state, datetime(2026, 4, 7, 10, 0, tzinfo=timezone.utc))
        future_state.entry_text = "jump the gun"
        future_state.learner_status = "learning"
        future_state.srs_bucket = "3d"

        review_service._list_active_queue_states = AsyncMock(
            return_value=[future_state, due_now_state]
        )

        payload = await review_service.get_grouped_review_queue_by_due(user_id=user_id, now=now)

        assert payload["total_count"] == 1
        assert payload["groups"] == [
            {
                "group_key": "in_2_days",
                "label": "In 2 days",
                "due_in_days": 2,
                "count": 1,
                "items": [
                    {
                        "queue_item_id": str(future_state.id),
                        "entry_id": str(future_state.entry_id),
                        "entry_type": "phrase",
                        "text": "jump the gun",
                        "status": "learning",
                        "next_review_at": "2026-04-07T10:00:00+00:00",
                        "due_review_date": future_state.due_review_date.isoformat(),
                        "min_due_at_utc": future_state.min_due_at_utc.isoformat(),
                        "last_reviewed_at": None,
                        "bucket": "3d",
                    }
                ],
            },
        ]

    @pytest.mark.asyncio
    async def test_get_grouped_review_queue_by_due_keeps_due_now_and_later_today_separate(
        self, review_service
    ):
        now = datetime(2026, 4, 5, 9, 0, tzinfo=timezone.utc)
        user_id = uuid.uuid4()

        due_now_state = EntryReviewState(
            id=uuid.uuid4(),
            user_id=user_id,
            entry_type="word",
            entry_id=uuid.uuid4(),
            target_type="meaning",
            target_id=uuid.uuid4(),
            stability=1,
            difficulty=0.5,
        )
        _set_canonical_schedule(due_now_state, now)
        due_now_state.entry_text = "alpha"
        due_now_state.learner_status = "learning"
        due_now_state.srs_bucket = "1d"

        later_today_state = EntryReviewState(
            id=uuid.uuid4(),
            user_id=user_id,
            entry_type="word",
            entry_id=uuid.uuid4(),
            target_type="meaning",
            target_id=uuid.uuid4(),
            stability=1,
            difficulty=0.5,
        )
        _set_canonical_schedule(later_today_state, now + timedelta(seconds=1))
        later_today_state.entry_text = "beta"
        later_today_state.learner_status = "learning"
        later_today_state.srs_bucket = "1d"

        review_service._list_active_queue_states = AsyncMock(
            return_value=[later_today_state, due_now_state]
        )

        payload = await review_service.get_grouped_review_queue_by_due(user_id=user_id, now=now)

        assert [group["group_key"] for group in payload["groups"]] == ["due_now", "later_today"]
        assert [group["count"] for group in payload["groups"]] == [1, 1]

    @pytest.mark.asyncio
    async def test_get_grouped_review_queue_bucket_detail_sorts_by_requested_order(
        self, review_service
    ):
        now = datetime(2026, 4, 5, 9, 0, tzinfo=timezone.utc)
        user_id = uuid.uuid4()

        earliest = EntryReviewState(
            id=uuid.uuid4(),
            user_id=user_id,
            entry_type="word",
            entry_id=uuid.uuid4(),
            target_type="meaning",
            target_id=uuid.uuid4(),
            stability=3,
            difficulty=0.5,
        )
        _set_canonical_schedule(earliest, now + timedelta(minutes=15))
        earliest.last_reviewed_at = now - timedelta(days=3)
        earliest.entry_text = "gamma"
        earliest.learner_status = "learning"
        earliest.srs_bucket = "1d"

        latest = EntryReviewState(
            id=uuid.uuid4(),
            user_id=user_id,
            entry_type="word",
            entry_id=uuid.uuid4(),
            target_type="meaning",
            target_id=uuid.uuid4(),
            stability=3,
            difficulty=0.5,
        )
        _set_canonical_schedule(latest, now + timedelta(hours=4))
        latest.last_reviewed_at = now - timedelta(days=1)
        latest.entry_text = "alpha"
        latest.learner_status = "learning"
        latest.srs_bucket = "1d"

        middle = EntryReviewState(
            id=uuid.uuid4(),
            user_id=user_id,
            entry_type="phrase",
            entry_id=uuid.uuid4(),
            target_type="phrase_sense",
            target_id=uuid.uuid4(),
            stability=3,
            difficulty=0.5,
        )
        _set_canonical_schedule(middle, now + timedelta(hours=2))
        middle.last_reviewed_at = now - timedelta(days=2)
        middle.entry_text = "beta"
        middle.learner_status = "learning"
        middle.srs_bucket = "1d"

        review_service._list_active_queue_states = AsyncMock(return_value=[latest, middle, earliest])

        payload = await review_service.get_grouped_review_queue_bucket_detail(
            user_id=user_id,
            now=now,
            bucket="1d",
            sort="next_review_at",
            order="asc",
        )

        assert payload["bucket"] == "1d"
        assert payload["count"] == 3
        assert payload["sort"] == "next_review_at"
        assert payload["order"] == "asc"
        assert [item["text"] for item in payload["items"]] == ["gamma", "beta", "alpha"]

    def test_build_current_schedule_payload_serializes_canonical_due_time_for_display(self):
        now = datetime(2026, 4, 5, 9, 0, tzinfo=timezone.utc)
        state = EntryReviewState(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            entry_type="word",
            entry_id=uuid.uuid4(),
            stability=7,
            difficulty=0.5,
        )
        _set_canonical_schedule(state, now + timedelta(days=3))
        state.recheck_due_at = None

        payload = ReviewService._build_current_schedule_payload(state, now=now, user_timezone="UTC")

        assert payload["queue_item_id"] == str(state.id)
        assert payload["due_review_date"] == state.due_review_date.isoformat()
        assert payload["min_due_at_utc"] == state.min_due_at_utc.isoformat()
        assert payload["current_schedule_value"] == "3d"
        assert payload["current_schedule_label"] == "In 3 days"
        assert "next_review_at" not in payload
        assert "current_schedule_source" not in payload
        assert next(
            option for option in payload["schedule_options"] if option["value"] == "3d"
        )["is_default"] is True

    def test_build_current_schedule_payload_uses_review_day_for_pre_release_next_day_schedule(self):
        now = datetime(2026, 4, 10, 14, 30, tzinfo=timezone.utc)
        state = EntryReviewState(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            entry_type="word",
            entry_id=uuid.uuid4(),
            stability=1,
            difficulty=0.5,
        )
        state.due_review_date = date(2026, 4, 11)
        state.min_due_at_utc = datetime(2026, 4, 10, 18, 0, tzinfo=timezone.utc)
        state.recheck_due_at = None

        payload = ReviewService._build_current_schedule_payload(
            state,
            now=now,
            user_timezone="Australia/Melbourne",
        )

        assert payload["current_schedule_value"] == "1d"
        assert payload["current_schedule_label"] == "Tomorrow"
        assert payload["due_review_date"] == "2026-04-11"
        assert payload["min_due_at_utc"] == state.min_due_at_utc.isoformat()
        assert "next_review_at" not in payload
        assert "current_schedule_source" not in payload

    def test_build_current_schedule_payload_serializes_canonical_fields_without_legacy_normal_schedule_keys(
        self,
    ):
        now = datetime(2026, 4, 10, 14, 30, tzinfo=timezone.utc)
        state = EntryReviewState(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            entry_type="word",
            entry_id=uuid.uuid4(),
            stability=1,
            difficulty=0.5,
        )
        state.due_review_date = date(2026, 4, 11)
        state.min_due_at_utc = datetime(2026, 4, 10, 18, 0, tzinfo=timezone.utc)
        state.recheck_due_at = None

        payload = ReviewService._build_current_schedule_payload(
            state,
            now=now,
            user_timezone="Australia/Melbourne",
        )

        assert payload["queue_item_id"] == str(state.id)
        assert payload["current_schedule_value"] == "1d"
        assert payload["current_schedule_label"] == "Tomorrow"
        assert payload["due_review_date"] == "2026-04-11"
        assert payload["min_due_at_utc"] == state.min_due_at_utc.isoformat()
        assert "next_review_at" not in payload
        assert "current_schedule_source" not in payload

    def test_build_current_schedule_payload_uses_sticky_due_for_westward_timezone_change(self):
        now = datetime(2026, 4, 10, 20, 0, tzinfo=timezone.utc)
        state = EntryReviewState(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            entry_type="word",
            entry_id=uuid.uuid4(),
            stability=1,
            difficulty=0.5,
        )
        state.due_review_date = date(2026, 4, 11)
        state.min_due_at_utc = datetime(2026, 4, 10, 18, 0, tzinfo=timezone.utc)
        state.recheck_due_at = None

        payload = ReviewService._build_current_schedule_payload(
            state,
            now=now,
            user_timezone="America/Los_Angeles",
        )

        assert payload["current_schedule_value"] == "1d"
        assert payload["current_schedule_label"] == "Tomorrow"
        assert payload["due_review_date"] == "2026-04-11"
        assert payload["min_due_at_utc"] == state.min_due_at_utc.isoformat()
        assert "next_review_at" not in payload
        assert "current_schedule_source" not in payload

    def test_effective_due_at_uses_official_review_day_fields(self):
        state = EntryReviewState(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            entry_type="word",
            entry_id=uuid.uuid4(),
            stability=1,
            difficulty=0.5,
        )
        state.recheck_due_at = None
        state.due_review_date = date(2026, 4, 11)
        state.min_due_at_utc = datetime(2026, 4, 10, 18, 0, tzinfo=timezone.utc)
        assert ReviewService._effective_due_at(state) == state.min_due_at_utc

    def test_build_current_schedule_payload_uses_official_fields_when_present(
        self,
    ):
        now = datetime(2026, 4, 10, 14, 30, tzinfo=timezone.utc)
        state = EntryReviewState(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            entry_type="word",
            entry_id=uuid.uuid4(),
            stability=1,
            difficulty=0.5,
        )
        state.recheck_due_at = None
        state.due_review_date = date(2026, 4, 11)
        state.min_due_at_utc = datetime(2026, 4, 10, 18, 0, tzinfo=timezone.utc)
        payload = ReviewService._build_current_schedule_payload(
            state,
            now=now,
            user_timezone="Australia/Melbourne",
        )

        assert payload["current_schedule_value"] == "1d"
        assert payload["current_schedule_label"] == "Tomorrow"
        assert payload["due_review_date"] == "2026-04-11"
        assert payload["min_due_at_utc"] == state.min_due_at_utc.isoformat()
        assert "next_review_at" not in payload
        assert "current_schedule_source" not in payload

    def test_build_current_schedule_payload_uses_short_horizon_value_for_same_day_recheck(self):
        now = datetime(2026, 4, 10, 14, 30, tzinfo=timezone.utc)
        state = EntryReviewState(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            entry_type="word",
            entry_id=uuid.uuid4(),
            stability=1,
            difficulty=0.5,
        )
        state.recheck_due_at = now + timedelta(minutes=10)
        payload = ReviewService._build_current_schedule_payload(state, now=now)

        assert payload["current_schedule_value"] == "10m"
        assert payload["current_schedule_label"] == "Later today"
        assert payload["next_review_at"] == state.recheck_due_at.isoformat()
        assert payload["schedule_options"][0] == {
            "value": "10m",
            "label": "Later today",
            "is_default": True,
        }

    def test_build_current_schedule_payload_keeps_next_day_meaning_for_rolled_recheck(self):
        now = datetime(2026, 4, 15, 13, 55, tzinfo=timezone.utc)
        state = EntryReviewState(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            entry_type="word",
            entry_id=uuid.uuid4(),
            stability=1,
            difficulty=0.5,
        )
        state.due_review_date = date(2026, 4, 16)
        state.min_due_at_utc = datetime(2026, 4, 15, 18, 0, tzinfo=timezone.utc)
        state.recheck_due_at = state.min_due_at_utc
        payload = ReviewService._build_current_schedule_payload(
            state,
            now=now,
            user_timezone="Australia/Melbourne",
        )

        assert payload["current_schedule_value"] == "1d"
        assert payload["current_schedule_label"] == "Tomorrow"
        assert payload["schedule_options"][0]["value"] == "1d"

    def test_long_horizon_success_sequence_reaches_multi_month_bucket(self):
        now = datetime(2026, 4, 5, 9, 0, tzinfo=timezone.utc)
        due_at = now
        stability = 3.0
        difficulty = 0.5

        for _ in range(7):
            result = calculate_next_review(
                outcome="correct_tested",
                prompt_type="typed_recall",
                stability=stability,
                difficulty=difficulty,
                grade="easy_pass",
            )
            due_at = due_at + timedelta(days=result.interval_days)
            stability = result.stability
            difficulty = result.difficulty

        assert ReviewService.classify_review_bucket(due_at, now) == "three_to_six_months"


class TestQueueSubmit:
    @pytest.mark.asyncio
    async def test_submit_queue_review_applies_sm2_and_increments_counters(
        self, review_service, mock_db
    ):
        user_id = uuid.uuid4()
        word_id = uuid.uuid4()
        meaning_id = uuid.uuid4()
        state = EntryReviewState(
            id=uuid.uuid4(),
            user_id=user_id,
            entry_type="word",
            entry_id=word_id,
            target_type="meaning",
            target_id=meaning_id,
            stability=1,
            difficulty=0.5,
            success_streak=1,
        )
        state.interval_days = 1
        locked_result = MagicMock()
        locked_result.scalar_one_or_none.return_value = state
        learner_status_result = MagicMock()
        learner_status_result.scalar_one_or_none.return_value = LearnerEntryStatus(
            user_id=user_id,
            entry_type="word",
            entry_id=word_id,
            status="learning",
        )
        mock_db.execute.side_effect = [locked_result, learner_status_result]
        review_service._build_detail_payload_for_word_id = AsyncMock(
            return_value={"entry_type": "word", "entry_id": str(word_id), "display_text": "resilience"}
        )
        prompt_token = review_service._encode_prompt_token(
            {
                "prompt_id": str(uuid.uuid4()),
                "user_id": str(user_id),
                "queue_item_id": str(state.id),
                "prompt_type": ReviewService.PROMPT_TYPE_DEFINITION_TO_ENTRY,
                "review_mode": ReviewService.REVIEW_MODE_MCQ,
                "source_entry_type": "word",
                "source_entry_id": str(word_id),
                "source_meaning_id": str(meaning_id),
                "correct_option_id": "A",
            }
        )

        updated = await review_service.submit_queue_review(
            item_id=state.id,
            quality=5,
            time_spent_ms=1500,
            user_id=user_id,
            prompt_token=prompt_token,
            selected_option_id="A",
            confirm=True,
        )

        assert updated.stability >= 1
        assert updated.interval_days >= 1
        assert updated.success_streak == 2
        assert updated.times_remembered == 1
        assert updated.outcome == "correct_tested"
        mock_db.commit.assert_awaited_once()
        assert any(
            isinstance(call.args[0], EntryReviewEvent) for call in mock_db.add.call_args_list
        )

    @pytest.mark.asyncio
    async def test_submit_queue_review_returns_success_preview_without_committing_until_confirmed(
        self, review_service, mock_db
    ):
        user_id = uuid.uuid4()
        word_id = uuid.uuid4()
        meaning_id = uuid.uuid4()
        state = EntryReviewState(
            id=uuid.uuid4(),
            user_id=user_id,
            entry_type="word",
            entry_id=word_id,
            target_type="meaning",
            target_id=meaning_id,
            stability=3,
            difficulty=0.4,
        )
        state_lookup_result = MagicMock()
        state_lookup_result.scalar_one_or_none.return_value = state
        mock_db.execute.side_effect = [state_lookup_result]
        review_service._build_detail_payload_for_word_id = AsyncMock(
            return_value={
                "entry_type": "word",
                "entry_id": str(word_id),
                "display_text": "barely",
                "meaning_count": 1,
                "remembered_count": 0,
                "compare_with": [],
                "meanings": [],
            }
        )

        prompt_token = review_service._encode_prompt_token(
            {
                "prompt_id": str(uuid.uuid4()),
                "user_id": str(user_id),
                "queue_item_id": str(state.id),
                "prompt_type": ReviewService.PROMPT_TYPE_DEFINITION_TO_ENTRY,
                "review_mode": ReviewService.REVIEW_MODE_MCQ,
                "source_entry_type": "word",
                "source_entry_id": str(word_id),
                "source_meaning_id": str(meaning_id),
                "correct_option_id": "A",
            }
        )

        updated = await review_service.submit_queue_review(
            item_id=state.id,
            quality=5,
            time_spent_ms=1500,
            user_id=user_id,
            prompt_token=prompt_token,
            selected_option_id="A",
        )

        assert updated is state
        assert updated.outcome == "correct_tested"
        assert updated.detail == {
            "entry_type": "word",
            "entry_id": str(word_id),
            "display_text": "barely",
            "meaning_count": 1,
            "remembered_count": 0,
            "compare_with": [],
            "meanings": [],
        }
        assert updated.last_submission_prompt_id is None
        mock_db.add.assert_not_called()
        mock_db.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_submit_queue_review_updates_entry_review_state_and_sets_recheck(
        self, review_service, mock_db
    ):
        user_id = uuid.uuid4()
        word_id = uuid.uuid4()
        state = EntryReviewState(
            id=uuid.uuid4(),
            user_id=user_id,
            entry_type="word",
            entry_id=word_id,
            stability=6,
            difficulty=0.5,
            success_streak=2,
        )
        state_lookup_result = MagicMock()
        state_lookup_result.scalar_one_or_none.return_value = state
        learner_status_result = MagicMock()
        learner_status_result.scalar_one_or_none.return_value = LearnerEntryStatus(
            user_id=user_id,
            entry_type="word",
            entry_id=word_id,
            status="learning",
        )
        word_lookup_result = MagicMock()
        word_lookup_result.scalar_one_or_none.return_value = Word(id=word_id, word="barely", language="en")
        meanings_result = MagicMock()
        meanings_result.scalars.return_value.all.return_value = [
            Meaning(id=uuid.uuid4(), word_id=word_id, definition="Only just, by a very small margin.")
        ]
        sentence_result = MagicMock()
        sentence_result.scalar_one_or_none.return_value = "He barely made it through the door."
        accent_result = MagicMock()
        accent_result.scalar_one_or_none.return_value = "us"
        history_count_result = MagicMock()
        history_count_result.scalar_one.return_value = 4
        prompt_token = review_service._encode_prompt_token(
            {
                "prompt_id": str(uuid.uuid4()),
                "user_id": str(user_id),
                "queue_item_id": str(state.id),
                "prompt_type": ReviewService.PROMPT_TYPE_SENTENCE_GAP,
                "review_mode": ReviewService.REVIEW_MODE_MCQ,
                "source_entry_type": "word",
                "source_entry_id": str(word_id),
                "source_meaning_id": str(uuid.uuid4()),
                "correct_option_id": "A",
            }
        )
        mock_db.execute.side_effect = [
            state_lookup_result,
            learner_status_result,
        ]
        review_service._build_detail_payload_for_word_id = AsyncMock(
            return_value={"entry_type": "word", "entry_id": str(word_id), "display_text": "barely"}
        )

        updated = await review_service.submit_queue_review(
            item_id=state.id,
            quality=1,
            time_spent_ms=1500,
            user_id=user_id,
            outcome="wrong",
            prompt_token=prompt_token,
        )

        assert updated.outcome == "wrong"
        assert updated.relearning is True
        assert updated.relearning_trigger == "wrong"
        assert updated.recheck_due_at is not None
        assert updated.needs_relearn is True
        assert updated.recheck_planned is True
        mock_db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_submit_queue_review_rolls_late_night_recheck_to_next_day_canonical_release(
        self, review_service, mock_db, monkeypatch
    ):
        user_id = uuid.uuid4()
        word_id = uuid.uuid4()
        reviewed_at = datetime(2026, 4, 15, 13, 55, tzinfo=timezone.utc)
        state = EntryReviewState(
            id=uuid.uuid4(),
            user_id=user_id,
            entry_type="word",
            entry_id=word_id,
            stability=6,
            difficulty=0.5,
            success_streak=2,
        )
        state_lookup_result = MagicMock()
        state_lookup_result.scalar_one_or_none.return_value = state
        learner_status_result = MagicMock()
        learner_status_result.scalar_one_or_none.return_value = LearnerEntryStatus(
            user_id=user_id,
            entry_type="word",
            entry_id=word_id,
            status="learning",
        )
        prompt_token = review_service._encode_prompt_token(
            {
                "prompt_id": str(uuid.uuid4()),
                "user_id": str(user_id),
                "queue_item_id": str(state.id),
                "prompt_type": ReviewService.PROMPT_TYPE_SENTENCE_GAP,
                "review_mode": ReviewService.REVIEW_MODE_MCQ,
                "source_entry_type": "word",
                "source_entry_id": str(word_id),
                "source_meaning_id": str(uuid.uuid4()),
                "correct_option_id": "A",
            }
        )
        mock_db.execute.side_effect = [
            state_lookup_result,
            learner_status_result,
        ]
        review_service._get_user_review_preferences = AsyncMock(
            return_value=MagicMock(
                timezone="Australia/Melbourne",
                review_depth_preset="balanced",
                enable_confidence_check=True,
            )
        )
        review_service._build_detail_payload_for_word_id = AsyncMock(
            return_value={"entry_type": "word", "entry_id": str(word_id), "display_text": "barely"}
        )
        monkeypatch.setattr(review_submission_module, "datetime", _frozen_datetime_class(reviewed_at))

        updated = await review_service.submit_queue_review(
            item_id=state.id,
            quality=1,
            time_spent_ms=1500,
            user_id=user_id,
            outcome="wrong",
            prompt_token=prompt_token,
        )

        assert updated.outcome == "wrong"
        assert updated.relearning is True
        assert updated.relearning_trigger == "wrong"
        assert updated.due_review_date == due_review_date_for_bucket(
            reviewed_at_utc=reviewed_at,
            user_timezone="Australia/Melbourne",
            bucket="1d",
        )
        assert updated.min_due_at_utc == min_due_at_for_bucket(
            reviewed_at_utc=reviewed_at,
            user_timezone="Australia/Melbourne",
            bucket="1d",
        )
        assert updated.recheck_due_at == updated.min_due_at_utc
        assert updated.recheck_due_at != reviewed_at + timedelta(minutes=10)

    @pytest.mark.asyncio
    async def test_submit_queue_review_records_typed_analytics_fields(
        self, review_service, mock_db
    ):
        user_id = uuid.uuid4()
        word_id = uuid.uuid4()
        state = EntryReviewState(
            id=uuid.uuid4(),
            user_id=user_id,
            entry_type="word",
            entry_id=word_id,
            stability=2,
            difficulty=0.5,
        )
        state_lookup_result = MagicMock()
        state_lookup_result.scalar_one_or_none.return_value = state
        learner_status_result = MagicMock()
        learner_status_result.scalar_one_or_none.return_value = LearnerEntryStatus(
            user_id=user_id,
            entry_type="word",
            entry_id=word_id,
            status="learning",
        )
        word_lookup_result = MagicMock()
        word_lookup_result.scalar_one_or_none.return_value = Word(id=word_id, word="resilience", language="en")
        meanings_result = MagicMock()
        meanings_result.scalars.return_value.all.return_value = [
            Meaning(id=uuid.uuid4(), word_id=word_id, definition="The capacity to recover quickly from difficulties.")
        ]
        sentence_result = MagicMock()
        sentence_result.scalar_one_or_none.return_value = "Resilience helps teams adapt to change."
        accent_result = MagicMock()
        accent_result.scalar_one_or_none.return_value = "us"
        history_count_result = MagicMock()
        history_count_result.scalar_one.return_value = 2
        source_meaning_id = uuid.uuid4()
        prompt_token = review_service._encode_prompt_token(
            {
                "prompt_id": str(uuid.uuid4()),
                "user_id": str(user_id),
                "queue_item_id": str(state.id),
                "prompt_type": ReviewService.PROMPT_TYPE_TYPED_RECALL,
                "review_mode": ReviewService.REVIEW_MODE_MCQ,
                "input_mode": "typed",
                "source_entry_type": "word",
                "source_entry_id": str(word_id),
                "source_meaning_id": str(source_meaning_id),
                "expected_input": "resilience",
            }
        )
        mock_db.execute.side_effect = [
            state_lookup_result,
            learner_status_result,
        ]
        review_service._build_detail_payload_for_word_id = AsyncMock(
            return_value={"entry_type": "word", "entry_id": str(word_id), "display_text": "resilience"}
        )

        await review_service.submit_queue_review(
            item_id=state.id,
            quality=4,
            time_spent_ms=1200,
            user_id=user_id,
            prompt_token=prompt_token,
            typed_answer="resilience",
            confirm=True,
        )

        event = next(
            call.args[0]
            for call in mock_db.add.call_args_list
            if call.args and hasattr(call.args[0], "prompt_type")
        )
        assert event.prompt_family == "typed_recall"
        assert event.target_type == "meaning"
        assert event.target_id is not None
        assert event.response_input_mode == "typed"
        assert event.response_value == "resilience"
        assert event.used_audio_placeholder is False
        assert event.audio_replay_count == 0


class TestAnalyticsSummary:
    @pytest.mark.asyncio
    async def test_get_review_analytics_summary_groups_recent_events(
        self, review_service, mock_db
    ):
        total_result = MagicMock()
        total_result.scalar_one.return_value = 5
        placeholder_result = MagicMock()
        placeholder_result.scalar_one.return_value = 1
        prompt_family_result = MagicMock()
        prompt_family_result.all.return_value = [
            MagicMock(value="typed_recall", count=3),
            MagicMock(value="situation", count=2),
        ]
        outcome_result = MagicMock()
        outcome_result.all.return_value = [
            MagicMock(value="correct_tested", count=4),
            MagicMock(value="wrong", count=1),
        ]
        input_mode_result = MagicMock()
        input_mode_result.all.return_value = [
            MagicMock(value="typed", count=3),
            MagicMock(value="choice", count=2),
        ]
        audio_replay_total_result = MagicMock()
        audio_replay_total_result.scalar_one.return_value = 7
        audio_replay_count_result = MagicMock()
        audio_replay_count_result.all.return_value = [
            MagicMock(value=0, count=3),
            MagicMock(value=1, count=2),
        ]
        mock_db.execute.side_effect = [
            total_result,
            placeholder_result,
            prompt_family_result,
            outcome_result,
            input_mode_result,
            audio_replay_total_result,
            audio_replay_count_result,
        ]

        summary = await review_service.get_review_analytics_summary(uuid.uuid4(), days=14)

        assert summary["days"] == 14
        assert summary["total_events"] == 5
        assert summary["audio_placeholder_events"] == 1
        assert summary["prompt_families"] == [
            {"value": "typed_recall", "count": 3},
            {"value": "situation", "count": 2},
        ]
        assert summary["outcomes"] == [
            {"value": "correct_tested", "count": 4},
            {"value": "wrong", "count": 1},
        ]
        assert summary["response_input_modes"] == [
            {"value": "typed", "count": 3},
            {"value": "choice", "count": 2},
        ]
        assert summary["total_audio_replays"] == 7
        assert summary["audio_replay_counts"] == [
            {"value": "0", "count": 3},
            {"value": "1", "count": 2},
        ]


class TestPromptFamilies:
    def test_select_review_mode_respects_confidence_setting(self, review_service):
        item = MagicMock(id=uuid.UUID(int=0))

        assert (
            review_service._select_review_mode(
                item=item,
                word="bank",
                sentence="We sat on the river bank.",
                allow_confidence=True,
            )
            == ReviewService.REVIEW_MODE_CONFIDENCE
        )
        assert (
            review_service._select_review_mode(
                item=item,
                word="bank",
                sentence="We sat on the river bank.",
                allow_confidence=False,
            )
            == ReviewService.REVIEW_MODE_MCQ
        )

    def test_build_mcq_options_uses_only_real_choices_when_distractors_are_thin(
        self, review_service
    ):
        options = review_service._build_mcq_options(
            correct="barely",
            distractors=["bravely", "rarely"],
        )

        assert len(options) == 3
        assert {option["label"] for option in options} == {"barely", "bravely", "rarely"}
        assert not any(option["label"].startswith("Option ") for option in options)

    @pytest.mark.asyncio
    async def test_build_review_prompt_sets_definition_to_entry_answer_to_entry(
        self, review_service, mock_db
    ):
        distractor_result = MagicMock()
        distractor_result.scalars.return_value.all.return_value = [
            "bravely",
            "rarely",
            "boldly",
        ]
        mock_db.execute.return_value = distractor_result

        prompt = await review_service._build_mandated_prompt(
            review_mode=ReviewService.REVIEW_MODE_MCQ,
            prompt_type=ReviewService.PROMPT_TYPE_DEFINITION_TO_ENTRY,
            word="barely",
            definition="Only just, by a very small margin.",
            distractors=["bravely", "rarely", "boldly"],
            sentence=None,
            target_is_word=True,
            alternative_definitions=None,
        )

        correct = next(option for option in prompt["options"] if option["is_correct"])
        assert correct["label"] == "barely"

    @pytest.mark.asyncio
    async def test_build_review_prompt_sets_entry_to_definition_answer_to_definition(
        self, review_service, mock_db
    ):
        distractor_result = MagicMock()
        distractor_result.scalars.return_value.all.return_value = [
            "Acting with courage.",
            "Almost never.",
            "With full confidence.",
        ]
        mock_db.execute.return_value = distractor_result

        prompt = await review_service._build_mandated_prompt(
            review_mode=ReviewService.REVIEW_MODE_MCQ,
            prompt_type=ReviewService.PROMPT_TYPE_ENTRY_TO_DEFINITION,
            word="barely",
            definition="Only just, by a very small margin.",
            distractors=[
                "Acting with courage.",
                "Almost never.",
                "With full confidence.",
            ],
            sentence=None,
            target_is_word=False,
            alternative_definitions=None,
        )

        correct = next(option for option in prompt["options"] if option["is_correct"])
        assert correct["label"] == "Only just, by a very small margin."

    @pytest.mark.asyncio
    async def test_build_card_prompt_supports_meaning_discrimination_when_forced(
        self, review_service, mock_db
    ):
        prompt = await review_service._build_card_prompt(
            review_mode=ReviewService.REVIEW_MODE_MCQ,
            source_text="rocky",
            definition="Covered with rocks.",
            sentence=None,
            is_phrase_entry=False,
            distractor_seed="seed",
            meaning_id=uuid.uuid4(),
            index=0,
            alternative_definitions=[
                "Unstable and likely to fail.",
                "Difficult because of problems.",
                "Covered with rocks.",
            ],
            forced_prompt_type=ReviewService.PROMPT_TYPE_MEANING_DISCRIMINATION,
        )

        assert prompt["prompt_type"] == "meaning_discrimination"
        assert prompt["question"] == "rocky"
        assert len(prompt["options"]) == 3
        assert not any(option["label"].startswith("Option ") for option in prompt["options"])

    @pytest.mark.asyncio
    async def test_build_card_prompt_uses_typed_recall_for_deep_stage_two_hard_slots(
        self, review_service, mock_db, monkeypatch
    ):
        review_service._get_user_review_preferences = AsyncMock(
            return_value=MagicMock(
                review_depth_preset="deep",
                enable_audio_spelling=False,
                enable_confidence_check=True,
            )
        )
        monkeypatch.setattr(review_service, "_get_user_accent_preference", AsyncMock(return_value="us"))

        prompt = await review_service._build_card_prompt(
            review_mode=ReviewService.REVIEW_MODE_MCQ,
            source_text="resilience",
            definition="The capacity to recover quickly from difficulties.",
            sentence="Resilience helps teams adapt after major setbacks.",
            is_phrase_entry=False,
            distractor_seed="seed",
            meaning_id=uuid.uuid4(),
            index=0,
            alternative_definitions=[
                "The capacity to recover quickly from difficulties.",
                "A tendency to overreact.",
                "A refusal to listen.",
            ],
            user_id=uuid.uuid4(),
            source_entry_id=uuid.uuid4(),
            source_entry_type="word",
            previous_prompt_type=ReviewService.PROMPT_TYPE_SENTENCE_GAP,
            srs_bucket="7d",
            cadence_step=0,
        )

        assert prompt["prompt_type"] == "typed_recall"
        assert prompt["options"] is None
        assert prompt["expected_input"] is None
        assert prompt["input_mode"] == "typed"
        assert prompt["prompt_token"]
        assert prompt["source_meaning_id"] is not None
        assert "type the word or phrase" in prompt["stem"].lower()

    @pytest.mark.asyncio
    async def test_build_card_prompt_supports_speak_recall_placeholder_when_forced(
        self, review_service, mock_db, monkeypatch
    ):
        review_service._get_user_review_preferences = AsyncMock(
            return_value=MagicMock(
                review_depth_preset="balanced",
                enable_audio_spelling=True,
                enable_confidence_check=True,
            )
        )
        monkeypatch.setattr(
            review_service,
            "_select_prompt_type",
            MagicMock(return_value=ReviewService.PROMPT_TYPE_SPEAK_RECALL),
        )
        review_service._load_prompt_audio_assets = AsyncMock(
            return_value=[
                MagicMock(
                    locale="en_us",
                    content_scope="word",
                    relative_path="review/word/en_us/word.mp3",
                    storage_policy=MagicMock(primary_storage_base="/tmp/voice", primary_storage_kind="local"),
                    id=uuid.uuid4(),
                )
            ]
        )
        review_service._get_user_accent_preference = AsyncMock(return_value="us")
        prompt = await review_service._build_card_prompt(
            review_mode=ReviewService.REVIEW_MODE_MCQ,
            source_text="resilience",
            definition="The capacity to recover quickly from difficulties.",
            sentence=None,
            is_phrase_entry=False,
            distractor_seed="seed",
            meaning_id=uuid.uuid4(),
            index=2,
            alternative_definitions=[
                "The capacity to recover quickly from difficulties.",
                "A tendency to overreact.",
                "A refusal to listen.",
            ],
            user_id=uuid.uuid4(),
            source_entry_id=uuid.uuid4(),
            source_entry_type="word",
            forced_prompt_type=ReviewService.PROMPT_TYPE_SPEAK_RECALL,
        )

        assert prompt["prompt_type"] == "speak_recall"
        assert prompt["input_mode"] == "speech_placeholder"
        assert prompt["voice_placeholder_text"] is not None
        assert prompt["audio_state"] == "ready"
        assert prompt["audio"]["preferred_playback_url"].endswith("/content")
        assert prompt["expected_input"] is None
        assert prompt["prompt_token"]

    @pytest.mark.asyncio
    async def test_build_card_prompt_strips_answer_truth_from_mcq_options(
        self, review_service, mock_db
    ):
        review_service._get_user_review_preferences = AsyncMock(
            return_value=MagicMock(
                review_depth_preset="balanced",
                enable_audio_spelling=False,
                enable_confidence_check=True,
            )
        )
        review_service._fetch_same_day_definition_distractors = AsyncMock(return_value=[])
        review_service._fetch_adjacent_definition_distractors = AsyncMock(return_value=[])
        prompt = await review_service._build_card_prompt(
            review_mode=ReviewService.REVIEW_MODE_MCQ,
            source_text="barely",
            definition="Only just, by a very small margin.",
            sentence=None,
            is_phrase_entry=False,
            distractor_seed="seed",
            meaning_id=uuid.uuid4(),
            index=0,
            alternative_definitions=[
                "Only just, by a very small margin.",
                "With great courage.",
                "Almost never.",
            ],
            user_id=uuid.uuid4(),
            source_entry_id=uuid.uuid4(),
            source_entry_type="word",
            queue_item_id=uuid.uuid4(),
        )

        assert prompt["prompt_token"]
        assert prompt["options"]
        assert all("is_correct" not in option for option in prompt["options"])

    @pytest.mark.asyncio
    async def test_fetch_word_distractors_avoids_random_order(
        self, review_service, mock_db
    ):
        result = MagicMock()
        result.scalars.return_value.all.return_value = ["alpha", "beta", "gamma"]
        mock_db.execute.return_value = result

        await review_service._fetch_word_distractors("delta", limit=3)

        executed_query = mock_db.execute.await_args_list[0].args[0]
        assert "random()" not in str(executed_query).lower()

    @pytest.mark.asyncio
    async def test_fetch_definition_distractors_avoids_random_order(
        self, review_service, mock_db
    ):
        result = MagicMock()
        result.scalars.return_value.all.return_value = ["alpha", "beta", "gamma"]
        mock_db.execute.return_value = result

        await review_service._fetch_definition_distractors(uuid.uuid4(), limit=3)

        executed_query = mock_db.execute.call_args.args[0]
        assert "random()" not in str(executed_query).lower()

    @pytest.mark.asyncio
    async def test_build_card_prompt_prefers_same_day_definition_distractors_before_frequency_fallback(
        self, review_service, mock_db, monkeypatch
    ):
        user_id = uuid.uuid4()
        review_service._get_user_review_preferences = AsyncMock(
            return_value=MagicMock(
                review_depth_preset="balanced",
                enable_audio_spelling=False,
                enable_confidence_check=True,
            )
        )
        monkeypatch.setattr(review_service, "_get_user_accent_preference", AsyncMock(return_value="uk"))
        monkeypatch.setattr(
            review_service,
            "_select_prompt_type",
            MagicMock(return_value=ReviewService.PROMPT_TYPE_AUDIO_TO_DEFINITION),
        )
        review_service._fetch_same_day_definition_distractors = AsyncMock(
            return_value=[
                "A financial institution that stores money.",
                "A raised pile of snow.",
                "A large mass of cloud.",
            ]
        )
        review_service._fetch_adjacent_definition_distractors = AsyncMock(
            return_value=["A long narrow table."]
        )
        review_service._load_prompt_audio_assets = AsyncMock(return_value=[])
        audio_loader = AsyncMock(
            return_value={
                "preferred_playback_url": "/api/words/voice-assets/test-asset/content",
                "preferred_locale": "us",
                "locales": {
                    "us": {
                        "playback_url": "/api/words/voice-assets/test-asset/content",
                        "locale": "en_us",
                        "relative_path": "word_bank/word/en_us/female-word.mp3",
                    }
                },
            }
        )
        monkeypatch.setattr(review_service, "_build_prompt_audio_payload", audio_loader)

        prompt = await review_service._build_card_prompt(
            review_mode=ReviewService.REVIEW_MODE_MCQ,
            source_text="bank",
            definition="The land alongside a river.",
            sentence=None,
            is_phrase_entry=False,
            distractor_seed="review",
            meaning_id=uuid.uuid4(),
            index=0,
            alternative_definitions=None,
            user_id=user_id,
            source_entry_id=uuid.uuid4(),
            source_entry_type="word",
        )

        assert prompt["prompt_type"] == "audio_to_definition"
        labels = [option["label"] for option in prompt["options"]]
        assert "A financial institution that stores money." in labels
        assert "A long narrow table." not in labels
        assert prompt["audio"]["preferred_playback_url"] == "/api/words/voice-assets/test-asset/content"
        assert prompt["audio"]["preferred_locale"] == "us"
        assert prompt["audio_state"] == "ready"
        audio_loader.assert_awaited_once_with([], preferred_accent="uk")
        review_service._fetch_same_day_definition_distractors.assert_awaited_once()
        review_service._fetch_adjacent_definition_distractors.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_build_card_prompt_prefers_word_confusables_for_definition_to_entry(
        self, review_service, mock_db, monkeypatch
    ):
        source_entry_id = uuid.uuid4()
        review_service._get_user_review_preferences = AsyncMock(
            return_value=MagicMock(
                review_depth_preset="balanced",
                enable_audio_spelling=False,
                enable_confidence_check=True,
            )
        )
        monkeypatch.setattr(
            review_service,
            "_select_prompt_type",
            MagicMock(return_value=ReviewService.PROMPT_TYPE_DEFINITION_TO_ENTRY),
        )
        review_service._fetch_word_confusable_distractors = AsyncMock(
            return_value=["barley", "bare", "barren"]
        )
        review_service._fetch_same_day_entry_distractors = AsyncMock(return_value=["hardly"])
        review_service._fetch_adjacent_entry_distractors = AsyncMock(return_value=["boldly"])

        prompt = await review_service._build_card_prompt(
            review_mode=ReviewService.REVIEW_MODE_MCQ,
            source_text="barely",
            definition="Only just, by a very small margin.",
            sentence=None,
            is_phrase_entry=False,
            distractor_seed="seed",
            meaning_id=uuid.uuid4(),
            index=0,
            alternative_definitions=None,
            user_id=uuid.uuid4(),
            source_entry_id=source_entry_id,
            source_entry_type="word",
        )

        labels = [option["label"] for option in prompt["options"]]
        assert "barley" in labels
        assert "hardly" not in labels
        assert "boldly" not in labels
        review_service._fetch_word_confusable_distractors.assert_awaited_once_with(
            target_entry_id=source_entry_id,
            limit=3,
        )
        review_service._fetch_same_day_entry_distractors.assert_not_awaited()
        review_service._fetch_adjacent_entry_distractors.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_build_word_detail_payload_uses_user_accent_and_exposes_pronunciations(
        self, review_service, mock_db, monkeypatch
    ):
        user_id = uuid.uuid4()
        word = Word(
            id=uuid.uuid4(),
            word="bank",
            language="en",
            phonetic="/bæŋk/",
            phonetics={
                "us": {"ipa": "/bæŋk/", "confidence": 0.99},
                "uk": {"ipa": "/baŋk/", "confidence": 0.98},
            },
        )
        meaning = Meaning(id=uuid.uuid4(), word_id=word.id, definition="A financial institution", part_of_speech="noun")

        payload = await review_service._build_word_detail_payload(
            user_id=user_id,
            word=word,
            meanings=[meaning],
            example_by_meaning_id={meaning.id: "I went to the bank."},
            remembered_count=3,
            accent="uk",
        )

        assert payload["pronunciation"] == "/baŋk/"
        assert payload["pronunciations"] == {"us": "/bæŋk/", "uk": "/baŋk/"}

    @pytest.mark.asyncio
    async def test_build_card_prompt_uses_adjacent_frequency_distractors_when_same_day_pool_is_small(
        self, review_service, mock_db, monkeypatch
    ):
        user_id = uuid.uuid4()
        review_service._get_user_review_preferences = AsyncMock(
            return_value=MagicMock(
                review_depth_preset="balanced",
                enable_audio_spelling=False,
                enable_confidence_check=True,
            )
        )
        monkeypatch.setattr(review_service, "_get_user_accent_preference", AsyncMock(return_value="us"))
        monkeypatch.setattr(
            review_service,
            "_select_prompt_type",
            MagicMock(return_value=ReviewService.PROMPT_TYPE_AUDIO_TO_DEFINITION),
        )
        review_service._fetch_same_day_definition_distractors = AsyncMock(
            return_value=["A financial institution that stores money."]
        )
        review_service._fetch_adjacent_definition_distractors = AsyncMock(
            return_value=[
                "A raised pile of snow.",
                "A large mass of cloud.",
            ]
        )
        review_service._load_prompt_audio_assets = AsyncMock(return_value=[])
        audio_loader = AsyncMock(return_value=None)
        monkeypatch.setattr(review_service, "_build_prompt_audio_payload", audio_loader)

        prompt = await review_service._build_card_prompt(
            review_mode=ReviewService.REVIEW_MODE_MCQ,
            source_text="bank",
            definition="The land alongside a river.",
            sentence=None,
            is_phrase_entry=False,
            distractor_seed="review",
            meaning_id=uuid.uuid4(),
            index=0,
            alternative_definitions=None,
            user_id=user_id,
            source_entry_id=uuid.uuid4(),
            source_entry_type="word",
        )

        labels = [option["label"] for option in prompt["options"]]
        assert "A financial institution that stores money." in labels
        assert "A raised pile of snow." in labels
        assert "A large mass of cloud." in labels
        review_service._fetch_adjacent_definition_distractors.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_build_card_prompt_supports_collocation_check_when_forced(
        self, review_service, mock_db
    ):
        distractor_result = MagicMock()
        distractor_result.scalars.return_value.all.return_value = [
            "abandon ship",
            "cross the line",
            "hold your fire",
        ]
        mock_db.execute.return_value = distractor_result

        prompt = await review_service._build_card_prompt(
            review_mode=ReviewService.REVIEW_MODE_MCQ,
            source_text="jump the gun",
            definition="To do something too soon.",
            sentence="They jump the gun whenever a draft appears.",
            is_phrase_entry=True,
            distractor_seed="seed",
            meaning_id=uuid.uuid4(),
            index=1,
            alternative_definitions=[
                "To do something too soon.",
                "To wait too long.",
                "To avoid a task.",
            ],
            forced_prompt_type=ReviewService.PROMPT_TYPE_COLLOCATION_CHECK,
        )

        assert prompt["prompt_type"] == "collocation_check"
        assert prompt["sentence_masked"] is not None
        assert "common expression" in prompt["stem"].lower()
        assert prompt["question"] == "They ___ whenever a draft appears."
        assert "jump the gun" not in prompt["question"].lower()
        assert len(prompt["options"]) == 4

    @pytest.mark.asyncio
    async def test_build_card_prompt_supports_situation_matching_when_forced(
        self, review_service, mock_db
    ):
        distractor_result = MagicMock()
        distractor_result.scalars.return_value.all.return_value = [
            "shut down",
            "hold back",
            "fall apart",
        ]
        mock_db.execute.return_value = distractor_result

        prompt = await review_service._build_card_prompt(
            review_mode=ReviewService.REVIEW_MODE_MCQ,
            source_text="resilience",
            definition="The capacity to recover quickly from difficulties.",
            sentence="Resilience helps teams adapt after major setbacks.",
            is_phrase_entry=False,
            distractor_seed="seed",
            meaning_id=uuid.uuid4(),
            index=2,
            alternative_definitions=[
                "The capacity to recover quickly from difficulties.",
                "A tendency to overreact.",
                "A refusal to listen.",
            ],
            forced_prompt_type=ReviewService.PROMPT_TYPE_SITUATION_MATCHING,
        )

        assert prompt["prompt_type"] == "situation_matching"
        assert "situation" in prompt["stem"].lower()
        assert prompt["question"] == "___ helps teams adapt after major setbacks."
        assert "resilience" not in prompt["question"].lower()
        assert len(prompt["options"]) == 4

    @pytest.mark.asyncio
    async def test_build_card_prompt_supports_confidence_check(
        self, review_service, mock_db, monkeypatch
    ):
        user_id = uuid.uuid4()
        source_entry_id = uuid.uuid4()
        meaning_id = uuid.uuid4()
        prefs = MagicMock()
        prefs.review_depth_preset = "balanced"
        prefs.enable_audio_spelling = False
        prefs.enable_word_spelling = True
        prefs.enable_confidence_check = True
        prefs.show_pictures_in_questions = False

        monkeypatch.setattr(
            review_service,
            "_get_user_review_preferences",
            AsyncMock(return_value=prefs),
        )
        monkeypatch.setattr(
            review_service,
            "_get_user_accent_preference",
            AsyncMock(return_value="us"),
        )
        review_service._fetch_same_day_definition_distractors = AsyncMock(return_value=[])
        review_service._fetch_adjacent_definition_distractors = AsyncMock(return_value=[])
        review_service._load_prompt_audio_assets = AsyncMock(
            return_value=[
                MagicMock(
                    locale="en_us",
                    relative_path="review/word/en_us/word.mp3",
                    storage_policy=MagicMock(primary_storage_base="/tmp/voice", primary_storage_kind="local"),
                    id=uuid.uuid4(),
                )
            ]
        )

        prompt = await review_service._build_card_prompt(
            review_mode=ReviewService.REVIEW_MODE_CONFIDENCE,
            source_text="persistence",
            definition="The ability to keep going despite difficulties.",
            sentence="Persistence kept the project moving through repeated delays.",
            is_phrase_entry=False,
            distractor_seed="seed",
            meaning_id=meaning_id,
            index=0,
            alternative_definitions=None,
            user_id=user_id,
            source_entry_id=source_entry_id,
            source_entry_type="word",
        )

        assert prompt["prompt_type"] == "confidence_check"
        assert prompt["question"] == "Persistence kept the project moving through repeated delays."
        assert [option["label"] for option in prompt["options"]] == ["I remember it", "Not sure"]
        assert prompt["audio_state"] == "ready"
        assert prompt["audio"]["preferred_playback_url"].endswith("/content")

    @pytest.mark.asyncio
    async def test_prompt_audio_selection_prefers_word_scope_assets(
        self, review_service, mock_db
    ):
        word_asset = MagicMock(
            content_scope="word",
            locale="en_us",
            profile_key="female-word",
            word_id=uuid.uuid4(),
            meaning_id=None,
            meaning_example_id=None,
        )
        definition_asset = MagicMock(
            content_scope="definition",
            locale="en_us",
            profile_key="female-definition",
            word_id=word_asset.word_id,
            meaning_id=uuid.uuid4(),
            meaning_example_id=None,
        )
        ranked_assets = review_service._select_prompt_audio_assets(
            assets=[definition_asset, word_asset],
            target_entry_type="word",
            target_id=None,
            example_id=None,
        )

        assert ranked_assets[0] is word_asset

    @pytest.mark.asyncio
    async def test_build_card_prompt_audio_to_definition_hides_answer_word(
        self, review_service, mock_db, monkeypatch
    ):
        user_id = uuid.uuid4()
        source_entry_id = uuid.uuid4()
        meaning_id = uuid.uuid4()
        prefs = MagicMock()
        prefs.review_depth_preset = "deep"
        prefs.enable_audio_spelling = True
        prefs.enable_word_spelling = True
        prefs.enable_confidence_check = False
        prefs.show_pictures_in_questions = False

        monkeypatch.setattr(
            review_service,
            "_get_user_review_preferences",
            AsyncMock(return_value=prefs),
        )
        monkeypatch.setattr(
            review_service,
            "_select_prompt_type",
            MagicMock(return_value=ReviewService.PROMPT_TYPE_AUDIO_TO_DEFINITION),
        )
        monkeypatch.setattr(
            review_service,
            "_get_user_accent_preference",
            AsyncMock(return_value="us"),
        )
        review_service._fetch_same_day_definition_distractors = AsyncMock(return_value=[])
        review_service._fetch_adjacent_definition_distractors = AsyncMock(return_value=[])
        review_service._load_prompt_audio_assets = AsyncMock(
            return_value=[
                MagicMock(
                    locale="en_us",
                    relative_path="review/word/en_us/word.mp3",
                    storage_policy=MagicMock(primary_storage_base="/tmp/voice", primary_storage_kind="local"),
                    id=uuid.uuid4(),
                )
            ]
        )

        prompt = await review_service._build_card_prompt(
            review_mode=ReviewService.REVIEW_MODE_MCQ,
            source_text="tranquil",
            definition="Calm and peaceful.",
            sentence=None,
            is_phrase_entry=False,
            distractor_seed="seed",
            meaning_id=meaning_id,
            index=0,
            alternative_definitions=None,
            user_id=user_id,
            source_entry_id=source_entry_id,
            source_entry_type="word",
        )

        assert prompt["prompt_type"] == "audio_to_definition"
        assert prompt["question"] == "Which definition matches the audio?"
        assert prompt["question"] != "tranquil"

    def test_build_available_prompt_types_uses_v1_simple_pool_only(self, review_service):
        candidates = review_service._build_available_prompt_types(
            review_mode=ReviewService.REVIEW_MODE_MCQ,
            sentence="Persistence kept the project moving through repeated delays.",
            alternative_definitions=None,
            review_depth_preset="balanced",
            allow_typed_recall=True,
            allow_audio_spelling=True,
            allow_confidence=True,
            active_target_count=1,
            srs_bucket="7d",
            cadence_step=1,
        )

        assert candidates == [
            ReviewService.PROMPT_TYPE_ENTRY_TO_DEFINITION,
            ReviewService.PROMPT_TYPE_AUDIO_TO_DEFINITION,
            ReviewService.PROMPT_TYPE_DEFINITION_TO_ENTRY,
            ReviewService.PROMPT_TYPE_CONFIDENCE_CHECK,
        ]

    def test_build_available_prompt_types_uses_sentence_gap_only_for_standard_hard_slots(
        self, review_service
    ):
        candidates = review_service._build_available_prompt_types(
            review_mode=ReviewService.REVIEW_MODE_MCQ,
            sentence="Persistence kept the project moving through repeated delays.",
            alternative_definitions=None,
            review_depth_preset="balanced",
            allow_typed_recall=True,
            allow_audio_spelling=True,
            allow_confidence=True,
            active_target_count=1,
            srs_bucket="14d",
            cadence_step=2,
        )

        assert candidates == [ReviewService.PROMPT_TYPE_SENTENCE_GAP]

    def test_build_available_prompt_types_uses_sentence_gap_and_typed_recall_for_deep_hard_slots(
        self, review_service
    ):
        candidates = review_service._build_available_prompt_types(
            review_mode=ReviewService.REVIEW_MODE_MCQ,
            sentence="Persistence kept the project moving through repeated delays.",
            alternative_definitions=None,
            review_depth_preset="deep",
            allow_typed_recall=True,
            allow_audio_spelling=True,
            allow_confidence=True,
            active_target_count=1,
            srs_bucket="7d",
            cadence_step=0,
        )

        assert candidates == [
            ReviewService.PROMPT_TYPE_TYPED_RECALL,
            ReviewService.PROMPT_TYPE_SENTENCE_GAP,
        ]

    def test_build_available_prompt_types_uses_audio_spelling_in_deep_stage_three_hard_slots(
        self, review_service
    ):
        candidates = review_service._build_available_prompt_types(
            review_mode=ReviewService.REVIEW_MODE_MCQ,
            sentence="Persistence kept the project moving through repeated delays.",
            alternative_definitions=None,
            review_depth_preset="deep",
            allow_typed_recall=True,
            allow_audio_spelling=True,
            allow_confidence=True,
            active_target_count=1,
            srs_bucket="180d",
            cadence_step=0,
        )

        assert candidates == [
            ReviewService.PROMPT_TYPE_SPEAK_RECALL,
            ReviewService.PROMPT_TYPE_TYPED_RECALL,
            ReviewService.PROMPT_TYPE_SENTENCE_GAP,
        ]

    def test_build_available_prompt_types_allows_speak_recall_across_deep_stage_three(
        self, review_service
    ):
        candidates = review_service._build_available_prompt_types(
            review_mode=ReviewService.REVIEW_MODE_MCQ,
            sentence="Persistence kept the project moving through repeated delays.",
            alternative_definitions=None,
            review_depth_preset="deep",
            allow_typed_recall=True,
            allow_audio_spelling=True,
            allow_confidence=True,
            active_target_count=1,
            srs_bucket="30d",
            cadence_step=0,
        )

        assert candidates == [
            ReviewService.PROMPT_TYPE_TYPED_RECALL,
            ReviewService.PROMPT_TYPE_SENTENCE_GAP,
            ReviewService.PROMPT_TYPE_SPEAK_RECALL,
        ]

    @pytest.mark.asyncio
    async def test_build_card_prompt_standard_simple_pool_skips_typed_audio_and_deactivated_families(
        self, review_service, mock_db, monkeypatch
    ):
        user_id = uuid.uuid4()
        prefs = MagicMock()
        prefs.review_depth_preset = "balanced"
        prefs.enable_audio_spelling = False
        prefs.enable_word_spelling = True
        prefs.enable_confidence_check = True
        prefs.show_pictures_in_questions = False

        monkeypatch.setattr(
            review_service,
            "_get_user_review_preferences",
            AsyncMock(return_value=prefs),
        )
        review_service._fetch_same_day_entry_distractors = AsyncMock(return_value=[])
        review_service._fetch_adjacent_entry_distractors = AsyncMock(return_value=[])
        review_service._fetch_same_day_definition_distractors = AsyncMock(return_value=[])
        review_service._fetch_adjacent_definition_distractors = AsyncMock(return_value=[])
        review_service._load_prompt_audio_assets = AsyncMock(return_value=[])
        select_prompt_type = MagicMock(
            side_effect=lambda prompt_candidates, index=0, previous_prompt_type=None: prompt_candidates[0]
        )
        monkeypatch.setattr(review_service, "_select_prompt_type", select_prompt_type)

        await review_service._build_card_prompt(
            review_mode=ReviewService.REVIEW_MODE_MCQ,
            source_text="bank",
            definition="The land alongside a river.",
            sentence="We sat on the river bank.",
            is_phrase_entry=False,
            distractor_seed="seed",
            meaning_id=uuid.uuid4(),
            index=0,
            alternative_definitions=[
                "A financial institution that stores money.",
                "A raised pile of snow.",
                "A large mass of cloud.",
            ],
            user_id=user_id,
            source_entry_id=uuid.uuid4(),
            source_entry_type="word",
            srs_bucket="5d",
            cadence_step=1,
        )

        candidates = select_prompt_type.call_args.args[0]
        assert ReviewService.PROMPT_TYPE_TYPED_RECALL not in candidates
        assert ReviewService.PROMPT_TYPE_SPEAK_RECALL not in candidates
        assert ReviewService.PROMPT_TYPE_MEANING_DISCRIMINATION not in candidates
        assert ReviewService.PROMPT_TYPE_COLLOCATION_CHECK not in candidates
        assert ReviewService.PROMPT_TYPE_SITUATION_MATCHING not in candidates
        assert ReviewService.PROMPT_TYPE_DEFINITION_TO_ENTRY in candidates
        assert ReviewService.PROMPT_TYPE_ENTRY_TO_DEFINITION in candidates
        assert ReviewService.PROMPT_TYPE_CONFIDENCE_CHECK in candidates

    @pytest.mark.asyncio
    async def test_build_card_prompt_deep_hard_pool_includes_typed_recall_but_not_speak_recall(
        self, review_service, mock_db, monkeypatch
    ):
        user_id = uuid.uuid4()
        prefs = MagicMock()
        prefs.review_depth_preset = "deep"
        prefs.enable_audio_spelling = True
        prefs.enable_word_spelling = True
        prefs.enable_confidence_check = True
        prefs.show_pictures_in_questions = False

        monkeypatch.setattr(
            review_service,
            "_get_user_review_preferences",
            AsyncMock(return_value=prefs),
        )
        review_service._fetch_same_day_entry_distractors = AsyncMock(return_value=[])
        review_service._fetch_adjacent_entry_distractors = AsyncMock(return_value=[])
        review_service._fetch_same_day_definition_distractors = AsyncMock(return_value=[])
        review_service._fetch_adjacent_definition_distractors = AsyncMock(return_value=[])
        review_service._load_prompt_audio_assets = AsyncMock(return_value=[])
        select_prompt_type = MagicMock(
            side_effect=lambda prompt_candidates, index=0, previous_prompt_type=None: prompt_candidates[0]
        )
        monkeypatch.setattr(review_service, "_select_prompt_type", select_prompt_type)

        await review_service._build_card_prompt(
            review_mode=ReviewService.REVIEW_MODE_MCQ,
            source_text="resilience",
            definition="The capacity to recover quickly from difficulties.",
            sentence="Resilience helps teams adapt after major setbacks.",
            is_phrase_entry=False,
            distractor_seed="seed",
            meaning_id=uuid.uuid4(),
            index=0,
            alternative_definitions=[
                "The capacity to recover quickly from difficulties.",
                "A tendency to overreact.",
                "A refusal to listen.",
            ],
            user_id=user_id,
            source_entry_id=uuid.uuid4(),
            source_entry_type="word",
            srs_bucket="7d",
            cadence_step=0,
        )

        candidates = select_prompt_type.call_args.args[0]
        assert ReviewService.PROMPT_TYPE_TYPED_RECALL in candidates
        assert ReviewService.PROMPT_TYPE_SPEAK_RECALL not in candidates
        assert candidates == [
            ReviewService.PROMPT_TYPE_TYPED_RECALL,
            ReviewService.PROMPT_TYPE_SENTENCE_GAP,
        ]

    @pytest.mark.asyncio
    async def test_build_card_prompt_confidence_remains_available_even_if_legacy_pref_disabled(
        self, review_service, mock_db, monkeypatch
    ):
        user_id = uuid.uuid4()
        prefs = MagicMock()
        prefs.review_depth_preset = "balanced"
        prefs.enable_audio_spelling = False
        prefs.enable_word_spelling = True
        prefs.enable_confidence_check = False
        prefs.show_pictures_in_questions = False

        monkeypatch.setattr(
            review_service,
            "_get_user_review_preferences",
            AsyncMock(return_value=prefs),
        )
        review_service._fetch_word_confusable_distractors = AsyncMock(
            return_value=["barley", "barren", "boldly"]
        )
        review_service._fetch_same_day_entry_distractors = AsyncMock(return_value=[])
        review_service._fetch_adjacent_entry_distractors = AsyncMock(return_value=[])
        review_service._fetch_same_day_definition_distractors = AsyncMock(return_value=[])
        review_service._fetch_adjacent_definition_distractors = AsyncMock(return_value=[])
        review_service._load_prompt_audio_assets = AsyncMock(return_value=[])
        select_prompt_type = MagicMock(
            side_effect=lambda prompt_candidates, index=0, previous_prompt_type=None: prompt_candidates[-1]
        )
        monkeypatch.setattr(review_service, "_select_prompt_type", select_prompt_type)

        await review_service._build_card_prompt(
            review_mode=ReviewService.REVIEW_MODE_MCQ,
            source_text="bank",
            definition="The land alongside a river.",
            sentence="We sat on the river bank.",
            is_phrase_entry=False,
            distractor_seed="seed",
            meaning_id=uuid.uuid4(),
            index=0,
            alternative_definitions=None,
            user_id=user_id,
            source_entry_id=uuid.uuid4(),
            source_entry_type="word",
            srs_bucket="5d",
            cadence_step=1,
        )

        candidates = select_prompt_type.call_args.args[0]
        assert ReviewService.PROMPT_TYPE_CONFIDENCE_CHECK in candidates

    @pytest.mark.asyncio
    async def test_build_card_prompt_deep_stage_three_ignores_legacy_audio_pref_gate(
        self, review_service, mock_db, monkeypatch
    ):
        user_id = uuid.uuid4()
        prefs = MagicMock()
        prefs.review_depth_preset = "deep"
        prefs.enable_audio_spelling = False
        prefs.enable_word_spelling = True
        prefs.enable_confidence_check = True
        prefs.show_pictures_in_questions = False

        monkeypatch.setattr(
            review_service,
            "_get_user_review_preferences",
            AsyncMock(return_value=prefs),
        )
        review_service._fetch_same_day_entry_distractors = AsyncMock(return_value=[])
        review_service._fetch_adjacent_entry_distractors = AsyncMock(return_value=[])
        review_service._fetch_same_day_definition_distractors = AsyncMock(return_value=[])
        review_service._fetch_adjacent_definition_distractors = AsyncMock(return_value=[])
        review_service._load_prompt_audio_assets = AsyncMock(
            return_value=[
                MagicMock(
                    locale="en_us",
                    content_scope="word",
                    relative_path="review/word/en_us/word.mp3",
                    storage_policy=MagicMock(primary_storage_base="/tmp/voice", primary_storage_kind="local"),
                    id=uuid.uuid4(),
                )
            ]
        )
        select_prompt_type = MagicMock(
            side_effect=lambda prompt_candidates, index=0, previous_prompt_type=None: prompt_candidates[-1]
        )
        monkeypatch.setattr(review_service, "_select_prompt_type", select_prompt_type)
        monkeypatch.setattr(review_service, "_get_user_accent_preference", AsyncMock(return_value="us"))

        await review_service._build_card_prompt(
            review_mode=ReviewService.REVIEW_MODE_MCQ,
            source_text="resilience",
            definition="The capacity to recover quickly from difficulties.",
            sentence="Resilience helps teams adapt after major setbacks.",
            is_phrase_entry=False,
            distractor_seed="seed",
            meaning_id=uuid.uuid4(),
            index=0,
            alternative_definitions=None,
            user_id=user_id,
            source_entry_id=uuid.uuid4(),
            source_entry_type="word",
            srs_bucket="30d",
            cadence_step=0,
        )

        candidates = select_prompt_type.call_args.args[0]
        assert ReviewService.PROMPT_TYPE_SPEAK_RECALL in candidates

    @pytest.mark.asyncio
    async def test_build_card_prompt_deep_stage_three_hard_pool_includes_speak_recall(
        self, review_service, mock_db, monkeypatch
    ):
        user_id = uuid.uuid4()
        prefs = MagicMock()
        prefs.review_depth_preset = "deep"
        prefs.enable_audio_spelling = True
        prefs.enable_word_spelling = True
        prefs.enable_confidence_check = True
        prefs.show_pictures_in_questions = False

        monkeypatch.setattr(
            review_service,
            "_get_user_review_preferences",
            AsyncMock(return_value=prefs),
        )
        review_service._fetch_same_day_entry_distractors = AsyncMock(return_value=[])
        review_service._fetch_adjacent_entry_distractors = AsyncMock(return_value=[])
        review_service._fetch_same_day_definition_distractors = AsyncMock(return_value=[])
        review_service._fetch_adjacent_definition_distractors = AsyncMock(return_value=[])
        review_service._load_prompt_audio_assets = AsyncMock(
            return_value=[
                MagicMock(
                    locale="en_us",
                    content_scope="word",
                    relative_path="review/word/en_us/word.mp3",
                    storage_policy=MagicMock(primary_storage_base="/tmp/voice", primary_storage_kind="local"),
                    id=uuid.uuid4(),
                )
            ]
        )
        select_prompt_type = MagicMock(
            side_effect=lambda prompt_candidates, index=0, previous_prompt_type=None: prompt_candidates[0]
        )
        monkeypatch.setattr(review_service, "_select_prompt_type", select_prompt_type)
        monkeypatch.setattr(review_service, "_get_user_accent_preference", AsyncMock(return_value="us"))

        prompt = await review_service._build_card_prompt(
            review_mode=ReviewService.REVIEW_MODE_MCQ,
            source_text="resilience",
            definition="The capacity to recover quickly from difficulties.",
            sentence="Resilience helps teams adapt after major setbacks.",
            is_phrase_entry=False,
            distractor_seed="seed",
            meaning_id=uuid.uuid4(),
            index=0,
            alternative_definitions=None,
            user_id=user_id,
            source_entry_id=uuid.uuid4(),
            source_entry_type="word",
            srs_bucket="180d",
            cadence_step=0,
        )

        candidates = select_prompt_type.call_args.args[0]
        assert candidates == [
            ReviewService.PROMPT_TYPE_SPEAK_RECALL,
            ReviewService.PROMPT_TYPE_TYPED_RECALL,
            ReviewService.PROMPT_TYPE_SENTENCE_GAP,
        ]
        assert prompt["prompt_type"] == ReviewService.PROMPT_TYPE_SPEAK_RECALL

    @pytest.mark.asyncio
    async def test_build_card_prompt_falls_back_when_audio_prompt_has_no_audio_and_avoids_repetition(
        self, review_service, mock_db, monkeypatch
    ):
        review_service._get_user_review_preferences = AsyncMock(
            return_value=MagicMock(
                review_depth_preset="balanced",
                enable_audio_spelling=False,
                enable_confidence_check=True,
            )
        )
        review_service._fetch_word_confusable_distractors = AsyncMock(
            return_value=["barley", "barren", "boldly"]
        )
        review_service._fetch_same_day_entry_distractors = AsyncMock(return_value=[])
        review_service._fetch_adjacent_entry_distractors = AsyncMock(return_value=[])
        review_service._load_prompt_audio_assets = AsyncMock(return_value=[])
        monkeypatch.setattr(review_service, "_get_user_accent_preference", AsyncMock(return_value="us"))

        prompt = await review_service._build_card_prompt(
            review_mode=ReviewService.REVIEW_MODE_MCQ,
            source_text="barely",
            definition="Only just, by a very small margin.",
            sentence="We barely made the train.",
            is_phrase_entry=False,
            distractor_seed="seed",
            meaning_id=uuid.uuid4(),
            index=0,
            alternative_definitions=None,
            user_id=uuid.uuid4(),
            source_entry_id=uuid.uuid4(),
            source_entry_type="word",
            previous_prompt_type=ReviewService.PROMPT_TYPE_ENTRY_TO_DEFINITION,
            srs_bucket="7d",
            cadence_step=1,
        )

        assert prompt["prompt_type"] == ReviewService.PROMPT_TYPE_DEFINITION_TO_ENTRY

    @pytest.mark.asyncio
    async def test_build_card_prompt_falls_back_when_speak_recall_has_no_audio(
        self, review_service, mock_db, monkeypatch
    ):
        review_service._get_user_review_preferences = AsyncMock(
            return_value=MagicMock(
                review_depth_preset="deep",
                enable_audio_spelling=True,
                enable_confidence_check=True,
            )
        )
        review_service._fetch_same_day_entry_distractors = AsyncMock(return_value=[])
        review_service._fetch_adjacent_entry_distractors = AsyncMock(return_value=[])
        review_service._fetch_same_day_definition_distractors = AsyncMock(return_value=[])
        review_service._fetch_adjacent_definition_distractors = AsyncMock(return_value=[])
        review_service._load_prompt_audio_assets = AsyncMock(return_value=[])

        prompt = await review_service._build_card_prompt(
            review_mode=ReviewService.REVIEW_MODE_MCQ,
            source_text="candidate",
            definition="A person being considered for a role or position.",
            sentence="The candidate presented a strong plan during the interview.",
            is_phrase_entry=False,
            distractor_seed="seed",
            meaning_id=uuid.uuid4(),
            index=0,
            alternative_definitions=None,
            user_id=uuid.uuid4(),
            source_entry_id=uuid.uuid4(),
            source_entry_type="word",
            previous_prompt_type=ReviewService.PROMPT_TYPE_TYPED_RECALL,
            srs_bucket="180d",
            cadence_step=0,
        )

        assert prompt["prompt_type"] == ReviewService.PROMPT_TYPE_SENTENCE_GAP

    @pytest.mark.asyncio
    async def test_scheduler_accepts_collocation_and_situation_prompt_types(self):
        collocation = calculate_next_review(
            outcome="correct_tested",
            prompt_type="collocation_check",
            stability=3,
            difficulty=0.5,
        )
        situation = calculate_next_review(
            outcome="correct_tested",
            prompt_type="situation_matching",
            stability=3,
            difficulty=0.5,
        )

        assert collocation.interval_days > 0
        assert situation.interval_days > 0
        assert situation.stability >= collocation.stability

    @pytest.mark.asyncio
    async def test_scheduler_accepts_typed_recall_prompt_type(self):
        typed = calculate_next_review(
            outcome="correct_tested",
            prompt_type="typed_recall",
            stability=3,
            difficulty=0.5,
        )

        assert typed.interval_days > 0
        assert typed.stability > 3

    @pytest.mark.asyncio
    async def test_scheduler_accepts_confidence_check_prompt_type(self):
        confidence = calculate_next_review(
            outcome="correct_tested",
            prompt_type="confidence_check",
            stability=3,
            difficulty=0.5,
        )

        assert confidence.interval_days > 0
        assert confidence.stability > 0

    @pytest.mark.asyncio
    async def test_scheduler_distinguishes_grade_buckets(self):
        hard = calculate_next_review(
            outcome="correct_tested",
            prompt_type="typed_recall",
            stability=3,
            difficulty=0.5,
            grade="hard_pass",
        )
        good = calculate_next_review(
            outcome="correct_tested",
            prompt_type="typed_recall",
            stability=3,
            difficulty=0.5,
            grade="good_pass",
        )
        easy = calculate_next_review(
            outcome="correct_tested",
            prompt_type="typed_recall",
            stability=3,
            difficulty=0.5,
            grade="easy_pass",
        )

        assert hard.interval_days < good.interval_days < easy.interval_days

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

        aggregate_result = MagicMock()
        aggregate_result.one.return_value = (10, 7)
        mock_db.execute.side_effect = [aggregate_result]
        visible_states = [
            EntryReviewState(
                id=uuid.uuid4(),
                user_id=user_id,
                entry_type="word",
                entry_id=uuid.uuid4(),
                target_type="meaning",
                target_id=uuid.uuid4(),
            ),
            EntryReviewState(
                id=uuid.uuid4(),
                user_id=user_id,
                entry_type="word",
                entry_id=uuid.uuid4(),
                target_type="meaning",
                target_id=uuid.uuid4(),
            ),
            EntryReviewState(
                id=uuid.uuid4(),
                user_id=user_id,
                entry_type="word",
                entry_id=uuid.uuid4(),
                target_type="meaning",
                target_id=uuid.uuid4(),
            ),
            EntryReviewState(
                id=uuid.uuid4(),
                user_id=user_id,
                entry_type="word",
                entry_id=uuid.uuid4(),
                target_type="meaning",
                target_id=uuid.uuid4(),
            ),
            EntryReviewState(
                id=uuid.uuid4(),
                user_id=user_id,
                entry_type="word",
                entry_id=uuid.uuid4(),
                target_type="meaning",
                target_id=uuid.uuid4(),
            ),
        ]
        _set_canonical_schedule(visible_states[0], datetime.now(timezone.utc) - timedelta(minutes=5))
        visible_states[1].recheck_due_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        _set_canonical_schedule(visible_states[1], datetime.now(timezone.utc) + timedelta(days=1))
        _set_canonical_schedule(visible_states[2], datetime.now(timezone.utc) + timedelta(days=2))
        _set_canonical_schedule(visible_states[3], datetime.now(timezone.utc) + timedelta(days=3))
        _set_canonical_schedule(visible_states[4], datetime.now(timezone.utc) + timedelta(days=4))
        review_service._list_active_queue_states = AsyncMock(return_value=visible_states)

        stats = await review_service.get_queue_stats(user_id=user_id)

        assert stats["total_items"] == 5
        assert stats["due_items"] == 2
        assert stats["review_count"] == 10
        assert stats["correct_count"] == 7
        assert stats["accuracy"] == 0.7
        review_service._list_active_queue_states.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_queue_stats_uses_short_lived_cache(self, review_service, mock_db):
        user_id = uuid.uuid4()

        aggregate_result = MagicMock()
        aggregate_result.one.return_value = (10, 7)
        mock_db.execute.side_effect = [aggregate_result]
        visible_state = EntryReviewState(
            id=uuid.uuid4(),
            user_id=user_id,
            entry_type="word",
            entry_id=uuid.uuid4(),
            target_type="meaning",
            target_id=uuid.uuid4(),
        )
        review_service._list_active_queue_states = AsyncMock(return_value=[visible_state])

        first = await review_service.get_queue_stats(user_id=user_id)
        second = await review_service.get_queue_stats(user_id=user_id)

        assert first == second
        assert mock_db.execute.await_count == 1
        review_service._list_active_queue_states.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_queue_stats_counts_visible_items_after_sibling_burying(
        self, review_service, mock_db
    ):
        user_id = uuid.uuid4()
        now = datetime.now(timezone.utc)
        aggregate_result = MagicMock()
        aggregate_result.one.return_value = (4, 2)
        mock_db.execute.side_effect = [aggregate_result]

        visible_state_one = EntryReviewState(
            id=uuid.uuid4(),
            user_id=user_id,
            entry_type="word",
            entry_id=uuid.uuid4(),
            target_type="meaning",
            target_id=uuid.uuid4(),
        )
        _set_canonical_schedule(visible_state_one, None)
        visible_state_two = EntryReviewState(
            id=uuid.uuid4(),
            user_id=user_id,
            entry_type="word",
            entry_id=uuid.uuid4(),
            target_type="meaning",
            target_id=uuid.uuid4(),
        )
        _set_canonical_schedule(visible_state_two, now + timedelta(days=1))
        review_service._list_active_queue_states = AsyncMock(
            return_value=[visible_state_one, visible_state_two]
        )

        stats = await review_service.get_queue_stats(user_id=user_id)

        assert stats["total_items"] == 1
        assert stats["due_items"] == 0
        assert stats["review_count"] == 4
        assert stats["correct_count"] == 2
        assert stats["accuracy"] == 0.5


class TestUpdateQueueItemSchedule:
    @pytest.mark.asyncio
    async def test_update_queue_item_schedule_uses_bucket_override_for_official_reschedule(
        self, review_service, mock_db
    ):
        user_id = uuid.uuid4()
        state_id = uuid.uuid4()
        entry_state = EntryReviewState(
            id=state_id,
            user_id=user_id,
            entry_type="word",
            entry_id=uuid.uuid4(),
            target_type="meaning",
            target_id=uuid.uuid4(),
            stability=3,
            difficulty=0.4,
        )
        entry_state.interval_days = 3
        entry_state.srs_bucket = "3d"
        state_lookup = MagicMock()
        state_lookup.scalar_one_or_none.return_value = entry_state
        learner_status_lookup = MagicMock()
        learner_status_lookup.scalar_one_or_none.return_value = LearnerEntryStatus(
            user_id=user_id,
            entry_type="word",
            entry_id=entry_state.entry_id,
            status="learning",
        )
        mock_db.execute.side_effect = [state_lookup, learner_status_lookup]

        updated = await review_service.update_queue_item_schedule(
            user_id=user_id,
            item_id=state_id,
            schedule_override="7d",
        )

        assert updated["current_schedule_value"] == "7d"
        assert entry_state.srs_bucket == "7d"
        assert entry_state.interval_days == 7
        assert entry_state.min_due_at_utc is not None
        mock_db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_submit_queue_review_invalidates_queue_stats_cache(
        self, review_service, mock_db, monkeypatch
    ):
        user_id = uuid.uuid4()
        review_service._store_cached_queue_stats(
            user_id,
            {
                "total_items": 5,
                "due_items": 2,
                "review_count": 10,
                "correct_count": 7,
                "accuracy": 0.7,
            },
        )

        queue_item = MagicMock()
        queue_item.id = uuid.uuid4()

        async def fake_submit_queue_review_impl(*args, **kwargs):
            return queue_item

        monkeypatch.setattr(
            review_module,
            "submit_queue_review_impl",
            fake_submit_queue_review_impl,
        )

        result = await review_service.submit_queue_review(
            item_id=queue_item.id,
            quality=3,
            time_spent_ms=1200,
            user_id=user_id,
        )

        assert result is queue_item
        assert review_service._get_cached_queue_stats(user_id) is None


class TestLearningStart:
    @pytest.mark.asyncio
    async def test_start_learning_entry_for_word_commits_created_target_states(
        self, review_service, mock_db
    ):
        user_id = uuid.uuid4()
        word_id = uuid.uuid4()
        meaning_id = uuid.uuid4()
        word = Word(id=word_id, word="resilience", language="en")
        meaning = Meaning(
            id=meaning_id,
            word_id=word_id,
            definition="The capacity to recover quickly from difficulties.",
            order_index=0,
        )

        status_result = MagicMock()
        status_result.scalar_one_or_none.return_value = None
        word_result = MagicMock()
        word_result.scalar_one_or_none.return_value = word
        meanings_result = MagicMock()
        meanings_result.scalars.return_value.all.return_value = [meaning]
        mock_db.execute.side_effect = [status_result, word_result, meanings_result]

        review_service._get_user_review_preferences = AsyncMock(
            return_value=MagicMock(
                review_depth_preset="balanced",
                enable_confidence_check=True,
                enable_audio_spelling=False,
            )
        )
        review_service._get_user_accent_preference = AsyncMock(return_value="us")
        review_service._fetch_first_meaning_sentence_map = AsyncMock(return_value={meaning_id: None})
        review_service._fetch_history_count_by_word_id = AsyncMock(return_value={word_id: 0})
        target_state = EntryReviewState(
                id=uuid.uuid4(),
                user_id=user_id,
                entry_type="word",
                entry_id=word_id,
                target_type="meaning",
                target_id=meaning_id,
                stability=1.0,
                difficulty=0.5,
            )
        target_state.srs_bucket = "1d"
        target_state.cadence_step = 0
        target_state.interval_days = 1
        _set_canonical_schedule(target_state, datetime.now(timezone.utc) + timedelta(days=1))
        review_service._ensure_target_review_state = AsyncMock(return_value=target_state)
        review_service._build_word_detail_payload = AsyncMock(
            return_value={
                "entry_type": "word",
                "entry_id": str(word_id),
                "display_text": "resilience",
                "meaning_count": 1,
                "remembered_count": 0,
                "compare_with": [],
                "meanings": [],
            }
        )
        review_service._build_card_prompt = AsyncMock(
            return_value={
                "mode": "mcq",
                "prompt_type": "definition_to_entry",
                "question": "The capacity to recover quickly from difficulties.",
                "options": [],
            }
        )

        await review_service.start_learning_entry(
            user_id=user_id,
            entry_type="word",
            entry_id=word_id,
        )

        created_status = mock_db.add.call_args_list[0].args[0]
        assert isinstance(created_status, LearnerEntryStatus)
        assert created_status.status == "learning"
        assert target_state.min_due_at_utc is not None
        mock_db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_ensure_target_review_state_initializes_new_learning_schedule(
        self, review_service, mock_db
    ):
        user_id = uuid.uuid4()
        word_id = uuid.uuid4()
        meaning_id = uuid.uuid4()

        existing_result = MagicMock()
        existing_result.scalar_one_or_none.return_value = None
        created_state: EntryReviewState | None = None

        async def flush_side_effect():
            nonlocal created_state
            created_state = mock_db.add.call_args.args[0]

        mock_db.execute.side_effect = [existing_result]
        mock_db.flush.side_effect = flush_side_effect

        state = await review_service._ensure_target_review_state(
            user_id=user_id,
            target_type="meaning",
            target_id=meaning_id,
            entry_type="word",
            entry_id=word_id,
        )

        assert state is created_state
        assert state.srs_bucket == "1d"
        assert state.interval_days == 1
        assert state.cadence_step == 0
        assert state.min_due_at_utc is not None
        assert state.min_due_at_utc > datetime.now(timezone.utc)

    @pytest.mark.asyncio
    async def test_start_learning_entry_for_phrase_uses_phrase_target_state_as_queue_item_id(
        self, review_service, mock_db
    ):
        user_id = uuid.uuid4()
        phrase_id = uuid.uuid4()
        state_id = uuid.uuid4()
        sense_id = uuid.uuid4()
        phrase = MagicMock()
        phrase.id = phrase_id
        phrase.phrase_text = "jump the gun"

        state = EntryReviewState(
            id=state_id,
            user_id=user_id,
            entry_type="phrase",
            entry_id=phrase_id,
            target_type="phrase_sense",
            target_id=sense_id,
            stability=3,
            difficulty=0.5,
        )
        sense = MagicMock()
        sense.id = sense_id
        sense.definition = "To do something too soon."
        sense.order_index = 0

        status_result = MagicMock()
        status_result.scalar_one_or_none.return_value = None
        phrase_result = MagicMock()
        phrase_result.scalar_one_or_none.return_value = phrase
        senses_result = MagicMock()
        senses_result.scalars.return_value.all.return_value = [sense]

        review_service._ensure_target_review_state = AsyncMock(return_value=state)
        review_service._get_user_review_preferences = AsyncMock(
            return_value=MagicMock(
                review_depth_preset="balanced",
                enable_confidence_check=True,
                enable_audio_spelling=False,
            )
        )
        review_service._build_phrase_detail_payload = AsyncMock(
            return_value={
                "entry_type": "phrase",
                "entry_id": str(phrase_id),
                "display_text": "jump the gun",
                "meaning_count": 1,
                "remembered_count": 0,
                "compare_with": [],
                "meanings": [],
            }
        )
        review_service._fetch_first_sense_sentence_map = AsyncMock(
            return_value={sense_id: "They jumped the gun and announced it early."}
        )
        review_service._build_card_prompt = AsyncMock(
            return_value={
                "mode": "mcq",
                "prompt_type": "definition_to_entry",
                "question": "To do something too soon.",
                "options": [],
            }
        )
        mock_db.execute.side_effect = [status_result, phrase_result, senses_result]

        payload = await review_service.start_learning_entry(
            user_id=user_id,
            entry_type="phrase",
            entry_id=phrase_id,
        )

        assert payload["queue_item_ids"] == [str(state_id)]
        assert payload["cards"][0]["queue_item_id"] == str(state_id)
        created_status = mock_db.add.call_args_list[0].args[0]
        assert isinstance(created_status, LearnerEntryStatus)
        assert created_status.status == "learning"

    def test_default_schedule_option_avoids_same_day_as_default_for_newly_fragile_items(
        self, review_service
    ):
        assert review_service._default_schedule_option_value(0) == "1d"


class TestReviewRedesignGaps:
    def test_normalize_typed_answer_ignores_case_punctuation_and_extra_whitespace(
        self, review_service
    ):
        normalized = review_service._normalize_typed_answer("  Look,   up!! ")

        assert normalized == "look up"

    def test_compare_typed_answer_returns_particle_feedback_for_phrase_mismatch(
        self, review_service
    ):
        comparison = review_service._compare_typed_answer(
            expected_input="look up",
            typed_answer="look in",
            entry_type="phrase",
        )

        assert comparison["is_correct"] is False
        assert comparison["feedback_note"] == (
            "The verb is right, but the particle is different. Changing the particle changes the phrase."
        )

    @pytest.mark.asyncio
    async def test_build_card_prompt_suppresses_ambiguous_audio_for_multi_sense_parent(
        self, review_service
    ):
        review_service._get_user_review_preferences = AsyncMock(
            return_value=MagicMock(
                review_depth_preset="balanced",
                enable_audio_spelling=False,
                enable_confidence_check=True,
            )
        )
        review_service._fetch_same_day_entry_distractors = AsyncMock(return_value=["set in", "set up"])
        review_service._fetch_adjacent_entry_distractors = AsyncMock(return_value=["set aside"])
        review_service._fetch_same_day_definition_distractors = AsyncMock(return_value=[])
        review_service._fetch_adjacent_definition_distractors = AsyncMock(return_value=[])

        prompt = await review_service._build_card_prompt(
            review_mode=ReviewService.REVIEW_MODE_MCQ,
            source_text="set off",
            definition="To start a journey.",
            sentence="They set off before sunrise.",
            is_phrase_entry=True,
            distractor_seed="sense-1",
            meaning_id=uuid.uuid4(),
            index=0,
            alternative_definitions=[
                "To start a journey.",
                "To cause an alarm to ring.",
            ],
            active_target_count=2,
            user_id=uuid.uuid4(),
            source_entry_id=uuid.uuid4(),
            source_entry_type="phrase",
        )

        assert prompt["prompt_type"] != ReviewService.PROMPT_TYPE_AUDIO_TO_DEFINITION

    def test_select_prompt_audio_assets_prefers_example_then_sense_then_entry(
        self, review_service
    ):
        entry_asset = MagicMock()
        entry_asset.content_scope = "word"
        entry_asset.meaning_example_id = None
        entry_asset.meaning_id = None
        entry_asset.word_id = uuid.uuid4()

        sense_asset = MagicMock()
        sense_asset.content_scope = "definition"
        sense_asset.meaning_example_id = None
        sense_asset.meaning_id = uuid.uuid4()
        sense_asset.word_id = None

        example_asset = MagicMock()
        example_asset.content_scope = "example"
        example_asset.meaning_example_id = uuid.uuid4()
        example_asset.meaning_id = None
        example_asset.word_id = None

        selected = review_service._select_prompt_audio_assets(
            assets=[entry_asset, sense_asset, example_asset],
            target_entry_type="word",
            target_id=sense_asset.meaning_id,
            example_id=example_asset.meaning_example_id,
        )

        assert selected == [example_asset, sense_asset, entry_asset]

    @pytest.mark.asyncio
    async def test_start_learning_entry_for_word_uses_only_the_first_meaning(
        self, review_service, mock_db
    ):
        user_id = uuid.uuid4()
        word_id = uuid.uuid4()
        first_meaning_id = uuid.uuid4()
        second_meaning_id = uuid.uuid4()
        target_state_id = uuid.uuid4()

        word = Word(id=word_id, word="resilience", language="en")
        first_meaning = Meaning(
            id=first_meaning_id,
            word_id=word_id,
            definition="The capacity to recover quickly.",
            order_index=0,
        )
        second_meaning = Meaning(
            id=second_meaning_id,
            word_id=word_id,
            definition="A tendency to recover from shocks.",
            order_index=1,
        )
        target_state = EntryReviewState(
            id=target_state_id,
            user_id=user_id,
            entry_type="word",
            entry_id=word_id,
            target_type="meaning",
            target_id=first_meaning_id,
            stability=0.3,
            difficulty=0.5,
        )

        status_result = MagicMock()
        status_result.scalar_one_or_none.return_value = None
        word_result = MagicMock()
        word_result.scalar_one_or_none.return_value = word
        meaning_result = MagicMock()
        meaning_result.scalars.return_value.all.return_value = [first_meaning, second_meaning]
        mock_db.execute.side_effect = [status_result, word_result, meaning_result]

        review_service._ensure_entry_review_state = AsyncMock(
            side_effect=AssertionError("parent entry state helper should not be used")
        )
        review_service._ensure_target_review_state = AsyncMock(return_value=target_state)
        review_service._get_user_review_preferences = AsyncMock(
            return_value=MagicMock(
                review_depth_preset="balanced",
                enable_confidence_check=True,
                enable_audio_spelling=False,
            )
        )
        review_service._build_word_detail_payload = AsyncMock(
            return_value={
                "entry_type": "word",
                "entry_id": str(word_id),
                "display_text": "resilience",
                "meaning_count": 2,
                "remembered_count": 0,
                "compare_with": [],
                "meanings": [],
            }
        )
        review_service._get_user_accent_preference = AsyncMock(return_value="us")
        review_service._fetch_first_meaning_sentence_map = AsyncMock(
            return_value={first_meaning_id: None}
        )
        review_service._fetch_history_count_by_word_id = AsyncMock(return_value={word_id: 0})
        review_service._build_card_prompt = AsyncMock(
            return_value={
                "mode": "mcq",
                "prompt_type": "definition_to_entry",
                "question": "The capacity to recover quickly.",
                "options": [],
            }
        )

        payload = await review_service.start_learning_entry(
            user_id=user_id,
            entry_type="word",
            entry_id=word_id,
        )

        assert payload["meaning_ids"] == [str(first_meaning_id)]
        assert payload["queue_item_ids"] == [str(target_state_id)]
        assert len(payload["cards"]) == 1
        assert payload["cards"][0]["queue_item_id"] == str(target_state_id)
        assert payload["cards"][0]["meaning_id"] == str(first_meaning_id)
        kwargs = review_service._build_card_prompt.await_args.kwargs
        assert kwargs["definition"] == first_meaning.definition
        created_status = mock_db.add.call_args_list[0].args[0]
        assert isinstance(created_status, LearnerEntryStatus)
        assert created_status.status == "learning"

    def test_bury_sibling_targets_keeps_only_one_due_target_per_parent(self, review_service):
        parent_entry_id = uuid.uuid4()
        sibling_one = EntryReviewState(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            entry_type="word",
            entry_id=parent_entry_id,
            target_type="meaning",
            target_id=uuid.uuid4(),
            stability=2,
            difficulty=0.5,
        )
        sibling_two = EntryReviewState(
            id=uuid.uuid4(),
            user_id=sibling_one.user_id,
            entry_type="word",
            entry_id=parent_entry_id,
            target_type="meaning",
            target_id=uuid.uuid4(),
            stability=4,
            difficulty=0.5,
        )

        filtered = review_service._apply_sibling_bury_rule([sibling_one, sibling_two])

        assert filtered == [sibling_one]

    @pytest.mark.asyncio
    async def test_get_due_queue_items_hydrates_the_first_meaning_even_for_legacy_target_rows(
        self, review_service, mock_db
    ):
        user_id = uuid.uuid4()
        word_id = uuid.uuid4()
        first_meaning_id = uuid.uuid4()
        legacy_target_meaning_id = uuid.uuid4()
        state = EntryReviewState(
            id=uuid.uuid4(),
            user_id=user_id,
            entry_type="word",
            entry_id=word_id,
            target_type="meaning",
            target_id=legacy_target_meaning_id,
            stability=5,
            difficulty=0.5,
        )
        _set_canonical_schedule(state, datetime.now(timezone.utc) - timedelta(minutes=5))

        word = Word(id=word_id, word="resilience", language="en")
        first_meaning = Meaning(
            id=first_meaning_id,
            word_id=word_id,
            definition="The capacity to recover quickly from difficulties.",
            order_index=0,
        )
        legacy_target_meaning = Meaning(
            id=legacy_target_meaning_id,
            word_id=word_id,
            definition="A tendency to bounce back after setbacks.",
            order_index=1,
        )

        state_result = MagicMock()
        state_result.scalars.return_value.all.return_value = [state]
        word_result = MagicMock()
        word_result.scalars.return_value.all.return_value = [word]
        meanings_result = MagicMock()
        meanings_result.scalars.return_value.all.return_value = [
            first_meaning,
            legacy_target_meaning,
        ]
        mock_db.execute.side_effect = [state_result, word_result, meanings_result]

        review_service._get_user_review_preferences = AsyncMock(
            return_value=MagicMock(review_depth_preset="balanced", enable_confidence_check=True)
        )
        review_service._get_user_accent_preference = AsyncMock(return_value="us")
        review_service._fetch_first_meaning_sentence_map = AsyncMock(
            return_value={first_meaning_id: None, legacy_target_meaning_id: None}
        )
        review_service._fetch_history_count_by_word_id = AsyncMock(return_value={word_id: 1})
        review_service._build_card_prompt = AsyncMock(return_value={"prompt_type": "definition_to_entry"})
        review_service._build_word_detail_payload = AsyncMock(
            return_value={
                "entry_type": "word",
                "entry_id": str(word_id),
                "display_text": "resilience",
                "meaning_count": 2,
                "remembered_count": 1,
                "compare_with": [],
                "meanings": [],
            }
        )

        due_items = await review_service.get_due_queue_items(user_id=user_id, limit=10)

        assert len(due_items) == 1
        assert due_items[0]["definition"] == first_meaning.definition
        assert due_items[0]["source_meaning_id"] == str(first_meaning_id)
        assert due_items[0]["target_id"] == str(first_meaning_id)
        assert state.target_id == legacy_target_meaning_id

    @pytest.mark.asyncio
    async def test_get_due_queue_items_does_not_mutate_orm_target_when_duplicate_first_meaning_row_exists(
        self, review_service, mock_db
    ):
        user_id = uuid.uuid4()
        word_id = uuid.uuid4()
        first_meaning_id = uuid.uuid4()
        legacy_target_meaning_id = uuid.uuid4()

        legacy_state = EntryReviewState(
            id=uuid.uuid4(),
            user_id=user_id,
            entry_type="word",
            entry_id=word_id,
            target_type="meaning",
            target_id=legacy_target_meaning_id,
            stability=5,
            difficulty=0.5,
        )
        _set_canonical_schedule(legacy_state, datetime.now(timezone.utc) - timedelta(minutes=5))

        first_meaning_state = EntryReviewState(
            id=uuid.uuid4(),
            user_id=user_id,
            entry_type="word",
            entry_id=word_id,
            target_type="meaning",
            target_id=first_meaning_id,
            stability=3,
            difficulty=0.5,
        )
        _set_canonical_schedule(first_meaning_state, datetime.now(timezone.utc) - timedelta(minutes=4))

        word = Word(id=word_id, word="resilience", language="en")
        first_meaning = Meaning(
            id=first_meaning_id,
            word_id=word_id,
            definition="The capacity to recover quickly from difficulties.",
            order_index=0,
        )
        legacy_target_meaning = Meaning(
            id=legacy_target_meaning_id,
            word_id=word_id,
            definition="A tendency to bounce back after setbacks.",
            order_index=1,
        )

        state_result = MagicMock()
        state_result.scalars.return_value.all.return_value = [legacy_state, first_meaning_state]
        word_result = MagicMock()
        word_result.scalars.return_value.all.return_value = [word]
        meanings_result = MagicMock()
        meanings_result.scalars.return_value.all.return_value = [
            first_meaning,
            legacy_target_meaning,
        ]
        mock_db.execute.side_effect = [state_result, word_result, meanings_result]

        review_service._get_user_review_preferences = AsyncMock(
            return_value=MagicMock(review_depth_preset="balanced", enable_confidence_check=True)
        )
        review_service._get_user_accent_preference = AsyncMock(return_value="us")
        review_service._fetch_first_meaning_sentence_map = AsyncMock(
            return_value={first_meaning_id: None, legacy_target_meaning_id: None}
        )
        review_service._fetch_history_count_by_word_id = AsyncMock(return_value={word_id: 1})
        review_service._build_card_prompt = AsyncMock(return_value={"prompt_type": "definition_to_entry"})
        review_service._build_word_detail_payload = AsyncMock(
            return_value={
                "entry_type": "word",
                "entry_id": str(word_id),
                "display_text": "resilience",
                "meaning_count": 2,
                "remembered_count": 1,
                "compare_with": [],
                "meanings": [],
            }
        )

        due_items = await review_service.get_due_queue_items(user_id=user_id, limit=10)

        assert len(due_items) == 1
        assert due_items[0]["source_meaning_id"] == str(first_meaning_id)
        assert due_items[0]["target_id"] == str(first_meaning_id)
        assert legacy_state.target_id == legacy_target_meaning_id
        assert first_meaning_state.target_id == first_meaning_id

    @pytest.mark.asyncio
    async def test_submit_queue_review_persists_the_first_meaning_target_for_legacy_rows(
        self, review_service, mock_db
    ):
        user_id = uuid.uuid4()
        state_id = uuid.uuid4()
        word_id = uuid.uuid4()
        legacy_target_id = uuid.uuid4()
        first_meaning_id = uuid.uuid4()
        prompt_id = str(uuid.uuid4())
        entry_state = EntryReviewState(
            id=state_id,
            user_id=user_id,
            entry_type="word",
            entry_id=word_id,
            target_type="meaning",
            target_id=legacy_target_id,
            stability=3,
            difficulty=0.4,
        )
        entry_state.meaning_id = legacy_target_id

        locked_result = MagicMock()
        locked_result.scalar_one_or_none.return_value = entry_state
        learner_status_result = MagicMock()
        learner_status_result.scalar_one_or_none.return_value = LearnerEntryStatus(
            user_id=user_id,
            entry_type="word",
            entry_id=word_id,
            status="learning",
        )
        mock_db.execute.side_effect = [locked_result, learner_status_result]
        review_service._build_detail_payload_for_word_id = AsyncMock(
            return_value={
                "entry_type": "word",
                "entry_id": str(word_id),
                "display_text": "resilience",
            }
        )
        review_service._record_entry_review_event = AsyncMock()

        prompt_token = review_service._encode_prompt_token(
            {
                "prompt_id": prompt_id,
                "user_id": str(user_id),
                "queue_item_id": str(state_id),
                "prompt_type": ReviewService.PROMPT_TYPE_DEFINITION_TO_ENTRY,
                "review_mode": ReviewService.REVIEW_MODE_MCQ,
                "source_entry_type": "word",
                "source_entry_id": str(word_id),
                "source_meaning_id": str(first_meaning_id),
                "correct_option_id": "A",
            }
        )

        updated = await review_service.submit_queue_review(
            item_id=state_id,
            quality=4,
            time_spent_ms=5000,
            user_id=user_id,
            selected_option_id="A",
            prompt_token=prompt_token,
            confirm=True,
        )

        assert updated.target_id == first_meaning_id
        assert updated.meaning_id == first_meaning_id
        assert updated.target_type == "meaning"
        assert review_service._record_entry_review_event.await_args.kwargs["target_id"] == first_meaning_id

    @pytest.mark.asyncio
    async def test_get_due_queue_items_buries_due_sibling_targets_for_same_parent(
        self, review_service, mock_db
    ):
        user_id = uuid.uuid4()
        word_id = uuid.uuid4()
        first_meaning_id = uuid.uuid4()
        second_meaning_id = uuid.uuid4()

        first_state = EntryReviewState(
            id=uuid.uuid4(),
            user_id=user_id,
            entry_type="word",
            entry_id=word_id,
            target_type="meaning",
            target_id=first_meaning_id,
            stability=2,
            difficulty=0.5,
        )
        _set_canonical_schedule(first_state, datetime.now(timezone.utc) - timedelta(minutes=6))
        second_state = EntryReviewState(
            id=uuid.uuid4(),
            user_id=user_id,
            entry_type="word",
            entry_id=word_id,
            target_type="meaning",
            target_id=second_meaning_id,
            stability=4,
            difficulty=0.5,
        )
        _set_canonical_schedule(second_state, datetime.now(timezone.utc) - timedelta(minutes=5))

        state_result = MagicMock()
        state_result.scalars.return_value.all.return_value = [first_state, second_state]
        accent_result = MagicMock()
        accent_result.scalar_one_or_none.return_value = "us"
        word_result = MagicMock()
        word_result.scalars.return_value.all.return_value = [
            Word(id=word_id, word="resilience", language="en")
        ]
        meanings_result = MagicMock()
        meanings_result.scalars.return_value.all.return_value = [
            Meaning(id=first_meaning_id, word_id=word_id, definition="Definition one"),
            Meaning(id=second_meaning_id, word_id=word_id, definition="Definition two"),
        ]
        sentence_map_result = MagicMock()
        sentence_map_result.all.return_value = []
        history_count_result = MagicMock()
        history_count_result.all.return_value = []
        mock_db.execute.side_effect = [
            state_result,
            accent_result,
            word_result,
            meanings_result,
            sentence_map_result,
            history_count_result,
        ]

        review_service._get_user_review_preferences = AsyncMock(
            return_value=MagicMock(review_depth_preset="balanced", enable_confidence_check=True)
        )
        review_service._build_card_prompt = AsyncMock(return_value={"prompt_type": "definition_to_entry"})
        review_service._build_word_detail_payload = AsyncMock(
            return_value={
                "entry_type": "word",
                "entry_id": str(word_id),
                "display_text": "resilience",
                "meaning_count": 2,
                "remembered_count": 1,
                "compare_with": [],
                "meanings": [],
            }
        )

        due_items = await review_service.get_due_queue_items(user_id=user_id, limit=10)

        assert len(due_items) == 1
        assert due_items[0]["source_meaning_id"] == str(first_meaning_id)

    @pytest.mark.asyncio
    async def test_get_due_queue_items_overfetches_before_burying_siblings(
        self, review_service, mock_db
    ):
        user_id = uuid.uuid4()
        state_result = MagicMock()
        state_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = state_result

        await review_service.get_due_queue_items(user_id=user_id, limit=5)

        executed_query = mock_db.execute.await_args_list[0].args[0]
        compiled = executed_query.compile(compile_kwargs={"literal_binds": True})
        assert "LIMIT 40" in str(compiled)

    @pytest.mark.asyncio
    async def test_get_due_queue_items_uses_wide_overfetch_window_for_small_limits(
        self, review_service, mock_db
    ):
        user_id = uuid.uuid4()
        state_result = MagicMock()
        state_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = state_result

        await review_service.get_due_queue_items(user_id=user_id, limit=1)

        executed_query = mock_db.execute.await_args_list[0].args[0]
        compiled = executed_query.compile(compile_kwargs={"literal_binds": True})
        assert "LIMIT 33" in str(compiled)

    @pytest.mark.asyncio
    async def test_fetch_same_day_entry_distractors_reuses_request_local_pool(
        self, review_service, mock_db
    ):
        user_id = uuid.uuid4()
        result = MagicMock()
        result.all.return_value = [
            (uuid.uuid4(), "alpha"),
            (uuid.uuid4(), "beta"),
            (uuid.uuid4(), "gamma"),
            (uuid.uuid4(), "delta"),
        ]
        mock_db.execute.return_value = result

        first = await review_service._fetch_same_day_entry_distractors(
            user_id=user_id,
            target_entry_id=uuid.uuid4(),
            target_entry_type="word",
            limit=3,
        )
        second = await review_service._fetch_same_day_entry_distractors(
            user_id=user_id,
            target_entry_id=uuid.uuid4(),
            target_entry_type="word",
            limit=3,
        )

        assert first == ["alpha", "beta", "gamma"]
        assert second == ["alpha", "beta", "gamma"]
        assert mock_db.execute.await_count == 1



class TestEntryReviewStateConcurrency:
    @pytest.mark.asyncio
    async def test_ensure_target_review_state_recovers_from_concurrent_insert(
        self, review_service, mock_db
    ):
        user_id = uuid.uuid4()
        target_id = uuid.uuid4()
        entry_id = uuid.uuid4()
        recovered_state = EntryReviewState(
            id=uuid.uuid4(),
            user_id=user_id,
            target_type="meaning",
            target_id=target_id,
            entry_type="word",
            entry_id=entry_id,
            stability=0.3,
            difficulty=0.5,
        )

        first_lookup = MagicMock()
        first_lookup.scalar_one_or_none.return_value = None
        second_lookup = MagicMock()
        second_lookup.scalar_one_or_none.return_value = recovered_state
        mock_db.execute.side_effect = [first_lookup, second_lookup]
        mock_db.flush.side_effect = IntegrityError("insert", {}, Exception("duplicate key"))

        state = await review_service._ensure_target_review_state(
            user_id=user_id,
            target_type="meaning",
            target_id=target_id,
            entry_type="word",
            entry_id=entry_id,
        )

        assert state is recovered_state
        assert mock_db.execute.await_count == 2

    @pytest.mark.asyncio
    async def test_submit_queue_review_treats_same_prompt_token_as_idempotent(
        self, review_service, mock_db
    ):
        user_id = uuid.uuid4()
        state_id = uuid.uuid4()
        meaning_id = uuid.uuid4()
        entry_id = uuid.uuid4()
        prompt_id = str(uuid.uuid4())
        entry_state = EntryReviewState(
            id=state_id,
            user_id=user_id,
            entry_type="word",
            entry_id=entry_id,
            target_type="meaning",
            target_id=meaning_id,
            stability=3,
            difficulty=0.4,
        )
        entry_state.last_submission_prompt_id = prompt_id
        entry_state.detail = {"entry_type": "word", "entry_id": str(entry_id), "display_text": "bank"}
        entry_state.schedule_options = [{"value": "1d", "label": "Tomorrow", "is_default": True}]

        locked_result = MagicMock()
        locked_result.scalar_one_or_none.return_value = entry_state
        mock_db.execute.return_value = locked_result

        prompt_token = review_service._encode_prompt_token(
            {
                "prompt_id": prompt_id,
                "user_id": str(user_id),
                "queue_item_id": str(state_id),
                "prompt_type": ReviewService.PROMPT_TYPE_DEFINITION_TO_ENTRY,
                "review_mode": ReviewService.REVIEW_MODE_MCQ,
                "source_entry_type": "word",
                "source_entry_id": str(entry_id),
                "source_meaning_id": str(meaning_id),
                "correct_option_id": "A",
            }
        )

        updated = await review_service.submit_queue_review(
            item_id=state_id,
            quality=4,
            time_spent_ms=5000,
            user_id=user_id,
            selected_option_id="A",
            prompt_token=prompt_token,
        )

        assert updated is entry_state
        mock_db.add.assert_not_called()
        mock_db.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_submit_queue_review_rehydrates_idempotent_entry_state_response(
        self, review_service, mock_db
    ):
        user_id = uuid.uuid4()
        state_id = uuid.uuid4()
        meaning_id = uuid.uuid4()
        entry_id = uuid.uuid4()
        prompt_id = str(uuid.uuid4())
        entry_state = EntryReviewState(
            id=state_id,
            user_id=user_id,
            entry_type="word",
            entry_id=entry_id,
            target_type="meaning",
            target_id=meaning_id,
            stability=3,
            difficulty=0.4,
        )
        entry_state.interval_days = 1
        entry_state.last_submission_prompt_id = prompt_id

        locked_result = MagicMock()
        locked_result.scalar_one_or_none.return_value = entry_state
        mock_db.execute.return_value = locked_result
        review_service._build_detail_payload_for_word_id = AsyncMock(
            return_value={
                "entry_type": "word",
                "entry_id": str(entry_id),
                "display_text": "resilience",
            }
        )

        prompt_token = review_service._encode_prompt_token(
            {
                "prompt_id": prompt_id,
                "user_id": str(user_id),
                "queue_item_id": str(state_id),
                "prompt_type": ReviewService.PROMPT_TYPE_TYPED_RECALL,
                "review_mode": ReviewService.REVIEW_MODE_MCQ,
                "source_entry_type": "word",
                "source_entry_id": str(entry_id),
                "source_meaning_id": str(meaning_id),
                "expected_input": "resilience",
            }
        )

        updated = await review_service.submit_queue_review(
            item_id=state_id,
            quality=4,
            time_spent_ms=5000,
            user_id=user_id,
            typed_answer="resilience",
            prompt_token=prompt_token,
            outcome="correct_tested",
        )

        assert updated is entry_state
        assert updated.detail == {
            "entry_type": "word",
            "entry_id": str(entry_id),
            "display_text": "resilience",
        }
        assert any(
            option["value"] == "1d" and option["is_default"]
            for option in updated.schedule_options or []
        )
        mock_db.add.assert_not_called()
        mock_db.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_submit_queue_review_applies_schedule_override_on_idempotent_resubmit(
        self, review_service, mock_db, monkeypatch
    ):
        original_reviewed_at = datetime(2026, 4, 10, 14, 30, tzinfo=timezone.utc)
        retried_at = datetime(2026, 4, 10, 18, 30, tzinfo=timezone.utc)
        user_id = uuid.uuid4()
        state_id = uuid.uuid4()
        meaning_id = uuid.uuid4()
        entry_id = uuid.uuid4()
        prompt_id = str(uuid.uuid4())
        original_due_at = min_due_at_for_bucket(
            reviewed_at_utc=original_reviewed_at,
            user_timezone="Australia/Melbourne",
            bucket="1d",
        )
        entry_state = EntryReviewState(
            id=state_id,
            user_id=user_id,
            entry_type="word",
            entry_id=entry_id,
            target_type="meaning",
            target_id=meaning_id,
            stability=3,
            difficulty=0.4,
        )
        entry_state.interval_days = 1
        entry_state.last_reviewed_at = original_reviewed_at
        entry_state.due_review_date = due_review_date_for_bucket(
            reviewed_at_utc=original_reviewed_at,
            user_timezone="Australia/Melbourne",
            bucket="1d",
        )
        entry_state.min_due_at_utc = original_due_at
        entry_state.last_submission_prompt_id = prompt_id
        entry_state.last_outcome = "correct_tested"
        entry_state.detail = {"entry_type": "word", "entry_id": str(entry_id), "display_text": "bank"}
        entry_state.schedule_options = [{"value": "1d", "label": "Tomorrow", "is_default": True}]

        locked_result = MagicMock()
        locked_result.scalar_one_or_none.return_value = entry_state
        prefs_result = MagicMock()
        prefs_result.scalar_one_or_none.return_value = UserPreference(
            user_id=user_id,
            timezone="Australia/Melbourne",
        )
        learner_status_result = MagicMock()
        learner_status_result.scalar_one_or_none.return_value = LearnerEntryStatus(
            user_id=user_id,
            entry_type="word",
            entry_id=entry_id,
            status="learning",
        )
        mock_db.execute.side_effect = [locked_result, prefs_result, learner_status_result]
        review_service._get_user_review_preferences = AsyncMock(
            return_value=UserPreference(
                user_id=user_id,
                timezone="Australia/Melbourne",
            )
        )
        monkeypatch.setattr(
            review_submission_module,
            "datetime",
            _frozen_datetime_class(retried_at),
        )

        prompt_token = review_service._encode_prompt_token(
            {
                "prompt_id": prompt_id,
                "user_id": str(user_id),
                "queue_item_id": str(state_id),
                "prompt_type": ReviewService.PROMPT_TYPE_DEFINITION_TO_ENTRY,
                "review_mode": ReviewService.REVIEW_MODE_MCQ,
                "source_entry_type": "word",
                "source_entry_id": str(entry_id),
                "source_meaning_id": str(meaning_id),
                "correct_option_id": "A",
            }
        )

        updated = await review_service.submit_queue_review(
            item_id=state_id,
            quality=4,
            time_spent_ms=5000,
            user_id=user_id,
            selected_option_id="A",
            prompt_token=prompt_token,
            schedule_override="7d",
        )

        assert updated is entry_state
        assert updated.interval_days == 7
        assert updated.due_review_date == due_review_date_for_bucket(
            reviewed_at_utc=original_reviewed_at,
            user_timezone="Australia/Melbourne",
            bucket="7d",
        )
        assert updated.min_due_at_utc == min_due_at_for_bucket(
            reviewed_at_utc=original_reviewed_at,
            user_timezone="Australia/Melbourne",
            bucket="7d",
        )
        assert updated.min_due_at_utc == min_due_at_for_bucket(
            reviewed_at_utc=original_reviewed_at,
            user_timezone="Australia/Melbourne",
            bucket="7d",
        )
        assert updated.min_due_at_utc != min_due_at_for_bucket(
            reviewed_at_utc=retried_at,
            user_timezone="Australia/Melbourne",
            bucket="7d",
        )
        assert updated.srs_bucket == "7d"
        assert updated.cadence_step == 1
        assert any(
            option["value"] == "7d" and option["is_default"]
            for option in updated.schedule_options or []
        )
        mock_db.add.assert_not_called()
        mock_db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_submit_queue_review_advances_exactly_one_bucket_on_success(
        self, review_service, mock_db, monkeypatch
    ):
        user_id = uuid.uuid4()
        state_id = uuid.uuid4()
        meaning_id = uuid.uuid4()
        entry_id = uuid.uuid4()
        entry_state = EntryReviewState(
            id=state_id,
            user_id=user_id,
            entry_type="word",
            entry_id=entry_id,
            target_type="meaning",
            target_id=meaning_id,
            stability=3,
            difficulty=0.4,
            srs_bucket="1d",
            cadence_step=0,
        )

        locked_result = MagicMock()
        locked_result.scalar_one_or_none.return_value = entry_state
        learner_status_result = MagicMock()
        learner_status_result.scalar_one_or_none.return_value = LearnerEntryStatus(
            user_id=user_id,
            entry_type="word",
            entry_id=entry_id,
            status="learning",
        )
        mock_db.execute.side_effect = [locked_result, learner_status_result]
        review_service._build_detail_payload_for_word_id = AsyncMock(
            return_value={
                "entry_type": "word",
                "entry_id": str(entry_id),
                "display_text": "resilience",
            }
        )

        next_review = datetime.now(timezone.utc) + timedelta(days=7)
        monkeypatch.setattr(
            review_submission_module,
            "calculate_next_review",
            MagicMock(
                return_value=MagicMock(
                    interval_days=7,
                    next_review=next_review,
                    stability=7.0,
                    difficulty=0.5,
                    is_fragile=False,
                )
            ),
        )

        prompt_token = review_service._encode_prompt_token(
            {
                "prompt_id": str(uuid.uuid4()),
                "user_id": str(user_id),
                "queue_item_id": str(state_id),
                "prompt_type": ReviewService.PROMPT_TYPE_DEFINITION_TO_ENTRY,
                "review_mode": ReviewService.REVIEW_MODE_MCQ,
                "source_entry_type": "word",
                "source_entry_id": str(entry_id),
                "source_meaning_id": str(meaning_id),
                "correct_option_id": "A",
            }
        )

        updated = await review_service.submit_queue_review(
            item_id=state_id,
            quality=4,
            time_spent_ms=5000,
            user_id=user_id,
            selected_option_id="A",
            prompt_token=prompt_token,
            confirm=True,
        )

        assert updated.srs_bucket == "2d"
        assert updated.cadence_step == 1
        assert updated.interval_days == 2

    @pytest.mark.asyncio
    async def test_submit_queue_review_ignores_client_outcome_for_objective_prompts(
        self, review_service, mock_db
    ):
        user_id = uuid.uuid4()
        state_id = uuid.uuid4()
        meaning_id = uuid.uuid4()
        entry_id = uuid.uuid4()
        entry_state = EntryReviewState(
            id=state_id,
            user_id=user_id,
            entry_type="word",
            entry_id=entry_id,
            target_type="meaning",
            target_id=meaning_id,
            stability=3,
            difficulty=0.4,
        )

        locked_result = MagicMock()
        locked_result.scalar_one_or_none.return_value = entry_state
        detail_result = MagicMock()
        detail_result.scalar_one_or_none.return_value = Word(id=entry_id, word="drum", language="en")
        meanings_result = MagicMock()
        meanings_result.scalars.return_value.all.return_value = [
            Meaning(
                id=meaning_id,
                word_id=entry_id,
                definition="A percussion instrument.",
                part_of_speech="noun",
                order_index=0,
            )
        ]
        history_result = MagicMock()
        history_result.scalar_one.return_value = 0
        learner_status_result = MagicMock()
        learner_status_result.scalar_one_or_none.return_value = LearnerEntryStatus(
            user_id=user_id,
            entry_type="word",
            entry_id=entry_id,
            status="learning",
        )
        mock_db.execute.side_effect = [locked_result, learner_status_result]
        review_service._build_detail_payload_for_word_id = AsyncMock(
            return_value={"entry_type": "word", "entry_id": str(entry_id), "display_text": "drum"}
        )

        prompt_token = review_service._encode_prompt_token(
            {
                "prompt_id": str(uuid.uuid4()),
                "user_id": str(user_id),
                "queue_item_id": str(state_id),
                "prompt_type": ReviewService.PROMPT_TYPE_DEFINITION_TO_ENTRY,
                "review_mode": ReviewService.REVIEW_MODE_MCQ,
                "source_entry_type": "word",
                "source_entry_id": str(entry_id),
                "source_meaning_id": str(meaning_id),
                "correct_option_id": "A",
            }
        )

        updated = await review_service.submit_queue_review(
            item_id=state_id,
            quality=4,
            time_spent_ms=5000,
            user_id=user_id,
            selected_option_id="B",
            outcome="remember",
            prompt_token=prompt_token,
        )

        assert updated.outcome == "wrong"
        assert updated.needs_relearn is True

    @pytest.mark.asyncio
    async def test_submit_queue_review_failure_steps_back_bucket_but_schedules_tomorrow(
        self, review_service, mock_db
    ):
        user_id = uuid.uuid4()
        state_id = uuid.uuid4()
        meaning_id = uuid.uuid4()
        entry_id = uuid.uuid4()
        entry_state = EntryReviewState(
            id=state_id,
            user_id=user_id,
            entry_type="word",
            entry_id=entry_id,
            target_type="meaning",
            target_id=meaning_id,
            stability=14,
            difficulty=0.4,
            srs_bucket="14d",
            cadence_step=2,
        )
        locked_result = MagicMock()
        locked_result.scalar_one_or_none.return_value = entry_state
        learner_status_result = MagicMock()
        learner_status_result.scalar_one_or_none.return_value = LearnerEntryStatus(
            user_id=user_id,
            entry_type="word",
            entry_id=entry_id,
            status="learning",
        )
        mock_db.execute.side_effect = [locked_result, learner_status_result]
        review_service._build_detail_payload_for_word_id = AsyncMock(
            return_value={"entry_type": "word", "entry_id": str(entry_id), "display_text": "drum"}
        )

        prompt_token = review_service._encode_prompt_token(
            {
                "prompt_id": str(uuid.uuid4()),
                "user_id": str(user_id),
                "queue_item_id": str(state_id),
                "prompt_type": ReviewService.PROMPT_TYPE_DEFINITION_TO_ENTRY,
                "review_mode": ReviewService.REVIEW_MODE_MCQ,
                "source_entry_type": "word",
                "source_entry_id": str(entry_id),
                "source_meaning_id": str(meaning_id),
                "correct_option_id": "A",
            }
        )

        before = datetime.now(timezone.utc)
        updated = await review_service.submit_queue_review(
            item_id=state_id,
            quality=0,
            time_spent_ms=3000,
            user_id=user_id,
            selected_option_id="B",
            prompt_token=prompt_token,
            confirm=True,
        )
        after = datetime.now(timezone.utc)

        assert updated.outcome == "wrong"
        assert updated.srs_bucket == "7d"
        assert updated.interval_days == 7
        assert updated.min_due_at_utc is not None
        assert updated.due_review_date is not None
        assert updated.due_review_date in {
            due_review_date_for_bucket(
                reviewed_at_utc=before,
                user_timezone="UTC",
                bucket="1d",
            ),
            due_review_date_for_bucket(
                reviewed_at_utc=after,
                user_timezone="UTC",
                bucket="1d",
            ),
        }
        assert updated.recheck_due_at is not None
        assert updated.schedule_options == []

    @pytest.mark.asyncio
    async def test_submit_queue_review_rejects_schedule_override_after_failure(
        self, review_service, mock_db
    ):
        user_id = uuid.uuid4()
        state_id = uuid.uuid4()
        meaning_id = uuid.uuid4()
        entry_id = uuid.uuid4()
        entry_state = EntryReviewState(
            id=state_id,
            user_id=user_id,
            entry_type="word",
            entry_id=entry_id,
            target_type="meaning",
            target_id=meaning_id,
            stability=30,
            difficulty=0.4,
            srs_bucket="30d",
            cadence_step=0,
        )
        locked_result = MagicMock()
        locked_result.scalar_one_or_none.return_value = entry_state
        mock_db.execute.return_value = locked_result

        prompt_token = review_service._encode_prompt_token(
            {
                "prompt_id": str(uuid.uuid4()),
                "user_id": str(user_id),
                "queue_item_id": str(state_id),
                "prompt_type": ReviewService.PROMPT_TYPE_DEFINITION_TO_ENTRY,
                "review_mode": ReviewService.REVIEW_MODE_MCQ,
                "source_entry_type": "word",
                "source_entry_id": str(entry_id),
                "source_meaning_id": str(meaning_id),
                "correct_option_id": "A",
            }
        )

        with pytest.raises(ValueError, match="schedule_override is only allowed after success"):
            await review_service.submit_queue_review(
                item_id=state_id,
                quality=0,
                time_spent_ms=3000,
                user_id=user_id,
                selected_option_id="B",
                prompt_token=prompt_token,
                schedule_override="90d",
                confirm=True,
            )

    @pytest.mark.asyncio
    async def test_submit_queue_review_confidence_success_at_180d_does_not_mark_known(
        self, review_service, mock_db
    ):
        user_id = uuid.uuid4()
        state_id = uuid.uuid4()
        meaning_id = uuid.uuid4()
        entry_id = uuid.uuid4()
        entry_state = EntryReviewState(
            id=state_id,
            user_id=user_id,
            entry_type="word",
            entry_id=entry_id,
            target_type="meaning",
            target_id=meaning_id,
            stability=180,
            difficulty=0.4,
            srs_bucket="180d",
            cadence_step=2,
        )
        locked_result = MagicMock()
        locked_result.scalar_one_or_none.return_value = entry_state
        learner_status = LearnerEntryStatus(
            user_id=user_id,
            entry_type="word",
            entry_id=entry_id,
            status="learning",
        )
        learner_status_result = MagicMock()
        learner_status_result.scalar_one_or_none.return_value = learner_status
        mock_db.execute.side_effect = [locked_result, learner_status_result]
        review_service._build_detail_payload_for_word_id = AsyncMock(
            return_value={"entry_type": "word", "entry_id": str(entry_id), "display_text": "resilience"}
        )

        prompt_token = review_service._encode_prompt_token(
            {
                "prompt_id": str(uuid.uuid4()),
                "user_id": str(user_id),
                "queue_item_id": str(state_id),
                "prompt_type": ReviewService.PROMPT_TYPE_CONFIDENCE_CHECK,
                "review_mode": ReviewService.REVIEW_MODE_CONFIDENCE,
                "source_entry_type": "word",
                "source_entry_id": str(entry_id),
                "source_meaning_id": str(meaning_id),
                "correct_option_id": "A",
            }
        )

        updated = await review_service.submit_queue_review(
            item_id=state_id,
            quality=4,
            time_spent_ms=3000,
            user_id=user_id,
            selected_option_id="A",
            prompt_token=prompt_token,
            confirm=True,
        )

        assert updated.outcome == "remember"
        assert updated.srs_bucket == "180d"
        assert updated.interval_days == 180
        assert updated.min_due_at_utc is not None
        assert learner_status.status == "learning"

    @pytest.mark.asyncio
    async def test_submit_queue_review_objective_success_at_180d_marks_known(
        self, review_service, mock_db
    ):
        user_id = uuid.uuid4()
        state_id = uuid.uuid4()
        meaning_id = uuid.uuid4()
        entry_id = uuid.uuid4()
        entry_state = EntryReviewState(
            id=state_id,
            user_id=user_id,
            entry_type="word",
            entry_id=entry_id,
            target_type="meaning",
            target_id=meaning_id,
            stability=180,
            difficulty=0.4,
            srs_bucket="180d",
            cadence_step=2,
        )
        locked_result = MagicMock()
        locked_result.scalar_one_or_none.return_value = entry_state
        learner_status = LearnerEntryStatus(
            user_id=user_id,
            entry_type="word",
            entry_id=entry_id,
            status="learning",
        )
        learner_status_result = MagicMock()
        learner_status_result.scalar_one_or_none.return_value = learner_status
        mock_db.execute.side_effect = [locked_result, learner_status_result]
        review_service._build_detail_payload_for_word_id = AsyncMock(
            return_value={"entry_type": "word", "entry_id": str(entry_id), "display_text": "resilience"}
        )

        prompt_token = review_service._encode_prompt_token(
            {
                "prompt_id": str(uuid.uuid4()),
                "user_id": str(user_id),
                "queue_item_id": str(state_id),
                "prompt_type": ReviewService.PROMPT_TYPE_DEFINITION_TO_ENTRY,
                "review_mode": ReviewService.REVIEW_MODE_MCQ,
                "source_entry_type": "word",
                "source_entry_id": str(entry_id),
                "source_meaning_id": str(meaning_id),
                "correct_option_id": "A",
            }
        )

        updated = await review_service.submit_queue_review(
            item_id=state_id,
            quality=4,
            time_spent_ms=3000,
            user_id=user_id,
            selected_option_id="A",
            prompt_token=prompt_token,
            confirm=True,
        )

        assert updated.outcome == "correct_tested"
        assert updated.srs_bucket == "known"
        assert updated.interval_days is None
        assert updated.min_due_at_utc is None
        assert learner_status.status == "known"

    @pytest.mark.asyncio
    async def test_submit_queue_review_rejects_stale_prompt_submission(
        self, review_service, mock_db
    ):
        user_id = uuid.uuid4()
        state_id = uuid.uuid4()
        meaning_id = uuid.uuid4()
        entry_id = uuid.uuid4()
        entry_state = EntryReviewState(
            id=state_id,
            user_id=user_id,
            entry_type="word",
            entry_id=entry_id,
            target_type="meaning",
            target_id=meaning_id,
            stability=7,
            difficulty=0.4,
            srs_bucket="7d",
            cadence_step=1,
            last_submission_prompt_id=str(uuid.uuid4()),
        )
        entry_state.last_reviewed_at = datetime.now(timezone.utc)

        locked_result = MagicMock()
        locked_result.scalar_one_or_none.return_value = entry_state
        mock_db.execute.return_value = locked_result

        prompt_token = review_service._encode_prompt_token(
            {
                "prompt_id": str(uuid.uuid4()),
                "issued_at": (entry_state.last_reviewed_at - timedelta(minutes=5)).isoformat(),
                "user_id": str(user_id),
                "queue_item_id": str(state_id),
                "prompt_type": ReviewService.PROMPT_TYPE_DEFINITION_TO_ENTRY,
                "review_mode": ReviewService.REVIEW_MODE_MCQ,
                "source_entry_type": "word",
                "source_entry_id": str(entry_id),
                "source_meaning_id": str(meaning_id),
                "correct_option_id": "A",
            }
        )

        with pytest.raises(ValueError, match="Prompt submission is stale"):
            await review_service.submit_queue_review(
                item_id=state_id,
                quality=4,
                time_spent_ms=3000,
                user_id=user_id,
                selected_option_id="A",
                prompt_token=prompt_token,
                confirm=True,
            )


class TestPromptTokenHardening:
    def test_prompt_token_round_trips_without_exposing_answer_truth(self, review_service):
        payload = {
            "prompt_id": str(uuid.uuid4()),
            "user_id": str(uuid.uuid4()),
            "queue_item_id": str(uuid.uuid4()),
            "prompt_type": ReviewService.PROMPT_TYPE_TYPED_RECALL,
            "review_mode": ReviewService.REVIEW_MODE_MCQ,
            "input_mode": "typed",
            "source_entry_type": "word",
            "source_entry_id": str(uuid.uuid4()),
            "source_meaning_id": str(uuid.uuid4()),
            "correct_option_id": "A",
            "expected_input": "resilience",
        }

        token = review_service._encode_prompt_token(payload)

        assert "." not in token
        assert "resilience" not in token
        assert "correct_option_id" not in token
        assert review_service._decode_prompt_token(token)["expected_input"] == "resilience"

    def test_prompt_token_rejects_tampering(self, review_service):
        token = review_service._encode_prompt_token(
            {
                "prompt_id": str(uuid.uuid4()),
                "user_id": str(uuid.uuid4()),
                "queue_item_id": str(uuid.uuid4()),
                "prompt_type": ReviewService.PROMPT_TYPE_DEFINITION_TO_ENTRY,
                "review_mode": ReviewService.REVIEW_MODE_MCQ,
            }
        )

        midpoint = len(token) // 2
        replacement = "A" if token[midpoint] != "A" else "B"
        tampered = f"{token[:midpoint]}{replacement}{token[midpoint + 1:]}"
        assert review_service._decode_prompt_token(tampered) is None


class TestReviewGradeDerivation:
    def test_derive_review_grade_ignores_timing_for_objective_typed_prompts(self):
        prompt = {"prompt_type": ReviewService.PROMPT_TYPE_TYPED_RECALL}

        fast = ReviewService._derive_review_grade(
            outcome="correct_tested",
            prompt=prompt,
            quality=4,
            time_spent_ms=500,
        )
        slow = ReviewService._derive_review_grade(
            outcome="correct_tested",
            prompt=prompt,
            quality=4,
            time_spent_ms=12000,
        )

        assert fast == "good_pass"
        assert slow == "good_pass"

    def test_derive_review_grade_ignores_timing_for_mcq_prompts(self):
        prompt = {"prompt_type": ReviewService.PROMPT_TYPE_DEFINITION_TO_ENTRY}

        fast = ReviewService._derive_review_grade(
            outcome="correct_tested",
            prompt=prompt,
            quality=4,
            time_spent_ms=500,
        )
        slow = ReviewService._derive_review_grade(
            outcome="correct_tested",
            prompt=prompt,
            quality=4,
            time_spent_ms=12000,
        )

        assert fast == "good_pass"
        assert slow == "good_pass"
