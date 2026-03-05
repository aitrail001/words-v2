import uuid
from unittest.mock import AsyncMock

import pytest


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


@pytest.mark.asyncio
async def test_health_adds_request_id_header_when_missing(client):
    response = await client.get("/api/health")
    assert response.status_code == 200
    request_id = response.headers.get("x-request-id")
    assert request_id is not None
    assert request_id != ""
    uuid.UUID(request_id)


@pytest.mark.asyncio
async def test_health_echoes_provided_request_id_header(client):
    request_id = "test-request-id-123"
    response = await client.get(
        "/api/health",
        headers={"X-Request-ID": request_id},
    )
    assert response.status_code == 200
    assert response.headers.get("x-request-id") == request_id
