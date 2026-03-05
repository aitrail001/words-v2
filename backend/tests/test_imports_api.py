import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.database import get_db
from app.core.redis import get_redis
from app.core.security import create_access_token, hash_password
from app.main import app
from app.models.epub_import import EpubImport
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
    @patch("app.api.imports.extract_epub_vocabulary.delay")
    async def test_create_import_success(self, mock_delay, client, mock_db):
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
            "/api/imports",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("book.epub", b"fake epub content", "application/epub+zip")},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["filename"] == "book.epub"
        assert data["status"] == "pending"
        mock_delay.assert_called_once()

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
    @patch("app.api.imports.extract_epub_vocabulary.delay")
    async def test_create_import_duplicate_completed_returns_existing(
        self, mock_delay, client, mock_db
    ):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        user = make_user(user_id)

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user

        existing_import = EpubImport(
            id=uuid.uuid4(),
            user_id=user_id,
            filename="book.epub",
            file_hash="b" * 64,
            status="completed",
            total_words=10,
            processed_words=10,
            created_at=datetime.now(timezone.utc),
        )
        existing_result = MagicMock()
        existing_result.scalar_one_or_none.return_value = existing_import
        mock_db.execute.side_effect = [user_result, existing_result]

        response = await client.post(
            "/api/imports",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("book.epub", b"duplicate content", "application/epub+zip")},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(existing_import.id)
        assert data["status"] == "completed"
        mock_delay.assert_not_called()
        mock_db.add.assert_not_called()

    @pytest.mark.asyncio
    @patch("app.api.imports.extract_epub_vocabulary.delay")
    async def test_create_import_duplicate_processing_returns_existing(
        self, mock_delay, client, mock_db
    ):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        user = make_user(user_id)

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user

        existing_import = EpubImport(
            id=uuid.uuid4(),
            user_id=user_id,
            filename="book.epub",
            file_hash="c" * 64,
            status="processing",
            total_words=0,
            processed_words=0,
            created_at=datetime.now(timezone.utc),
        )
        existing_result = MagicMock()
        existing_result.scalar_one_or_none.return_value = existing_import
        mock_db.execute.side_effect = [user_result, existing_result]

        response = await client.post(
            "/api/imports",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("book.epub", b"duplicate content", "application/epub+zip")},
        )

        assert response.status_code == 202
        data = response.json()
        assert data["id"] == str(existing_import.id)
        assert data["status"] == "processing"
        mock_delay.assert_not_called()
        mock_db.add.assert_not_called()

    @pytest.mark.asyncio
    @patch("app.api.imports.UPLOAD_DIR")
    @patch("app.api.imports.extract_epub_vocabulary.delay")
    async def test_create_import_enqueue_failure_marks_failed_and_cleans_up_file(
        self, mock_delay, mock_upload_dir, client, mock_db, tmp_path
    ):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        user = make_user(user_id)

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        existing_result = MagicMock()
        existing_result.scalar_one_or_none.return_value = None
        mock_db.execute.side_effect = [user_result, existing_result]

        mock_upload_dir.__truediv__.side_effect = lambda value: Path(tmp_path) / value

        async def fake_refresh(obj):
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

        created_import = mock_db.add.call_args[0][0]
        assert created_import.status == "failed"
        assert created_import.error_message == "Failed to queue import task"
        assert created_import.completed_at is not None
        assert mock_db.commit.await_count == 2
        assert list(tmp_path.iterdir()) == []


class TestListImports:
    @pytest.mark.asyncio
    async def test_list_imports(self, client, mock_db):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        user = make_user(user_id)

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user

        existing_import = EpubImport(
            id=uuid.uuid4(),
            user_id=user_id,
            filename="book.epub",
            file_hash="a" * 64,
            status="completed",
            total_words=100,
            processed_words=100,
            created_at=datetime.now(timezone.utc),
        )
        imports_result = MagicMock()
        imports_result.scalars.return_value.all.return_value = [existing_import]

        mock_db.execute.side_effect = [user_result, imports_result]

        response = await client.get(
            "/api/imports",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["filename"] == "book.epub"


class TestGetImport:
    @pytest.mark.asyncio
    async def test_get_import_not_found_with_ownership_filter(self, client, mock_db):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        user = make_user(user_id)
        import_id = uuid.uuid4()

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        import_result = MagicMock()
        import_result.scalar_one_or_none.return_value = None

        mock_db.execute.side_effect = [user_result, import_result]

        response = await client.get(
            f"/api/imports/{import_id}",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 404
        assert response.json()["detail"] == "Import not found"
