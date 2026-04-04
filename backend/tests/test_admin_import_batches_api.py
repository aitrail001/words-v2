import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient
from fastapi import HTTPException

import app.api.admin_import_batches as admin_import_batches_api
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
    session.rollback = AsyncMock()
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


def make_admin(user_id: uuid.UUID) -> User:
    return User(
        id=user_id,
        email="admin@example.com",
        password_hash=hash_password("password123"),
        role="admin",
    )


class TestAdminImportBatchesApi:
    @pytest.mark.asyncio
    async def test_create_import_batch_returns_empty_epub_batch(
        self,
        client,
        mock_db,
    ):
        admin_id = uuid.uuid4()
        token = create_access_token(subject=str(admin_id))
        user = make_admin(admin_id)
        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        mock_db.execute.side_effect = [user_result]

        async def fake_refresh(batch):
            if getattr(batch, "id", None) is None:
                batch.id = uuid.uuid4()
            if getattr(batch, "created_at", None) is None:
                batch.created_at = datetime.now(timezone.utc)

        mock_db.refresh.side_effect = fake_refresh

        response = await client.post(
            "/api/admin/import-batches",
            headers={"Authorization": f"Bearer {token}"},
            json={"batch_name": "wave-1"},
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["id"]
        assert payload["name"] == "wave-1"
        assert payload["total_jobs"] == 0
        assert payload["active_jobs"] == 0

    @pytest.mark.asyncio
    async def test_add_epub_files_to_existing_batch_enqueues_jobs(
        self,
        client,
        mock_db,
        monkeypatch,
    ):
        admin_id = uuid.uuid4()
        batch_id = uuid.uuid4()
        token = create_access_token(subject=str(admin_id))
        user = make_admin(admin_id)
        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        batch_result = MagicMock()
        batch_result.scalar_one_or_none.return_value = SimpleNamespace(
            id=batch_id,
            created_by_user_id=admin_id,
            batch_type="epub_preimport",
            name="existing-batch",
            created_at=datetime.now(timezone.utc),
        )
        mock_db.execute.side_effect = [user_result, batch_result]

        queued_job = ImportJob(
            id=uuid.uuid4(),
            user_id=admin_id,
            import_source_id=uuid.uuid4(),
            source_filename="queued.epub",
            source_hash="a" * 64,
            list_name="queued",
            status="queued",
            created_at=datetime.now(timezone.utc),
        )

        enqueue_mock = AsyncMock(return_value=(queued_job, None, False))
        monkeypatch.setattr(admin_import_batches_api, "enqueue_epub_import_upload", enqueue_mock)
        monkeypatch.setattr(
            admin_import_batches_api,
            "get_import_batch_summary",
            AsyncMock(
                return_value={
                    "id": str(batch_id),
                    "created_by_user_id": str(admin_id),
                    "batch_type": "epub_preimport",
                    "name": "existing-batch",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "total_jobs": 1,
                    "completed_jobs": 0,
                    "failed_jobs": 0,
                    "active_jobs": 1,
                }
            ),
        )

        response = await client.post(
            f"/api/admin/import-batches/{batch_id}/epub",
            headers={"Authorization": f"Bearer {token}"},
            files=[("files", ("queued.epub", b"queued", "application/epub+zip"))],
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["batch"]["id"] == str(batch_id)
        assert payload["jobs"][0]["source_filename"] == "queued.epub"
        assert enqueue_mock.await_args.kwargs["import_batch_id"] == batch_id

    @pytest.mark.asyncio
    async def test_create_epub_import_batch_rejects_too_many_files(
        self,
        client,
        mock_db,
        monkeypatch,
    ):
        admin_id = uuid.uuid4()
        token = create_access_token(subject=str(admin_id))
        user = make_admin(admin_id)
        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        mock_db.execute.side_effect = [user_result]

        monkeypatch.setattr(admin_import_batches_api.settings, "max_active_admin_preimports_per_request", 3)

        response = await client.post(
            "/api/admin/import-batches/epub",
            headers={"Authorization": f"Bearer {token}"},
            data={"batch_name": "too-many"},
            files=[
                ("files", ("one.epub", b"1", "application/epub+zip")),
                ("files", ("two.epub", b"2", "application/epub+zip")),
                ("files", ("three.epub", b"3", "application/epub+zip")),
                ("files", ("four.epub", b"4", "application/epub+zip")),
            ],
        )

        assert response.status_code == 400
        assert response.json()["detail"] == "Too many files in batch (max 3)"

    @pytest.mark.asyncio
    async def test_create_epub_import_batch_returns_failures_and_rolls_back_after_enqueue_exception(
        self,
        client,
        mock_db,
        monkeypatch,
    ):
        admin_id = uuid.uuid4()
        token = create_access_token(subject=str(admin_id))
        user = make_admin(admin_id)
        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        mock_db.execute.side_effect = [user_result]

        async def fake_refresh(batch):
            if getattr(batch, "id", None) is None:
                batch.id = uuid.uuid4()
            if getattr(batch, "created_at", None) is None:
                batch.created_at = datetime.now(timezone.utc)

        mock_db.refresh.side_effect = fake_refresh

        success_job = ImportJob(
            id=uuid.uuid4(),
            user_id=admin_id,
            import_source_id=uuid.uuid4(),
            source_filename="good.epub",
            source_hash="a" * 64,
            list_name="good",
            status="queued",
            created_at=datetime.now(timezone.utc),
        )

        enqueue_mock = AsyncMock(side_effect=[RuntimeError("boom"), (success_job, None, False)])
        monkeypatch.setattr(admin_import_batches_api, "enqueue_epub_import_upload", enqueue_mock)
        monkeypatch.setattr(
            admin_import_batches_api,
            "get_import_batch_summary",
            AsyncMock(
                return_value={
                    "id": str(uuid.uuid4()),
                    "created_by_user_id": str(admin_id),
                    "batch_type": "epub_preimport",
                    "name": "test-batch",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "total_jobs": 1,
                    "completed_jobs": 0,
                    "failed_jobs": 0,
                    "active_jobs": 1,
                }
            ),
        )

        response = await client.post(
            "/api/admin/import-batches/epub",
            headers={"Authorization": f"Bearer {token}"},
            data={"batch_name": "test-batch"},
            files=[
                ("files", ("bad.epub", b"bad", "application/epub+zip")),
                ("files", ("good.epub", b"good", "application/epub+zip")),
            ],
        )

        assert response.status_code == 200
        payload = response.json()
        assert len(payload["jobs"]) == 1
        assert payload["jobs"][0]["source_filename"] == "good.epub"
        assert len(payload["failures"]) == 1
        assert payload["failures"][0]["source_filename"] == "bad.epub"
        assert payload["failures"][0]["error"] == "Failed to enqueue import"
        assert mock_db.rollback.await_count == 1
        assert mock_db.add.call_count == 1
        created_batch = mock_db.add.call_args.args[0]
        created_batch_id = created_batch.id
        assert created_batch_id is not None
        first_call = enqueue_mock.await_args_list[0]
        second_call = enqueue_mock.await_args_list[1]
        assert first_call.kwargs["import_batch_id"] == created_batch_id
        assert second_call.kwargs["import_batch_id"] == created_batch_id

    @pytest.mark.asyncio
    async def test_create_epub_import_batch_falls_back_when_summary_load_fails(
        self,
        client,
        mock_db,
        monkeypatch,
    ):
        admin_id = uuid.uuid4()
        token = create_access_token(subject=str(admin_id))
        user = make_admin(admin_id)
        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        mock_db.execute.side_effect = [user_result]

        async def fake_refresh(batch):
            if getattr(batch, "id", None) is None:
                batch.id = uuid.uuid4()
            if getattr(batch, "created_at", None) is None:
                batch.created_at = datetime.now(timezone.utc)

        mock_db.refresh.side_effect = fake_refresh

        queued_job = ImportJob(
            id=uuid.uuid4(),
            user_id=admin_id,
            import_source_id=uuid.uuid4(),
            source_filename="queued.epub",
            source_hash="a" * 64,
            list_name="queued",
            status="queued",
            created_at=datetime.now(timezone.utc),
        )

        monkeypatch.setattr(
            admin_import_batches_api,
            "enqueue_epub_import_upload",
            AsyncMock(return_value=(queued_job, None, False)),
        )
        monkeypatch.setattr(
            admin_import_batches_api,
            "get_import_batch_summary",
            AsyncMock(side_effect=RuntimeError("summary failed")),
        )

        response = await client.post(
            "/api/admin/import-batches/epub",
            headers={"Authorization": f"Bearer {token}"},
            data={"batch_name": "fallback-summary"},
            files=[("files", ("queued.epub", b"queued", "application/epub+zip"))],
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["batch"]["name"] == "fallback-summary"
        assert payload["batch"]["total_jobs"] == 1
        assert payload["batch"]["active_jobs"] == 1
        assert payload["batch"]["failed_jobs"] == 0
        assert payload["jobs"][0]["source_filename"] == "queued.epub"

    @pytest.mark.asyncio
    async def test_create_epub_import_batch_uses_stable_actor_id_after_rollback(
        self,
        client,
        mock_db,
        monkeypatch,
    ):
        class ExpiringAdminUser:
            def __init__(self, user_id: uuid.UUID) -> None:
                self._id = user_id
                self.role = "admin"
                self.is_active = True
                self.expired = False

            @property
            def id(self) -> uuid.UUID:
                if self.expired:
                    raise RuntimeError("expired user")
                return self._id

        admin_id = uuid.uuid4()
        token = create_access_token(subject=str(admin_id))
        user = ExpiringAdminUser(admin_id)
        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        mock_db.execute.side_effect = [user_result]

        async def fake_refresh(batch):
            if getattr(batch, "id", None) is None:
                batch.id = uuid.uuid4()
            if getattr(batch, "created_at", None) is None:
                batch.created_at = datetime.now(timezone.utc)

        mock_db.refresh.side_effect = fake_refresh

        async def fake_rollback() -> None:
            user.expired = True

        mock_db.rollback.side_effect = fake_rollback

        success_job = ImportJob(
            id=uuid.uuid4(),
            user_id=admin_id,
            import_source_id=uuid.uuid4(),
            source_filename="good.epub",
            source_hash="a" * 64,
            list_name="good",
            status="queued",
            created_at=datetime.now(timezone.utc),
        )

        async def fake_enqueue(**kwargs):
            _ = kwargs["actor_user"].id
            file = kwargs["file"]
            if file.filename == "bad.epub":
                raise HTTPException(status_code=400, detail="Only .epub files are supported")
            return (success_job, None, False)

        monkeypatch.setattr(admin_import_batches_api, "enqueue_epub_import_upload", fake_enqueue)
        monkeypatch.setattr(
            admin_import_batches_api,
            "get_import_batch_summary",
            AsyncMock(
                return_value={
                    "id": str(uuid.uuid4()),
                    "created_by_user_id": str(admin_id),
                    "batch_type": "epub_preimport",
                    "name": "stable-actor-test",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "total_jobs": 1,
                    "completed_jobs": 0,
                    "failed_jobs": 0,
                    "active_jobs": 1,
                }
            ),
        )

        response = await client.post(
            "/api/admin/import-batches/epub",
            headers={"Authorization": f"Bearer {token}"},
            data={"batch_name": "stable-actor-test"},
            files=[
                ("files", ("bad.epub", b"bad", "application/epub+zip")),
                ("files", ("good.epub", b"good", "application/epub+zip")),
            ],
        )

        assert response.status_code == 200
        payload = response.json()
        assert len(payload["failures"]) == 1
        assert payload["failures"][0]["source_filename"] == "bad.epub"
        assert len(payload["jobs"]) == 1
        assert payload["jobs"][0]["source_filename"] == "good.epub"
