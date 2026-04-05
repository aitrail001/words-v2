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


class TestQueueAdd:
    @pytest.mark.asyncio
    async def test_add_to_queue_success(self, client, mock_db, auth_token, monkeypatch):
        token, user_id = auth_token
        user = make_user(user_id)
        meaning = Meaning(id=uuid.uuid4(), word_id=uuid.uuid4(), definition="Queue def")
        state_id = uuid.uuid4()

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        mock_db.execute.side_effect = [user_result]

        async def fake_add_to_queue(self, user_id, meaning_id):
            return EntryReviewState(
                id=state_id,
                user_id=user_id,
                entry_type="word",
                entry_id=meaning.word_id,
                target_type="meaning",
                target_id=meaning_id,
            )

        monkeypatch.setattr(
            "app.api.reviews.ReviewService.add_to_queue",
            fake_add_to_queue,
        )

        response = await client.post(
            "/api/reviews/queue",
            json={"meaning_id": str(meaning.id)},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["id"] == str(state_id)
        assert data["target_type"] == "meaning"
        assert data["target_id"] == str(meaning.id)

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
        due_item = EntryReviewState(
            id=uuid.uuid4(),
            user_id=user_id,
            entry_type="word",
            entry_id=uuid.uuid4(),
            target_type="meaning",
            target_id=uuid.uuid4(),
        )
        due_item.word_id = due_item.entry_id
        due_item.meaning_id = due_item.target_id
        due_item.card_type = "flashcard"
        due_item.next_review = datetime.now(timezone.utc) - timedelta(hours=1)

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
    async def test_get_due_queue_items_uses_response_target_overrides_without_mutating_item(
        self, client, mock_db, auth_token, monkeypatch
    ):
        token, user_id = auth_token
        user = make_user(user_id)
        legacy_target_id = uuid.uuid4()
        first_meaning_id = uuid.uuid4()
        due_item = EntryReviewState(
            id=uuid.uuid4(),
            user_id=user_id,
            entry_type="word",
            entry_id=uuid.uuid4(),
            target_type="meaning",
            target_id=legacy_target_id,
        )
        due_item.word_id = due_item.entry_id

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
                    "target_type": "meaning",
                    "target_id": str(first_meaning_id),
                    "source_meaning_id": str(first_meaning_id),
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
        assert data[0]["target_id"] == str(first_meaning_id)
        assert data[0]["meaning_id"] == str(first_meaning_id)
        assert data[0]["source_meaning_id"] == str(first_meaning_id)
        assert due_item.target_id == legacy_target_id

    @pytest.mark.asyncio
    async def test_get_grouped_review_queue_success(self, client, mock_db, auth_token, monkeypatch):
        token, user_id = auth_token
        user = make_user(user_id)
        now = datetime(2026, 4, 5, 9, 0, tzinfo=timezone.utc)

        learning_state = EntryReviewState(
            id=uuid.uuid4(),
            user_id=user_id,
            entry_type="word",
            entry_id=uuid.uuid4(),
            target_type="meaning",
            target_id=uuid.uuid4(),
        )
        learning_state.next_due_at = now + timedelta(hours=1)
        learning_state.last_reviewed_at = now - timedelta(days=1)
        learning_state.srs_bucket = "1d"

        known_state = EntryReviewState(
            id=uuid.uuid4(),
            user_id=user_id,
            entry_type="word",
            entry_id=uuid.uuid4(),
            target_type="meaning",
            target_id=uuid.uuid4(),
        )
        known_state.next_due_at = now + timedelta(days=1)
        known_state.srs_bucket = "180d"

        to_learn_state = EntryReviewState(
            id=uuid.uuid4(),
            user_id=user_id,
            entry_type="word",
            entry_id=uuid.uuid4(),
            target_type="meaning",
            target_id=uuid.uuid4(),
        )
        to_learn_state.next_due_at = now + timedelta(days=2)
        to_learn_state.srs_bucket = "2d"

        phrase_state = EntryReviewState(
            id=uuid.uuid4(),
            user_id=user_id,
            entry_type="phrase",
            entry_id=uuid.uuid4(),
            target_type="phrase_sense",
            target_id=uuid.uuid4(),
        )
        phrase_state.next_due_at = now + timedelta(days=1)
        phrase_state.srs_bucket = "7d"

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        state_result = MagicMock()
        state_result.all.return_value = [
            (learning_state, "learning"),
            (known_state, "known"),
            (to_learn_state, "to_learn"),
            (phrase_state, "learning"),
        ]
        word_result = MagicMock()
        word_result.all.return_value = [
            (learning_state.entry_id, "persistence"),
            (known_state.entry_id, "resilience"),
            (to_learn_state.entry_id, "tranquil"),
        ]
        phrase_result = MagicMock()
        phrase_result.all.return_value = [(phrase_state.entry_id, "break down")]
        mock_db.execute.side_effect = [user_result, state_result, word_result, phrase_result]

        class FrozenDateTime(datetime):
            @classmethod
            def now(cls, tz=None):
                return now if tz is None else now.astimezone(tz)

        monkeypatch.setattr("app.api.reviews.datetime", FrozenDateTime)

        response = await client.get(
            "/api/reviews/queue/grouped",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total_count"] == 2
        assert data["groups"][0]["bucket"] == "1d"
        assert data["groups"][0]["items"][0]["text"] == "persistence"
        assert data["groups"][0]["items"][0]["status"] == "learning"
        assert data["groups"][0]["items"][0]["bucket"] == "1d"
        assert "target_type" not in data["groups"][0]["items"][0]
        assert len(data["groups"]) == 2
        assert data["groups"][1]["bucket"] == "7d"
        assert data["groups"][1]["items"][0]["entry_type"] == "phrase"
        assert data["groups"][1]["items"][0]["text"] == "break down"

    @pytest.mark.asyncio
    async def test_get_grouped_review_queue_by_due_success(
        self, client, mock_db, auth_token, monkeypatch
    ):
        token, user_id = auth_token
        user = make_user(user_id)

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        mock_db.execute.side_effect = [user_result]

        async def fake_get_grouped_review_queue_by_due(
            self, *, user_id, now, include_debug_fields=False
        ):
            assert user_id == user.id
            assert isinstance(now, datetime)
            assert include_debug_fields is False
            return {
                "generated_at": "2026-04-05T09:00:00+00:00",
                "total_count": 2,
                "groups": [
                    {
                        "group_key": "due_now",
                        "label": "Due now",
                        "due_in_days": 0,
                        "count": 1,
                        "items": [
                            {
                                "queue_item_id": "queue-1",
                                "entry_id": "word-1",
                                "entry_type": "word",
                                "text": "persistence",
                                "status": "learning",
                                "next_review_at": None,
                                "last_reviewed_at": None,
                                "bucket": "1d",
                                "success_streak": 0,
                                "lapse_count": 0,
                                "times_remembered": 0,
                                "exposure_count": 0,
                                "history": [],
                            }
                        ],
                    }
                ],
            }

        monkeypatch.setattr(
            "app.api.reviews.ReviewService.get_grouped_review_queue_by_due",
            fake_get_grouped_review_queue_by_due,
            raising=False,
        )

        response = await client.get(
            "/api/reviews/queue/grouped/by-due",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total_count"] == 2
        assert data["groups"][0]["group_key"] == "due_now"
        assert data["groups"][0]["label"] == "Due now"
        assert data["groups"][0]["items"][0]["bucket"] == "1d"

    @pytest.mark.asyncio
    async def test_get_grouped_review_queue_admin_supports_effective_time_override(
        self, client, mock_db
    ):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        admin_user = User(
            id=user_id,
            email="admin@example.com",
            password_hash="hashed",
            role="admin",
        )

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = admin_user
        future_state = EntryReviewState(
            id=uuid.uuid4(),
            user_id=user_id,
            entry_type="word",
            entry_id=uuid.uuid4(),
            target_type="meaning",
            target_id=uuid.uuid4(),
        )
        future_state.next_due_at = datetime(2026, 10, 5, 9, 0, tzinfo=timezone.utc)
        future_state.srs_bucket = "180d"
        state_result = MagicMock()
        state_result.all.return_value = [(future_state, "learning")]
        word_result = MagicMock()
        word_result.all.return_value = [(future_state.entry_id, "candidate")]
        mock_db.execute.side_effect = [user_result, state_result, word_result]

        response = await client.get(
            "/api/reviews/admin/queue/grouped?effective_now=2026-10-05T09:00:00%2B00:00",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["debug"]["effective_now"] == "2026-10-05T09:00:00+00:00"
        assert data["groups"][0]["bucket"] == "180d"
        assert data["groups"][0]["items"][0]["text"] == "candidate"
        assert data["groups"][0]["items"][0]["target_type"] == "meaning"

    @pytest.mark.asyncio
    async def test_get_grouped_review_queue_admin_normalizes_naive_effective_time(
        self, client, mock_db
    ):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        admin_user = User(
            id=user_id,
            email="admin@example.com",
            password_hash="hashed",
            role="admin",
        )

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = admin_user
        state_result = MagicMock()
        state_result.all.return_value = []
        mock_db.execute.side_effect = [user_result, state_result]

        response = await client.get(
            "/api/reviews/admin/queue/grouped?effective_now=2026-10-05T09:00:00",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["debug"]["effective_now"] == "2026-10-05T09:00:00+00:00"

    @pytest.mark.asyncio
    async def test_get_grouped_review_queue_admin_requires_admin(
        self, client, mock_db, auth_token, monkeypatch
    ):
        token, user_id = auth_token
        user = make_user(user_id)

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        mock_db.execute.side_effect = [user_result]

        response = await client.get(
            "/api/reviews/admin/queue/grouped",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_get_review_queue_summary_success(self, client, mock_db, auth_token, monkeypatch):
        token, user_id = auth_token
        user = make_user(user_id)

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        mock_db.execute.side_effect = [user_result]

        async def fake_get_grouped_review_queue_summary(self, *, user_id, now):
            assert user_id == user.id
            assert isinstance(now, datetime)
            return {
                "generated_at": "2026-04-05T09:00:00+00:00",
                "total_count": 3,
                "groups": [
                    {"bucket": "overdue", "count": 2, "has_due_now": True},
                    {"bucket": "tomorrow", "count": 1, "has_due_now": False},
                ],
            }

        monkeypatch.setattr(
            "app.api.reviews.ReviewService.get_grouped_review_queue_summary",
            fake_get_grouped_review_queue_summary,
            raising=False,
        )

        response = await client.get(
            "/api/reviews/queue/summary",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total_count"] == 3
        assert data["groups"] == [
            {"bucket": "overdue", "count": 2, "has_due_now": True},
            {"bucket": "tomorrow", "count": 1, "has_due_now": False},
        ]

    @pytest.mark.asyncio
    async def test_get_admin_review_queue_summary_applies_effective_now(
        self, client, mock_db, monkeypatch
    ):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        admin_user = User(
            id=user_id,
            email="admin@example.com",
            password_hash="hashed",
            role="admin",
        )

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = admin_user
        mock_db.execute.side_effect = [user_result]

        async def fake_get_grouped_review_queue_summary(self, *, user_id, now):
            assert user_id == admin_user.id
            assert now == datetime(2026, 10, 5, 9, 0, tzinfo=timezone.utc)
            return {
                "generated_at": "2026-10-05T09:00:00+00:00",
                "total_count": 1,
                "groups": [
                    {"bucket": "due_now", "count": 1, "has_due_now": True},
                ],
            }

        monkeypatch.setattr(
            "app.api.reviews.ReviewService.get_grouped_review_queue_summary",
            fake_get_grouped_review_queue_summary,
            raising=False,
        )

        response = await client.get(
            "/api/reviews/admin/queue/summary?effective_now=2026-10-05T09:00:00%2B00:00",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["debug"]["effective_now"] == "2026-10-05T09:00:00+00:00"
        assert data["total_count"] == 1
        assert data["groups"] == [{"bucket": "due_now", "count": 1, "has_due_now": True}]

    @pytest.mark.asyncio
    async def test_get_review_queue_bucket_detail_supports_sort_and_order(
        self, client, mock_db, auth_token, monkeypatch
    ):
        token, user_id = auth_token
        user = make_user(user_id)

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        mock_db.execute.side_effect = [user_result]

        async def fake_get_grouped_review_queue_bucket_detail(
            self,
            *,
            user_id,
            now,
            bucket,
            sort,
            order,
            include_debug_fields=False,
        ):
            assert user_id == user.id
            assert isinstance(now, datetime)
            assert bucket == "later_today"
            assert sort == "text"
            assert order == "desc"
            assert include_debug_fields is False
            return {
                "generated_at": "2026-04-05T09:00:00+00:00",
                "bucket": "later_today",
                "count": 2,
                "sort": "text",
                "order": "desc",
                "items": [
                    {
                        "queue_item_id": str(uuid.uuid4()),
                        "entry_id": str(uuid.uuid4()),
                        "entry_type": "word",
                        "text": "zeta",
                        "status": "learning",
                        "next_review_at": "2026-04-05T12:00:00+00:00",
                        "last_reviewed_at": "2026-04-04T09:00:00+00:00",
                    },
                    {
                        "queue_item_id": str(uuid.uuid4()),
                        "entry_id": str(uuid.uuid4()),
                        "entry_type": "word",
                        "text": "alpha",
                        "status": "learning",
                        "next_review_at": "2026-04-05T10:00:00+00:00",
                        "last_reviewed_at": None,
                    },
                ],
            }

        monkeypatch.setattr(
            "app.api.reviews.ReviewService.get_grouped_review_queue_bucket_detail",
            fake_get_grouped_review_queue_bucket_detail,
            raising=False,
        )

        response = await client.get(
            "/api/reviews/queue/buckets/later_today?sort=text&order=desc",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["bucket"] == "later_today"
        assert data["sort"] == "text"
        assert data["order"] == "desc"
        assert [item["text"] for item in data["items"]] == ["zeta", "alpha"]

    @pytest.mark.asyncio
    async def test_get_admin_review_queue_bucket_detail_applies_effective_now(
        self, client, mock_db, monkeypatch
    ):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        admin_user = User(
            id=user_id,
            email="admin@example.com",
            password_hash="hashed",
            role="admin",
        )

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = admin_user
        mock_db.execute.side_effect = [user_result]

        async def fake_get_grouped_review_queue_bucket_detail(
            self,
            *,
            user_id,
            now,
            bucket,
            sort,
            order,
            include_debug_fields=False,
        ):
            assert user_id == admin_user.id
            assert now == datetime(2026, 10, 5, 9, 0, tzinfo=timezone.utc)
            assert bucket == "due_now"
            assert sort == "next_review_at"
            assert order == "asc"
            assert include_debug_fields is True
            return {
                "generated_at": "2026-10-05T09:00:00+00:00",
                "bucket": "due_now",
                "count": 1,
                "sort": "next_review_at",
                "order": "asc",
                "items": [
                    {
                        "queue_item_id": str(uuid.uuid4()),
                        "entry_id": str(uuid.uuid4()),
                        "entry_type": "word",
                        "text": "candidate",
                        "status": "learning",
                        "next_review_at": "2026-10-05T09:00:00+00:00",
                        "last_reviewed_at": "2026-10-04T09:00:00+00:00",
                        "target_type": "meaning",
                        "target_id": str(uuid.uuid4()),
                        "recheck_due_at": None,
                        "next_due_at": "2026-10-05T09:00:00+00:00",
                        "last_outcome": "correct_tested",
                        "relearning": False,
                        "relearning_trigger": None,
                    }
                ],
            }

        monkeypatch.setattr(
            "app.api.reviews.ReviewService.get_grouped_review_queue_bucket_detail",
            fake_get_grouped_review_queue_bucket_detail,
            raising=False,
        )

        response = await client.get(
            "/api/reviews/admin/queue/buckets/due_now?effective_now=2026-10-05T09:00:00%2B00:00",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["debug"]["effective_now"] == "2026-10-05T09:00:00+00:00"
        assert data["bucket"] == "due_now"
        assert data["items"][0]["target_type"] == "meaning"


class TestQueueScheduleUpdate:
    @pytest.mark.asyncio
    async def test_update_queue_schedule_success(self, client, mock_db, auth_token, monkeypatch):
        token, user_id = auth_token
        user = make_user(user_id)

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        mock_db.execute.side_effect = [user_result]

        async def fake_update_queue_item_schedule(self, *, user_id, item_id, schedule_override):
            assert schedule_override == "7d"
            return {
                "queue_item_id": str(item_id),
                "next_review_at": "2026-04-11T00:00:00+00:00",
                "current_schedule_value": "7d",
                "current_schedule_label": "In a week",
                "current_schedule_source": "scheduled_timestamp",
                "schedule_options": [
                    {"value": "1d", "label": "Tomorrow", "is_default": True},
                    {"value": "7d", "label": "In a week", "is_default": False},
                ],
            }

        monkeypatch.setattr(
            "app.api.reviews.ReviewService.update_queue_item_schedule",
            fake_update_queue_item_schedule,
        )

        item_id = uuid.uuid4()
        response = await client.put(
            f"/api/reviews/queue/{item_id}/schedule",
            json={"schedule_override": "7d"},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["queue_item_id"] == str(item_id)
        assert data["current_schedule_value"] == "7d"
        assert data["current_schedule_label"] == "In a week"
        assert data["current_schedule_source"] == "scheduled_timestamp"

    @pytest.mark.asyncio
    async def test_update_queue_schedule_rejects_invalid_override(self, client, mock_db, auth_token):
        token, user_id = auth_token
        user = make_user(user_id)

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        mock_db.execute.side_effect = [user_result]

        response = await client.put(
            f"/api/reviews/queue/{uuid.uuid4()}/schedule",
            json={"schedule_override": "bad-value"},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_get_due_queue_items_returns_audio_prompt_with_playback_url(
        self, client, mock_db, auth_token, monkeypatch
    ):
        token, user_id = auth_token
        user = make_user(user_id)
        due_item = EntryReviewState(
            id=uuid.uuid4(),
            user_id=user_id,
            entry_type="word",
            entry_id=uuid.uuid4(),
            target_type="meaning",
            target_id=uuid.uuid4(),
        )
        due_item.word_id = due_item.entry_id
        due_item.meaning_id = due_item.target_id
        due_item.card_type = "flashcard"
        due_item.next_review = datetime.now(timezone.utc) - timedelta(hours=1)

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
        mock_db.execute.side_effect = [user_result]

        async def fake_get_queue_stats(self, user_id):
            assert user_id == user.id
            return {
                "total_items": 3,
                "due_items": 2,
                "review_count": 10,
                "correct_count": 7,
                "accuracy": 0.7,
            }

        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.setattr(
            "app.api.reviews.ReviewService.get_queue_stats",
            fake_get_queue_stats,
            raising=False,
        )

        try:
            response = await client.get(
                "/api/reviews/queue/stats",
                headers={"Authorization": f"Bearer {token}"},
            )
        finally:
            monkeypatch.undo()

        assert response.status_code == 200
        assert int(response.headers["X-Reviews-Query-Count"]) >= 1
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
            item = EntryReviewState(
                id=item_id,
                user_id=user_id,
                entry_type="word",
                entry_id=uuid.uuid4(),
                target_type="meaning",
                target_id=uuid.uuid4(),
            )
            item.word_id = item.entry_id
            item.meaning_id = item.target_id
            item.card_type = "flashcard"
            item.next_review = datetime.now(timezone.utc) - timedelta(hours=1)
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
        item = EntryReviewState(
            id=uuid.uuid4(),
            user_id=user_id,
            entry_type="word",
            entry_id=uuid.uuid4(),
            target_type="meaning",
            target_id=uuid.uuid4(),
            stability=1,
            difficulty=0.5,
        )
        item.word_id = item.entry_id
        item.meaning_id = item.target_id
        item.card_type = "flashcard"
        item.interval_days = 1

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
    async def test_submit_queue_review_returns_400_for_stale_prompt_submission(
        self, client, mock_db, auth_token, monkeypatch
    ):
        token, user_id = auth_token
        user = make_user(user_id)
        item_id = uuid.uuid4()

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        mock_db.execute.side_effect = [user_result]

        async def fake_submit_queue_review(self, **kwargs):
            raise ValueError("Prompt submission is stale")

        monkeypatch.setattr(
            "app.api.reviews.ReviewService.submit_queue_review",
            fake_submit_queue_review,
        )

        response = await client.post(
            f"/api/reviews/queue/{item_id}/submit",
            json={"quality": 4, "time_spent_ms": 1234},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 400
        assert "stale" in response.json()["detail"].lower()

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

    @pytest.mark.asyncio
    async def test_submit_queue_review_serializes_lookup_result(
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
        state.quality_rating = 1
        state.time_spent_ms = 900
        state.interval_days = 1
        state.outcome = "lookup"
        state.needs_relearn = True
        state.recheck_planned = True
        state.detail = {
            "entry_type": "word",
            "entry_id": str(state.entry_id),
            "display_text": "barely",
            "primary_definition": "Only just, by a very small margin.",
            "meaning_count": 1,
            "remembered_count": 0,
            "compare_with": [],
            "meanings": [],
            "audio_state": "not_available",
        }
        state.schedule_options = []

        async def fake_submit_queue_review(self, **kwargs):
            return state

        monkeypatch.setattr(
            "app.api.reviews.ReviewService.submit_queue_review",
            fake_submit_queue_review,
        )

        response = await client.post(
            f"/api/reviews/queue/{state.id}/submit",
            json={"quality": 1, "time_spent_ms": 900, "outcome": "lookup"},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(state.id)
        assert data["outcome"] == "lookup"
        assert data["needs_relearn"] is True
        assert data["recheck_planned"] is True
        assert data["detail"]["display_text"] == "barely"
        assert data["schedule_options"] == []


class TestQueueStats:
    @pytest.mark.asyncio
    async def test_get_queue_stats_success(self, client, mock_db, auth_token):
        token, user_id = auth_token
        user = make_user(user_id)

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        mock_db.execute.side_effect = [user_result]

        async def fake_get_queue_stats(self, user_id):
            assert user_id == user.id
            return {
                "total_items": 3,
                "due_items": 1,
                "review_count": 8,
                "correct_count": 6,
                "accuracy": 0.75,
            }

        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.setattr(
            "app.api.reviews.ReviewService.get_queue_stats",
            fake_get_queue_stats,
            raising=False,
        )

        try:
            response = await client.get(
                "/api/reviews/queue/stats",
                headers={"Authorization": f"Bearer {token}"},
            )
        finally:
            monkeypatch.undo()

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
