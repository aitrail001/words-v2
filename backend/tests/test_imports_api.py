import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from starlette.responses import Response

from app.core.database import get_db
from app.core.redis import get_redis
from app.core.security import create_access_token, hash_password
from app.api import word_lists as word_lists_api
from app.main import app
from app.models.import_job import ImportJob
from app.models.import_source import ImportSource
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


class TestCreateImport:
    @pytest.mark.asyncio
    async def test_import_job_response_uses_explicit_source_without_lazy_loading(self):
        source_id = uuid.uuid4()
        user_id = uuid.uuid4()
        created_at = datetime.now(timezone.utc)
        import_source = ImportSource(
            id=source_id,
            source_type="epub",
            source_hash_sha256="a" * 64,
            status="completed",
            matched_entry_count=4,
            title="Clean title",
            author="Author Name",
            publisher="Publisher Name",
            published_year=2020,
            isbn="9780000000000",
        )

        class LazyLoadGuardJob:
            def __init__(self) -> None:
                self.id = uuid.uuid4()
                self.user_id = user_id
                self.import_source_id = source_id
                self.word_list_id = None
                self.status = "completed"
                self.source_filename = "book.epub"
                self.source_hash = "a" * 64
                self.list_name = "Imported list"
                self.list_description = None
                self.total_items = 0
                self.processed_items = 0
                self.progress_stage = "completed"
                self.progress_total = 0
                self.progress_completed = 0
                self.progress_current_label = "Completed from cached import"
                self.matched_entry_count = 0
                self.created_count = 0
                self.skipped_count = 0
                self.not_found_count = 0
                self.not_found_words = None
                self.error_count = 0
                self.error_message = None
                self.created_at = created_at
                self.started_at = None
                self.completed_at = created_at
                self.word_entry_count = 3
                self.phrase_entry_count = 1

            @property
            def import_source(self):
                raise AssertionError("serializer should not lazy-load import_source when explicit source is provided")

        response = word_lists_api._to_import_job_response(
            LazyLoadGuardJob(),
            import_source=import_source,
        )

        assert response.import_source_id == str(source_id)
        assert response.source_title == "Clean title"
        assert response.source_author == "Author Name"
        assert response.source_publisher == "Publisher Name"
        assert response.total_entries_extracted == 0

    @pytest.mark.asyncio
    async def test_create_import_helper_uses_shared_enqueue_service(self, mock_db):
        user_id = uuid.uuid4()
        user = make_user(user_id)
        created_source = ImportSource(
            id=uuid.uuid4(),
            source_type="epub",
            source_hash_sha256="a" * 64,
            status="pending",
            matched_entry_count=0,
        )
        created_job = ImportJob(
            id=uuid.uuid4(),
            user_id=user_id,
            import_source_id=created_source.id,
            source_filename="book.epub",
            source_hash=created_source.source_hash_sha256,
            list_name="Book",
            status="queued",
            created_at=datetime.now(timezone.utc),
        )
        upload = AsyncMock()
        upload.filename = "book.epub"
        response = Response()

        with patch.object(
            word_lists_api,
            "enqueue_epub_import_upload",
            AsyncMock(return_value=(created_job, created_source, False)),
        ) as mock_enqueue:
            result = await word_lists_api._create_import_job_from_upload(
                db=mock_db,
                user=user,
                file=upload,
                list_name="Book",
                list_description=None,
                response=response,
            )

        assert response.status_code == 201
        assert result.id == str(created_job.id)
        mock_enqueue.assert_awaited_once()

    @pytest.mark.asyncio
    @patch("app.api.word_lists.enqueue_epub_import_upload", new_callable=AsyncMock)
    async def test_create_import_success(self, mock_enqueue, client, mock_db):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        user = make_user(user_id)

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        mock_db.execute.side_effect = [user_result]
        created_source = ImportSource(
            id=uuid.uuid4(),
            source_type="epub",
            source_hash_sha256="a" * 64,
            status="pending",
            matched_entry_count=0,
        )
        created_job = ImportJob(
            id=uuid.uuid4(),
            user_id=user_id,
            import_source_id=created_source.id,
            source_filename="book.epub",
            source_hash="a" * 64,
            list_name="book",
            status="queued",
            created_at=datetime.now(timezone.utc),
        )
        mock_enqueue.return_value = (created_job, created_source, False)

        response = await client.post(
            "/api/imports",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("book.epub", b"fake epub content", "application/epub+zip")},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["source_filename"] == "book.epub"
        assert data["status"] == "queued"
        mock_enqueue.assert_awaited_once()

    @pytest.mark.asyncio
    @patch("app.api.word_lists.enqueue_epub_import_upload", new_callable=AsyncMock)
    async def test_create_import_reuses_completed_exact_source_without_requeue(
        self,
        mock_enqueue,
        client,
        mock_db,
    ):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        user = make_user(user_id)
        source_id = uuid.uuid4()

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        mock_db.execute.side_effect = [user_result]
        created_source = ImportSource(
            id=source_id,
            source_type="epub",
            source_hash_sha256="a" * 64,
            status="completed",
            matched_entry_count=3,
        )
        created_job = ImportJob(
            id=uuid.uuid4(),
            user_id=user_id,
            import_source_id=source_id,
            source_filename="book.epub",
            source_hash="a" * 64,
            list_name="book",
            status="completed",
            created_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
            progress_stage="completed",
            progress_current_label="Completed from cached import",
        )
        mock_enqueue.return_value = (created_job, created_source, True)

        response = await client.post(
            "/api/imports",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("book.epub", b"fake epub content", "application/epub+zip")},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"
        assert data["import_source_id"] == str(source_id)
        assert data["completed_at"] is not None
        assert data["progress_stage"] == "completed"
        assert data["progress_current_label"] == "Completed from cached import"
        mock_enqueue.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_import_rejects_non_epub(self, client, mock_db):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        user = make_user(user_id)

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        mock_db.execute.return_value = user_result

        response = await client.post(
            "/api/imports",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("notes.txt", b"not epub", "text/plain")},
        )

        assert response.status_code == 400
        assert response.json()["detail"] == "Only .epub files are supported"

    @pytest.mark.asyncio
    async def test_create_import_rejects_when_user_has_too_many_active_jobs(self, client, mock_db):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        user = make_user(user_id)

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        active_result = MagicMock()
        active_result.scalar_one.return_value = 3
        mock_db.execute.side_effect = [user_result, active_result]

        response = await client.post(
            "/api/imports",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("book.epub", b"fake epub content", "application/epub+zip")},
        )

        assert response.status_code == 429
        assert response.json()["detail"] == "Too many active imports"

    @pytest.mark.asyncio
    @patch("app.api.word_lists.enqueue_epub_import_upload", new_callable=AsyncMock)
    async def test_create_import_enqueue_failure_marks_failed_and_cleans_up_file(
        self, mock_enqueue, client, mock_db
    ):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        user = make_user(user_id)

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        mock_db.execute.side_effect = [user_result]
        from fastapi import HTTPException
        mock_enqueue.side_effect = HTTPException(status_code=503, detail="Import queue is unavailable")

        response = await client.post(
            "/api/imports",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("book.epub", b"queue failure content", "application/epub+zip")},
        )

        assert response.status_code == 503
        assert response.json()["detail"] == "Import queue is unavailable"


class TestListImports:
    @pytest.mark.asyncio
    async def test_list_imports_hydrates_source_details_before_serialization(self, client, mock_db):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        user = make_user(user_id)
        import_source_id = uuid.uuid4()
        created_at = datetime.now(timezone.utc)

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        jobs_result = MagicMock()
        jobs_result.scalars.return_value.all.return_value = [
            ImportJob(
                id=uuid.uuid4(),
                user_id=user_id,
                import_source_id=import_source_id,
                source_filename="book.epub",
                source_hash="a" * 64,
                list_name="Imported list",
                status="completed",
                total_items=10,
                processed_items=10,
                matched_entry_count=10,
                created_at=created_at,
                completed_at=created_at,
            )
        ]
        sources_result = MagicMock()
        sources_result.scalars.return_value.all.return_value = [
            ImportSource(
                id=import_source_id,
                source_type="epub",
                source_hash_sha256="a" * 64,
                title="Book Title",
                author="Alice",
                publisher="Publisher House",
                published_year=2024,
                isbn="9781234567890",
                pipeline_version="v1",
                lexicon_version="v1",
                status="completed",
                matched_entry_count=10,
            )
        ]
        counts_result = MagicMock()
        counts_result.all.return_value = []
        mock_db.execute.side_effect = [user_result, jobs_result, sources_result, counts_result]

        response = await client.get(
            "/api/imports",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["source_title"] == "Book Title"
        assert data[0]["source_publisher"] == "Publisher House"
        assert data[0]["source_hash"] == "a" * 64
