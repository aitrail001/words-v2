import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.database import get_db
from app.core.redis import get_redis
from app.core.security import create_access_token, hash_password
from app.main import app
from app.models.import_job import ImportJob
from app.models.user import User


@pytest.fixture
def mock_db():
    session = AsyncMock()
    session.execute = AsyncMock()
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


def make_user(user_id: uuid.UUID) -> User:
    return User(
        id=user_id,
        email="test@example.com",
        password_hash=hash_password("password123"),
    )


class TestImportJobStatusEndpoints:
    @pytest.mark.asyncio
    async def test_get_import_job_not_found(self, client, mock_db):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        user = make_user(user_id)
        job_id = uuid.uuid4()

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        job_result = MagicMock()
        job_result.scalar_one_or_none.return_value = None
        mock_db.execute.side_effect = [user_result, job_result]

        response = await client.get(
            f"/api/import-jobs/{job_id}",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 404
        assert response.json()["detail"] == "Import job not found"

    @pytest.mark.asyncio
    async def test_get_import_job_events_stream_content_type(self, client, mock_db):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        user = make_user(user_id)
        job = ImportJob(
            id=uuid.uuid4(),
            user_id=user_id,
            import_source_id=uuid.uuid4(),
            source_filename="book.epub",
            source_hash="d" * 64,
            list_name="Book Import",
            status="processing",
            total_items=100,
            processed_items=20,
            matched_entry_count=20,
            created_at=datetime.now(timezone.utc),
        )

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        job_result = MagicMock()
        job_result.scalar_one_or_none.return_value = job
        mock_db.execute.side_effect = [user_result, job_result]

        response = await client.get(
            f"/api/import-jobs/{job.id}/events",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
