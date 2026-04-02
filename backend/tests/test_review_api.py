import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import Request
from httpx import ASGITransport, AsyncClient

from app.core.database import get_db
from app.core.redis import get_redis
from app.core.security import create_access_token
from app.main import app
from app.models.user import User
from app.models.meaning import Meaning
from app.models.review import ReviewSession, ReviewCard
from app.models.entry_review import EntryReviewState
from app.api.request_db_metrics import instrument_session_for_request, restore_session_after_request


@pytest.fixture
def mock_db():
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.add = MagicMock()
    session.info = {}
    return session


@pytest.fixture
def mock_redis():
    r = AsyncMock()
    r.ping = AsyncMock(return_value=True)
    return r


@pytest.fixture
async def client(mock_db, mock_redis):
    async def override_get_db(request: Request):
        instrument_session_for_request(request, mock_db)
        try:
            yield mock_db
        finally:
            restore_session_after_request(mock_db)

    def override_get_redis():
        return mock_redis

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_redis] = override_get_redis

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest.fixture
def auth_token():
    user_id = uuid.uuid4()
    token = create_access_token(subject=str(user_id))
    return token, user_id


def make_user(user_id):
    return User(
        id=user_id,
        email="test@example.com",
        password_hash="hashed",
    )


class TestCreateSession:
    @pytest.mark.asyncio
    async def test_create_session_success(self, client, mock_db, auth_token):
        token, user_id = auth_token
        user = make_user(user_id)

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        mock_db.execute.return_value = user_result

        response = await client.post(
            "/api/reviews/sessions",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 201
        data = response.json()
        assert "id" in data
        assert data["cards_reviewed"] == 0
        assert data["completed_at"] is None

    @pytest.mark.asyncio
    async def test_create_session_requires_auth(self, client):
        response = await client.post("/api/reviews/sessions")
        assert response.status_code == 401


class TestGetDueCards:
    @pytest.mark.asyncio
    async def test_get_due_cards_success(self, client, mock_db, auth_token):
        token, user_id = auth_token
        user = make_user(user_id)

        card = ReviewCard(
            id=uuid.uuid4(),
            session_id=uuid.uuid4(),
            word_id=uuid.uuid4(),
            meaning_id=uuid.uuid4(),
            card_type="flashcard",
            next_review=datetime.now(timezone.utc) - timedelta(days=1),
        )

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        cards_result = MagicMock()
        cards_result.scalars.return_value.all.return_value = [card]
        mock_db.execute.side_effect = [user_result, cards_result]

        response = await client.get(
            "/api/reviews/due",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["card_type"] == "flashcard"

    @pytest.mark.asyncio
    async def test_get_due_cards_requires_auth(self, client):
        response = await client.get("/api/reviews/due")
        assert response.status_code == 401


class TestSubmitReview:
    @pytest.mark.asyncio
    async def test_submit_review_success(self, client, mock_db, auth_token):
        token, user_id = auth_token
        user = make_user(user_id)
        card_id = uuid.uuid4()
        card = ReviewCard(
            id=card_id,
            session_id=uuid.uuid4(),
            word_id=uuid.uuid4(),
            meaning_id=uuid.uuid4(),
            card_type="flashcard",
            ease_factor=2.5,
            interval_days=1,
            repetitions=1,
        )

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        card_result = MagicMock()
        card_result.scalar_one_or_none.return_value = card
        mock_db.execute.side_effect = [user_result, card_result]

        response = await client.post(
            f"/api/reviews/cards/{card_id}/submit",
            json={"quality": 4, "time_spent_ms": 5000},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["quality_rating"] == 4
        assert data["time_spent_ms"] == 5000

    @pytest.mark.asyncio
    async def test_submit_review_requires_auth(self, client):
        card_id = uuid.uuid4()
        response = await client.post(
            f"/api/reviews/cards/{card_id}/submit",
            json={"quality": 4, "time_spent_ms": 5000},
        )
        assert response.status_code == 401


class TestQueueAdd:
    @pytest.mark.asyncio
    async def test_add_to_queue_success(self, client, mock_db, auth_token):
        token, user_id = auth_token
        user = make_user(user_id)
        meaning = Meaning(id=uuid.uuid4(), word_id=uuid.uuid4(), definition="Queue def")
        session = ReviewSession(id=uuid.uuid4(), user_id=user_id)

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        existing_item_result = MagicMock()
        existing_item_result.scalar_one_or_none.return_value = None
        meaning_result = MagicMock()
        meaning_result.scalar_one_or_none.return_value = meaning
        session_result = MagicMock()
        session_result.scalar_one_or_none.return_value = session
        mock_db.execute.side_effect = [
            user_result,
            existing_item_result,
            meaning_result,
            session_result,
        ]

        response = await client.post(
            "/api/reviews/queue",
            json={"meaning_id": str(meaning.id)},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["meaning_id"] == str(meaning.id)
        assert data["word_id"] in (None, str(meaning.word_id))
        assert data["card_type"] == "flashcard"

    @pytest.mark.asyncio
    async def test_add_to_queue_requires_auth(self, client):
        response = await client.post(
            "/api/reviews/queue",
            json={"meaning_id": str(uuid.uuid4())},
        )
        assert response.status_code == 401


class TestQueueDue:
    @pytest.mark.asyncio
    async def test_get_due_queue_items_success(self, client, mock_db, auth_token, monkeypatch):
        token, user_id = auth_token
        user = make_user(user_id)
        due_item = ReviewCard(
            id=uuid.uuid4(),
            session_id=uuid.uuid4(),
            word_id=uuid.uuid4(),
            meaning_id=uuid.uuid4(),
            card_type="flashcard",
            next_review=datetime.now(timezone.utc) - timedelta(hours=1),
        )

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        mock_db.execute.side_effect = [user_result]

        async def fake_get_due_queue_items(self, user_id, limit=20, **kwargs):
            return [
                {
                    "item": due_item,
                    "word": "ephemeral",
                    "definition": "lasting a short time",
                    "review_mode": "mcq",
                    "prompt": None,
                    "source_entry_type": "word",
                    "source_entry_id": str(due_item.word_id),
                    "detail": None,
                    "schedule_options": [],
                }
            ]

        monkeypatch.setattr(
            "app.api.reviews.ReviewService.get_due_queue_items",
            fake_get_due_queue_items,
        )

        response = await client.get(
            "/api/reviews/queue/due?limit=5",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["id"] == str(due_item.id)
        assert data[0]["word"] == "ephemeral"
        assert data[0]["definition"] == "lasting a short time"
        assert int(response.headers["X-Reviews-Query-Count"]) >= 1
        assert float(response.headers["X-Reviews-Query-Time-Ms"]) >= 0.0

    @pytest.mark.asyncio
    async def test_get_due_queue_items_returns_audio_prompt_with_playback_url(
        self, client, mock_db, auth_token, monkeypatch
    ):
        token, user_id = auth_token
        user = make_user(user_id)
        due_item = ReviewCard(
            id=uuid.uuid4(),
            session_id=uuid.uuid4(),
            word_id=uuid.uuid4(),
            meaning_id=uuid.uuid4(),
            card_type="flashcard",
            next_review=datetime.now(timezone.utc) - timedelta(hours=1),
        )

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        mock_db.execute.side_effect = [user_result]

        async def fake_get_due_queue_items(self, user_id, limit=20, **kwargs):
            return [
                {
                    "item": due_item,
                    "word": "bank",
                    "definition": "The land alongside a river.",
                    "review_mode": "mcq",
                    "prompt": {
                        "mode": "mcq",
                        "prompt_type": "audio_to_definition",
                        "prompt_token": "opaque-prompt-token",
                        "stem": "Listen, then choose the best matching definition.",
                        "question": "bank",
                        "options": [
                            {"option_id": "A", "label": "The land alongside a river."},
                            {"option_id": "B", "label": "A financial institution."},
                            {"option_id": "C", "label": "A mass of cloud."},
                            {"option_id": "D", "label": "A pile of snow."},
                        ],
                        "audio_state": "ready",
                        "audio": {
                            "preferred_playback_url": "/api/words/voice-assets/test-asset/content",
                            "preferred_locale": "us",
                            "locales": {
                                "us": {
                                    "playback_url": "/api/words/voice-assets/test-asset/content",
                                    "locale": "en_us",
                                    "relative_path": "word_bank/word/en_us/female-word.mp3",
                                }
                            },
                        },
                    },
                    "source_entry_type": "word",
                    "source_entry_id": str(due_item.word_id),
                    "detail": None,
                    "schedule_options": [],
                }
            ]

        monkeypatch.setattr(
            "app.api.reviews.ReviewService.get_due_queue_items",
            fake_get_due_queue_items,
        )

        response = await client.get(
            "/api/reviews/queue/due?limit=5",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert (
            data[0]["prompt"]["audio"]["preferred_playback_url"]
            == "/api/words/voice-assets/test-asset/content"
        )
        assert data[0]["prompt"]["prompt_token"] == "opaque-prompt-token"
        assert "is_correct" not in data[0]["prompt"]["options"][0]

    @pytest.mark.asyncio
    async def test_get_queue_stats_emits_query_metrics_headers(self, client, mock_db, auth_token):
        token, user_id = auth_token
        user = make_user(user_id)

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        total_result = MagicMock()
        total_result.scalar_one.return_value = 3
        due_result = MagicMock()
        due_result.scalar_one.return_value = 2
        aggregate_result = MagicMock()
        aggregate_result.one.return_value = (10, 7)
        mock_db.execute.side_effect = [user_result, total_result, due_result, aggregate_result]

        response = await client.get(
            "/api/reviews/queue/stats",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        assert int(response.headers["X-Reviews-Query-Count"]) >= 2
        assert float(response.headers["X-Reviews-Query-Time-Ms"]) >= 0.0

    @pytest.mark.asyncio
    async def test_get_due_queue_items_requires_auth(self, client):
        response = await client.get("/api/reviews/queue/due")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_get_queue_item_success(self, client, mock_db, auth_token, monkeypatch):
        token, user_id = auth_token
        user = make_user(user_id)
        item_id = uuid.uuid4()

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        mock_db.execute.side_effect = [user_result]

        async def fake_get_queue_item(self, user_id, item_id):
            item = ReviewCard(
                id=item_id,
                session_id=uuid.uuid4(),
                word_id=uuid.uuid4(),
                meaning_id=uuid.uuid4(),
                card_type="flashcard",
                next_review=datetime.now(timezone.utc) - timedelta(hours=1),
            )
            return {
                "item": item,
                "word": "ephemeral",
                "definition": "lasting a short time",
                "review_mode": "mcq",
                "prompt": {
                    "mode": "mcq",
                    "prompt_type": "definition_to_entry",
                    "prompt_token": "opaque-prompt-token",
                    "question": "lasting a short time",
                    "options": [
                        {"option_id": "A", "label": "ephemeral"},
                        {"option_id": "B", "label": "permanent"},
                    ],
                    "audio_state": "not_available",
                },
                "source_entry_type": "word",
                "source_entry_id": str(item.word_id),
                "detail": {
                    "entry_type": "word",
                    "entry_id": str(item.word_id),
                    "display_text": "ephemeral",
                    "meaning_count": 1,
                    "remembered_count": 0,
                    "compare_with": [],
                    "meanings": [],
                    "audio_state": "not_available",
                },
                "schedule_options": [],
            }

        monkeypatch.setattr(
            "app.api.reviews.ReviewService.get_queue_item",
            fake_get_queue_item,
        )

        response = await client.get(
            f"/api/reviews/queue/{item_id}",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(item_id)
        assert data["prompt"]["prompt_token"] == "opaque-prompt-token"
        assert data["detail"]["display_text"] == "ephemeral"


class TestQueueSubmit:
    @pytest.mark.asyncio
    async def test_submit_queue_review_success(self, client, mock_db, auth_token, monkeypatch):
        token, user_id = auth_token
        user = make_user(user_id)
        item = ReviewCard(
            id=uuid.uuid4(),
            session_id=uuid.uuid4(),
            word_id=uuid.uuid4(),
            meaning_id=uuid.uuid4(),
            card_type="flashcard",
            ease_factor=2.5,
            interval_days=1,
            repetitions=1,
        )
        item.review_count = 0
        item.correct_count = 0

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        mock_db.execute.side_effect = [user_result]

        async def fake_submit_queue_review(self, **kwargs):
            assert kwargs["audio_replay_count"] == 2
            assert kwargs["prompt_token"] == "opaque-prompt-token"
            item.quality_rating = 4
            item.time_spent_ms = 1234
            item.card_type = "listening"
            return item

        monkeypatch.setattr(
            "app.api.reviews.ReviewService.submit_queue_review",
            fake_submit_queue_review,
        )

        response = await client.post(
            f"/api/reviews/queue/{item.id}/submit",
            json={
                "quality": 4,
                "time_spent_ms": 1234,
                "audio_replay_count": 2,
                "card_type": "listening",
                "prompt_token": "opaque-prompt-token",
            },
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(item.id)
        assert data["quality_rating"] == 4
        assert data["time_spent_ms"] == 1234
        assert data["card_type"] == "listening"

    @pytest.mark.asyncio
    async def test_submit_queue_review_returns_404_when_item_not_found(
        self, client, mock_db, auth_token, monkeypatch
    ):
        token, user_id = auth_token
        user = make_user(user_id)
        item_id = uuid.uuid4()

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        mock_db.execute.side_effect = [user_result]

        async def fake_submit_queue_review(self, **kwargs):
            raise ValueError(f"Queue item {item_id} not found")

        monkeypatch.setattr(
            "app.api.reviews.ReviewService.submit_queue_review",
            fake_submit_queue_review,
        )

        response = await client.post(
            f"/api/reviews/queue/{item_id}/submit",
            json={"quality": 4, "time_spent_ms": 1234},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_submit_queue_review_serializes_state_backed_result(
        self, client, mock_db, auth_token, monkeypatch
    ):
        token, user_id = auth_token
        user = make_user(user_id)

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        mock_db.execute.side_effect = [user_result]

        state = EntryReviewState(
            id=uuid.uuid4(),
            user_id=user_id,
            entry_type="word",
            entry_id=uuid.uuid4(),
            stability=3,
            difficulty=0.5,
        )
        state.quality_rating = 4
        state.time_spent_ms = 1234
        state.interval_days = 3
        state.outcome = "correct_tested"
        state.needs_relearn = False
        state.recheck_planned = False
        state.detail = {
            "entry_type": "word",
            "entry_id": str(state.entry_id),
            "display_text": "resilience",
            "meaning_count": 1,
            "remembered_count": 0,
            "compare_with": [],
            "meanings": [],
            "audio_state": "not_available",
        }
        state.schedule_options = [
            {"value": "3d", "label": "In 3 days", "is_default": True},
        ]

        async def fake_submit_queue_review(self, **kwargs):
            return state

        monkeypatch.setattr(
            "app.api.reviews.ReviewService.submit_queue_review",
            fake_submit_queue_review,
        )

        response = await client.post(
            f"/api/reviews/queue/{state.id}/submit",
            json={"quality": 4, "time_spent_ms": 1234},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(state.id)
        assert data["meaning_id"] == ""
        assert data["outcome"] == "correct_tested"
        assert data["detail"]["display_text"] == "resilience"
        assert data["schedule_options"][0]["value"] == "3d"


class TestQueueStats:
    @pytest.mark.asyncio
    async def test_get_queue_stats_success(self, client, mock_db, auth_token):
        token, user_id = auth_token
        user = make_user(user_id)

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        total_result = MagicMock()
        total_result.scalar_one.return_value = 3
        due_result = MagicMock()
        due_result.scalar_one.return_value = 1
        aggregate_result = MagicMock()
        aggregate_result.one.return_value = (8, 6)
        mock_db.execute.side_effect = [user_result, total_result, due_result, aggregate_result]

        response = await client.get(
            "/api/reviews/queue/stats",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total_items"] == 3
        assert data["due_items"] == 1
        assert data["review_count"] == 8
        assert data["correct_count"] == 6
        assert data["accuracy"] == 0.75

    @pytest.mark.asyncio
    async def test_get_queue_stats_requires_auth(self, client):
        response = await client.get("/api/reviews/queue/stats")
        assert response.status_code == 401


class TestReviewAnalyticsSummary:
    @pytest.mark.asyncio
    async def test_get_review_analytics_summary_success(
        self, client, mock_db, auth_token, monkeypatch
    ):
        token, user_id = auth_token
        user = make_user(user_id)

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        mock_db.execute.side_effect = [user_result]

        async def fake_get_review_analytics_summary(self, user_id, days=30):
            return {
                "days": days,
                "total_events": 4,
                "audio_placeholder_events": 1,
                "total_audio_replays": 2,
                "audio_replay_counts": [{"value": "0", "count": 3}],
                "prompt_families": [{"value": "typed_recall", "count": 2}],
                "outcomes": [{"value": "correct_tested", "count": 3}],
                "response_input_modes": [{"value": "typed", "count": 2}],
            }

        monkeypatch.setattr(
            "app.api.reviews.ReviewService.get_review_analytics_summary",
            fake_get_review_analytics_summary,
        )

        response = await client.get(
            "/api/reviews/analytics/summary?days=14",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["days"] == 14
        assert data["total_events"] == 4
        assert data["audio_placeholder_events"] == 1
        assert data["total_audio_replays"] == 2
        assert data["prompt_families"][0]["value"] == "typed_recall"
        assert int(response.headers["X-Reviews-Query-Count"]) >= 1
        assert float(response.headers["X-Reviews-Query-Time-Ms"]) >= 0.0

    @pytest.mark.asyncio
    async def test_get_review_analytics_summary_requires_auth(self, client):
        response = await client.get("/api/reviews/analytics/summary")
        assert response.status_code == 401


class TestCompleteSession:
    @pytest.mark.asyncio
    async def test_complete_session_success(self, client, mock_db, auth_token):
        token, user_id = auth_token
        user = make_user(user_id)
        session_id = uuid.uuid4()
        session = ReviewSession(id=session_id, user_id=user_id)

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        session_result = MagicMock()
        session_result.scalar_one_or_none.return_value = session
        mock_db.execute.side_effect = [user_result, session_result]

        response = await client.post(
            f"/api/reviews/sessions/{session_id}/complete",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["completed_at"] is not None

    @pytest.mark.asyncio
    async def test_complete_session_requires_auth(self, client):
        session_id = uuid.uuid4()
        response = await client.post(f"/api/reviews/sessions/{session_id}/complete")
        assert response.status_code == 401
