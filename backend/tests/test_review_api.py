import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.database import get_db
from app.core.redis import get_redis
from app.core.security import create_access_token
from app.main import app
from app.models.user import User
from app.models.review import ReviewSession, ReviewCard


@pytest.fixture
def mock_db():
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.add = MagicMock()
    return session


@pytest.fixture
def mock_redis():
    r = AsyncMock()
    r.ping = AsyncMock(return_value=True)
    return r


@pytest.fixture
async def client(mock_db, mock_redis):
    async def override_get_db():
        yield mock_db

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
