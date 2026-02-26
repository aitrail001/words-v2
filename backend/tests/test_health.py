import pytest
from unittest.mock import AsyncMock


@pytest.mark.asyncio
async def test_health_returns_ok(client):
    response = await client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["database"] == "ok"
    assert data["redis"] == "ok"


@pytest.mark.asyncio
async def test_health_degraded_when_db_fails(client, mock_db):
    mock_db.execute = AsyncMock(side_effect=Exception("connection refused"))
    response = await client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "degraded"
    assert data["database"] == "error"
    assert data["redis"] == "ok"


@pytest.mark.asyncio
async def test_health_degraded_when_redis_fails(client, mock_redis):
    mock_redis.ping = AsyncMock(side_effect=Exception("connection refused"))
    response = await client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "degraded"
    assert data["database"] == "ok"
    assert data["redis"] == "error"
