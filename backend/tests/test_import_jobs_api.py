import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

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
    session.commit = AsyncMock()
    session.add = MagicMock()
    session.refresh = AsyncMock()
    return session


@pytest.fixture
def mock_redis():
    r = AsyncMock()
    r.ping = AsyncMock(return_value=True)
    r.get = AsyncMock(return_value=None)
    r.set = AsyncMock(return_value=True)
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


class TestCreateWordListImport:
    @pytest.mark.asyncio
    @patch("app.api.word_lists.process_word_list_import.delay")
    async def test_create_import_job_success(self, mock_delay, client, mock_db):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        user = make_user(user_id)

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        existing_result = MagicMock()
        existing_result.scalar_one_or_none.return_value = None
        mock_db.execute.side_effect = [user_result, existing_result]

        async def fake_refresh(obj):
            obj.id = uuid.uuid4()
            obj.created_at = datetime.now(timezone.utc)

        mock_db.refresh.side_effect = fake_refresh

        response = await client.post(
            "/api/word-lists/import",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("book.epub", b"fake epub content", "application/epub+zip")},
            data={"list_name": "Book Import"},
        )

        assert response.status_code == 201
        body = response.json()
        assert body["list_name"] == "Book Import"
        assert body["status"] == "queued"
        assert body["source_filename"] == "book.epub"
        mock_delay.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_import_job_rejects_non_epub(self, client, mock_db):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        user = make_user(user_id)

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        mock_db.execute.return_value = user_result

        response = await client.post(
            "/api/word-lists/import",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("notes.txt", b"not epub", "text/plain")},
        )

        assert response.status_code == 400
        assert response.json()["detail"] == "Only .epub files are supported"


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

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user

        job = ImportJob(
            id=uuid.uuid4(),
            user_id=user_id,
            source_filename="book.epub",
            source_hash="d" * 64,
            list_name="Book Import",
            status="processing",
            total_items=100,
            processed_items=20,
            created_at=datetime.now(timezone.utc),
        )
        job_result = MagicMock()
        job_result.scalar_one_or_none.return_value = job

        mock_db.execute.side_effect = [user_result, job_result]

        response = await client.get(
            f"/api/import-jobs/{job.id}/events",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
