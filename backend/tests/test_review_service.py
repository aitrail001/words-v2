import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.review import ReviewService
from app.models.review import ReviewSession, ReviewCard
from app.models.entry_review import EntryReviewState
from app.models.word import Word
from app.models.meaning import Meaning
from app.spaced_repetition import calculate_next_review


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
        state.next_due_at = datetime.now(timezone.utc) - timedelta(minutes=5)
        word = Word(id=word_id, word="jump the gun", language="en")
        meanings = [
            Meaning(id=meaning_id, word_id=word_id, definition="To do something too soon."),
            Meaning(id=uuid.uuid4(), word_id=word_id, definition="To act before the proper time."),
        ]

        state_result = MagicMock()
        state_result.scalars.return_value.all.return_value = [state]
        word_result = MagicMock()
        word_result.scalar_one_or_none.return_value = word
        meanings_result = MagicMock()
        meanings_result.scalars.return_value.all.return_value = meanings
        sentence_result = MagicMock()
        sentence_result.scalar_one_or_none.return_value = "They jumped the gun and announced it early."
        distractor_result = MagicMock()
        distractor_result.scalars.return_value.all.return_value = ["cut corners", "miss the boat", "take over"]
        history_count_result = MagicMock()
        history_count_result.scalar_one.return_value = 3
        mock_db.execute.side_effect = [
            state_result,
            word_result,
            meanings_result,
            sentence_result,
            distractor_result,
            sentence_result,
            sentence_result,
            history_count_result,
        ]

        due_items = await review_service.get_due_queue_items(user_id=user_id, limit=10)

        assert len(due_items) == 1
        assert due_items[0]["source_entry_id"] == str(word_id)
        assert due_items[0]["detail"]["display_text"] == "jump the gun"
        assert due_items[0]["prompt"]["prompt_type"] in {
            "definition_to_entry",
            "entry_to_definition",
            "audio_to_definition",
            "sentence_gap",
            "collocation_check",
            "situation_matching",
            "meaning_discrimination",
        }


class TestHistoryLookup:
    @pytest.mark.asyncio
    async def test_get_latest_history_for_meaning_limits_to_first_row(self, review_service, mock_db):
        user_id = uuid.uuid4()
        meaning_id = uuid.uuid4()
        latest_history = MagicMock()
        result = MagicMock()
        result.scalars.return_value.first.return_value = latest_history
        mock_db.execute.return_value = result

        history = await review_service._get_latest_history_for_meaning(user_id, meaning_id)

        assert history is latest_history
        result.scalars.return_value.first.assert_called_once()
        executed_query = mock_db.execute.call_args.args[0]
        assert executed_query._limit_clause is not None


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
        word_lookup_result = MagicMock()
        word_lookup_result.scalar_one_or_none.return_value = Word(id=word_id, word="barely", language="en")
        meanings_result = MagicMock()
        meanings_result.scalars.return_value.all.return_value = [
            Meaning(id=uuid.uuid4(), word_id=word_id, definition="Only just, by a very small margin.")
        ]
        sentence_result = MagicMock()
        sentence_result.scalar_one_or_none.return_value = "He barely made it through the door."
        history_count_result = MagicMock()
        history_count_result.scalar_one.return_value = 4
        mock_db.execute.side_effect = [
            state_lookup_result,
            word_lookup_result,
            meanings_result,
            sentence_result,
            history_count_result,
        ]

        updated = await review_service.submit_queue_review(
            item_id=state.id,
            quality=1,
            time_spent_ms=1500,
            user_id=user_id,
            outcome="wrong",
            prompt={"prompt_type": "sentence_gap"},
        )

        assert updated.outcome == "wrong"
        assert updated.relearning is True
        assert updated.relearning_trigger == "wrong"
        assert updated.recheck_due_at is not None
        assert updated.needs_relearn is True
        assert updated.recheck_planned is True
        mock_db.commit.assert_awaited_once()

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
        word_lookup_result = MagicMock()
        word_lookup_result.scalar_one_or_none.return_value = Word(id=word_id, word="resilience", language="en")
        meanings_result = MagicMock()
        meanings_result.scalars.return_value.all.return_value = [
            Meaning(id=uuid.uuid4(), word_id=word_id, definition="The capacity to recover quickly from difficulties.")
        ]
        sentence_result = MagicMock()
        sentence_result.scalar_one_or_none.return_value = "Resilience helps teams adapt to change."
        history_count_result = MagicMock()
        history_count_result.scalar_one.return_value = 2
        mock_db.execute.side_effect = [
            state_lookup_result,
            word_lookup_result,
            meanings_result,
            sentence_result,
            history_count_result,
        ]

        await review_service.submit_queue_review(
            item_id=state.id,
            quality=4,
            time_spent_ms=1200,
            user_id=user_id,
            prompt={
                "prompt_type": "typed_recall",
                "input_mode": "typed",
                "audio_state": "not_available",
            },
            typed_answer="resilience",
        )

        event = next(
            call.args[0]
            for call in mock_db.add.call_args_list
            if call.args and hasattr(call.args[0], "prompt_type")
        )
        assert event.prompt_family == "typed_recall"
        assert event.response_input_mode == "typed"
        assert event.response_value == "resilience"
        assert event.used_audio_placeholder is False


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
        mock_db.execute.side_effect = [
            total_result,
            placeholder_result,
            prompt_family_result,
            outcome_result,
            input_mode_result,
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


class TestPromptFamilies:
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
    async def test_build_card_prompt_supports_meaning_discrimination(
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
        )

        assert prompt["prompt_type"] == "meaning_discrimination"
        assert prompt["question"] == "rocky"
        assert len(prompt["options"]) == 4

    @pytest.mark.asyncio
    async def test_build_card_prompt_supports_typed_recall(
        self, review_service, mock_db
    ):
        prompt = await review_service._build_card_prompt(
            review_mode=ReviewService.REVIEW_MODE_MCQ,
            source_text="resilience",
            definition="The capacity to recover quickly from difficulties.",
            sentence=None,
            is_phrase_entry=False,
            distractor_seed="seed",
            meaning_id=uuid.uuid4(),
            index=1,
            alternative_definitions=[
                "The capacity to recover quickly from difficulties.",
                "A tendency to overreact.",
                "A refusal to listen.",
            ],
        )

        assert prompt["prompt_type"] == "typed_recall"
        assert prompt["options"] is None
        assert prompt["expected_input"] == "resilience"
        assert "type the word or phrase" in prompt["stem"].lower()

    @pytest.mark.asyncio
    async def test_build_card_prompt_supports_speak_recall_placeholder(
        self, review_service, mock_db
    ):
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
        )

        assert prompt["prompt_type"] == "speak_recall"
        assert prompt["input_mode"] == "speech_placeholder"
        assert prompt["voice_placeholder_text"] is not None
        assert prompt["audio_state"] == "placeholder"

    @pytest.mark.asyncio
    async def test_build_card_prompt_prefers_same_day_definition_distractors_before_frequency_fallback(
        self, review_service, mock_db, monkeypatch
    ):
        user_id = uuid.uuid4()
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
        assert prompt["audio_state"] == "ready"
        review_service._fetch_same_day_definition_distractors.assert_awaited_once()
        review_service._fetch_adjacent_definition_distractors.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_build_card_prompt_uses_adjacent_frequency_distractors_when_same_day_pool_is_small(
        self, review_service, mock_db, monkeypatch
    ):
        user_id = uuid.uuid4()
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
    async def test_build_card_prompt_supports_collocation_check(
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
        )

        assert prompt["prompt_type"] == "collocation_check"
        assert prompt["sentence_masked"] is not None
        assert "common expression" in prompt["stem"].lower()
        assert len(prompt["options"]) == 4

    @pytest.mark.asyncio
    async def test_build_card_prompt_supports_situation_matching(
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
        )

        assert prompt["prompt_type"] == "situation_matching"
        assert "situation" in prompt["stem"].lower()
        assert prompt["question"] == "Resilience helps teams adapt after major setbacks."
        assert len(prompt["options"]) == 4

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


class TestLearningStart:
    @pytest.mark.asyncio
    async def test_start_learning_entry_for_phrase_uses_entry_state_as_queue_item_id(
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
            stability=3,
            difficulty=0.5,
        )
        sense = MagicMock()
        sense.id = sense_id
        sense.definition = "To do something too soon."
        sense.order_index = 0

        phrase_result = MagicMock()
        phrase_result.scalar_one_or_none.return_value = phrase
        senses_result = MagicMock()
        senses_result.scalars.return_value.all.return_value = [sense]

        review_service._ensure_entry_review_state = AsyncMock(return_value=state)
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
        review_service._fetch_first_sense_sentence = AsyncMock(
            return_value="They jumped the gun and announced it early."
        )
        review_service._build_card_prompt = AsyncMock(
            return_value={
                "mode": "mcq",
                "prompt_type": "definition_to_entry",
                "question": "To do something too soon.",
                "options": [],
            }
        )
        mock_db.execute.side_effect = [phrase_result, senses_result]

        payload = await review_service.start_learning_entry(
            user_id=user_id,
            entry_type="phrase",
            entry_id=phrase_id,
        )

        assert payload["queue_item_ids"] == [str(state_id)]
        assert payload["cards"][0]["queue_item_id"] == str(state_id)


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
