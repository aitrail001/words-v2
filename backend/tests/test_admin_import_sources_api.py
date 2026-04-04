import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

import app.api.admin_import_sources as admin_import_sources_api
from app.api.auth import get_current_admin_user
from app.core.database import get_db
from app.main import app
from app.models.user import User


@pytest.fixture
def mock_db():
    session = AsyncMock()
    return session


@pytest.fixture
async def client(mock_db):
    async def override_get_db():
        yield mock_db

    def override_admin():
        return User(
            id=uuid.uuid4(),
            email="admin@example.com",
            password_hash="unused",
            role="admin",
        )

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_admin_user] = override_admin

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_get_source_detail_uses_dedicated_detail_lookup(client, mock_db, monkeypatch):
    source_id = uuid.uuid4()
    detailed_source = {
        "id": str(source_id),
        "title": "Older Source",
        "status": "completed",
        "matched_entry_count": 12,
        "word_entry_count": 9,
        "phrase_entry_count": 3,
        "total_jobs": 4,
        "cache_hit_count": 2,
        "created_at": datetime.now(timezone.utc),
        "processed_at": datetime.now(timezone.utc),
        "deleted_at": None,
        "deleted_by_user_id": None,
        "deletion_reason": None,
    }

    async def fake_get_detail(_db, *, source_id):
        assert source_id == uuid.UUID(detailed_source["id"])
        return detailed_source

    async def fail_if_list_called(*_args, **_kwargs):
        raise AssertionError("list_admin_import_sources should not be used for detail lookups")

    monkeypatch.setattr(admin_import_sources_api, "get_admin_import_source_detail", fake_get_detail)
    monkeypatch.setattr(admin_import_sources_api, "list_admin_import_sources", fail_if_list_called)

    response = await client.get(f"/api/admin/import-sources/{source_id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == str(source_id)
    assert payload["word_entry_count"] == 9
    assert payload["phrase_entry_count"] == 3
    assert payload["total_jobs"] == 4
    assert payload["cache_hit_count"] == 2
