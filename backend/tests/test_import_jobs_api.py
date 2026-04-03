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
from app.models.import_source import ImportSource
from app.models.user import User


@pytest.fixture
def mock_db():
    session = AsyncMock()
    session.execute = AsyncMock()
    session.delete = AsyncMock()
    session.commit = AsyncMock()
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
    async def test_list_import_jobs_returns_most_recent_first(self, client, mock_db):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        user = make_user(user_id)
        older_job = ImportJob(
            id=uuid.uuid4(),
            user_id=user_id,
            import_source_id=uuid.uuid4(),
            source_filename="older.epub",
            source_hash="a" * 64,
            list_name="Older Import",
            status="completed",
            created_at=datetime(2026, 4, 2, tzinfo=timezone.utc),
        )
        newer_job = ImportJob(
            id=uuid.uuid4(),
            user_id=user_id,
            import_source_id=uuid.uuid4(),
            source_filename="newer.epub",
            source_hash="b" * 64,
            list_name="Newer Import",
            status="processing",
            created_at=datetime(2026, 4, 3, tzinfo=timezone.utc),
        )

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        jobs_result = MagicMock()
        jobs_result.scalars.return_value.all.return_value = [newer_job, older_job]
        sources_result = MagicMock()
        sources_result.scalars.return_value.all.return_value = [
            ImportSource(id=newer_job.import_source_id, source_type="epub", source_hash_sha256="b" * 64, pipeline_version="v1", lexicon_version="v1"),
            ImportSource(id=older_job.import_source_id, source_type="epub", source_hash_sha256="a" * 64, pipeline_version="v1", lexicon_version="v1"),
        ]
        counts_result = MagicMock()
        counts_result.all.return_value = []
        mock_db.execute.side_effect = [user_result, jobs_result, sources_result, counts_result]

        response = await client.get(
            "/api/import-jobs",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        assert [row["id"] for row in response.json()] == [str(newer_job.id), str(older_job.id)]

    @pytest.mark.asyncio
    async def test_list_import_jobs_filters_active_jobs(self, client, mock_db):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        user = make_user(user_id)
        active_job = ImportJob(
            id=uuid.uuid4(),
            user_id=user_id,
            import_source_id=uuid.uuid4(),
            source_filename="active.epub",
            source_hash="a" * 64,
            list_name="Active Import",
            status="processing",
            created_at=datetime.now(timezone.utc),
        )

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        jobs_result = MagicMock()
        jobs_result.scalars.return_value.all.return_value = [active_job]
        sources_result = MagicMock()
        sources_result.scalars.return_value.all.return_value = [
            ImportSource(id=active_job.import_source_id, source_type="epub", source_hash_sha256="a" * 64, pipeline_version="v1", lexicon_version="v1"),
        ]
        counts_result = MagicMock()
        counts_result.all.return_value = []
        mock_db.execute.side_effect = [user_result, jobs_result, sources_result, counts_result]

        response = await client.get(
            "/api/import-jobs?status_view=active",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        assert response.json()[0]["status"] == "processing"

    @pytest.mark.asyncio
    async def test_list_import_jobs_filters_history_jobs(self, client, mock_db):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        user = make_user(user_id)
        history_job = ImportJob(
            id=uuid.uuid4(),
            user_id=user_id,
            import_source_id=uuid.uuid4(),
            source_filename="done.epub",
            source_hash="b" * 64,
            list_name="Done Import",
            status="completed",
            completed_at=datetime.now(timezone.utc),
            created_at=datetime.now(timezone.utc),
        )

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        jobs_result = MagicMock()
        jobs_result.scalars.return_value.all.return_value = [history_job]
        sources_result = MagicMock()
        sources_result.scalars.return_value.all.return_value = [
            ImportSource(id=history_job.import_source_id, source_type="epub", source_hash_sha256="b" * 64, pipeline_version="v1", lexicon_version="v1"),
        ]
        counts_result = MagicMock()
        counts_result.all.return_value = []
        mock_db.execute.side_effect = [user_result, jobs_result, sources_result, counts_result]

        response = await client.get(
            "/api/import-jobs?status_view=history",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        assert response.json()[0]["status"] == "completed"

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
    async def test_delete_import_job_removes_terminal_user_record_only(self, client, mock_db):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        user = make_user(user_id)
        job = ImportJob(
            id=uuid.uuid4(),
            user_id=user_id,
            import_source_id=uuid.uuid4(),
            source_filename="done.epub",
            source_hash="a" * 64,
            list_name="Done Import",
            status="completed",
            created_at=datetime.now(timezone.utc),
        )

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        job_result = MagicMock()
        job_result.scalar_one_or_none.return_value = job
        mock_db.execute.side_effect = [user_result, job_result]

        response = await client.delete(
            f"/api/import-jobs/{job.id}",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 204
        mock_db.delete.assert_awaited_once_with(job)
        mock_db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_bulk_delete_import_jobs_rejects_active_job(self, client, mock_db):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        user = make_user(user_id)
        active_job = ImportJob(
            id=uuid.uuid4(),
            user_id=user_id,
            import_source_id=uuid.uuid4(),
            source_filename="active.epub",
            source_hash="a" * 64,
            list_name="Active Import",
            status="processing",
            created_at=datetime.now(timezone.utc),
        )

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        jobs_result = MagicMock()
        jobs_result.scalars.return_value.all.return_value = [active_job]
        mock_db.execute.side_effect = [user_result, jobs_result]

        response = await client.request(
            "DELETE",
            "/api/import-jobs",
            headers={"Authorization": f"Bearer {token}"},
            json={"job_ids": [str(active_job.id)]},
        )

        assert response.status_code == 409
        assert response.json()["detail"] == "Only completed or failed import jobs can be deleted"

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
        duplicate_result = MagicMock()
        duplicate_result.scalar_one_or_none.return_value = None
        mock_db.execute.side_effect = [user_result, job_result, duplicate_result]

        response = await client.get(
            f"/api/import-jobs/{job.id}/events",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")

    @pytest.mark.asyncio
    async def test_create_word_list_from_import_job_returns_400_for_empty_selection(self, client, mock_db):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        user = make_user(user_id)
        job = ImportJob(
            id=uuid.uuid4(),
            user_id=user_id,
            import_source_id=uuid.uuid4(),
            source_filename="book.epub",
            source_hash="e" * 64,
            list_name="Book Import",
            status="completed",
            created_at=datetime.now(timezone.utc),
        )

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        job_result = MagicMock()
        job_result.scalar_one_or_none.return_value = job
        duplicate_result = MagicMock()
        duplicate_result.scalar_one_or_none.return_value = None
        mock_db.execute.side_effect = [user_result, job_result, duplicate_result]

        response = await client.post(
            f"/api/import-jobs/{job.id}/word-lists",
            headers={"Authorization": f"Bearer {token}"},
            json={"name": "Imported", "selected_entries": []},
        )

        assert response.status_code == 400
        assert response.json()["detail"] == "At least one entry must be selected"
