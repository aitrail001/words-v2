import io
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from starlette.datastructures import UploadFile
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
    async def test_create_import_helper_caches_user_id_before_source_commit_boundary(self, mock_db):
        user_id = uuid.uuid4()

        class UserIdGuard:
            def __init__(self, guarded_user_id: uuid.UUID) -> None:
                self._id = guarded_user_id
                self.locked = False

            @property
            def id(self) -> uuid.UUID:
                if self.locked:
                    raise AssertionError("user.id should not be re-read after source creation")
                return self._id

        guarded_user = UserIdGuard(user_id)
        active_result = MagicMock()
        active_result.scalar_one.return_value = 0
        mock_db.execute.return_value = active_result

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

        async def fake_get_or_create_import_source(*args, **kwargs):
            guarded_user.locked = True
            return created_source

        async def fake_create_import_job(db, *, user_id, import_source, source_filename, list_name, list_description):
            assert user_id == guarded_user._id
            assert import_source is created_source
            assert source_filename == "book.epub"
            assert list_name == "Book"
            assert list_description is None
            assert db is mock_db
            return created_job

        upload = UploadFile(filename="book.epub", file=io.BytesIO(b"fake epub content"))
        response = Response()

        with (
            patch.object(word_lists_api, "get_or_create_import_source", side_effect=fake_get_or_create_import_source),
            patch.object(word_lists_api, "create_import_job", side_effect=fake_create_import_job),
            patch.object(word_lists_api.process_word_list_import, "delay"),
        ):
            result = await word_lists_api._create_import_job_from_upload(
                db=mock_db,
                user=guarded_user,
                file=upload,
                list_name="Book",
                list_description=None,
                response=response,
            )

        assert response.status_code == 201
        assert result.id == str(created_job.id)

    @pytest.mark.asyncio
    @patch("app.api.word_lists.process_word_list_import.delay")
    async def test_create_import_success(self, mock_delay, client, mock_db):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        user = make_user(user_id)

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        active_result = MagicMock()
        active_result.scalar_one.return_value = 0
        source_lookup = MagicMock()
        source_lookup.scalar_one_or_none.return_value = None
        mock_db.execute.side_effect = [user_result, active_result, source_lookup]

        async def fake_refresh(obj):
            if isinstance(obj, ImportSource):
                obj.id = uuid.uuid4()
                obj.status = "pending"
                obj.matched_entry_count = 0
            elif isinstance(obj, ImportJob):
                obj.id = uuid.uuid4()
                obj.created_at = datetime.now(timezone.utc)

        mock_db.refresh.side_effect = fake_refresh

        response = await client.post(
            "/api/imports",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("book.epub", b"fake epub content", "application/epub+zip")},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["source_filename"] == "book.epub"
        assert data["status"] == "queued"
        mock_delay.assert_called_once()

    @pytest.mark.asyncio
    @patch("app.api.word_lists.process_word_list_import.delay")
    async def test_create_import_reuses_completed_exact_source_without_requeue(
        self,
        mock_delay,
        client,
        mock_db,
    ):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        user = make_user(user_id)
        source_id = uuid.uuid4()

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        active_result = MagicMock()
        active_result.scalar_one.return_value = 0
        source_lookup = MagicMock()
        source_lookup.scalar_one_or_none.return_value = ImportSource(
            id=source_id,
            source_type="epub",
            source_hash_sha256="a" * 64,
            status="completed",
            matched_entry_count=3,
        )
        mock_db.execute.side_effect = [user_result, active_result, source_lookup]

        async def fake_refresh(obj):
            if isinstance(obj, ImportJob):
                obj.id = uuid.uuid4()
                obj.created_at = datetime.now(timezone.utc)

        mock_db.refresh.side_effect = fake_refresh

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
        mock_delay.assert_not_called()

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
    @patch("app.api.word_lists.UPLOAD_DIR")
    @patch("app.api.word_lists.process_word_list_import.delay")
    async def test_create_import_enqueue_failure_marks_failed_and_cleans_up_file(
        self, mock_delay, mock_upload_dir, client, mock_db, tmp_path
    ):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        user = make_user(user_id)

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        active_result = MagicMock()
        active_result.scalar_one.return_value = 0
        source_lookup = MagicMock()
        source_lookup.scalar_one_or_none.return_value = None
        mock_db.execute.side_effect = [user_result, active_result, source_lookup]
        mock_upload_dir.__truediv__.side_effect = lambda value: Path(tmp_path) / value

        async def fake_refresh(obj):
            if isinstance(obj, ImportSource):
                obj.id = uuid.uuid4()
                obj.status = "pending"
                obj.matched_entry_count = 0
            elif isinstance(obj, ImportJob):
                obj.id = uuid.uuid4()
                obj.created_at = datetime.now(timezone.utc)

        mock_db.refresh.side_effect = fake_refresh
        mock_delay.side_effect = RuntimeError("broker offline")

        response = await client.post(
            "/api/imports",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("book.epub", b"queue failure content", "application/epub+zip")},
        )

        assert response.status_code == 503
        assert response.json()["detail"] == "Import queue is unavailable"
        assert list(tmp_path.iterdir()) == []
