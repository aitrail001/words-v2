import uuid

import pytest

from app.core.security import create_access_token, decode_token
from app.services.auth_tokens import AuthTokenService


class InMemoryRedis:
    def __init__(self):
        self.store: dict[str, str] = {}
        self.expiry: dict[str, int] = {}

    async def set(self, name: str, value: str, ex: int | None = None, nx: bool = False):
        if nx and name in self.store:
            return False
        self.store[name] = value
        if ex is not None:
            self.expiry[name] = ex
        return True

    async def get(self, name: str):
        return self.store.get(name)

    async def delete(self, *names: str):
        deleted = 0
        for name in names:
            if name in self.store:
                deleted += 1
                del self.store[name]
        return deleted


class BytesRedis(InMemoryRedis):
    async def get(self, name: str):
        value = self.store.get(name)
        if isinstance(value, str):
            return value.encode()
        return value


@pytest.mark.asyncio
async def test_issue_token_pair_stores_active_refresh_jti():
    redis = InMemoryRedis()
    service = AuthTokenService(redis)
    subject = str(uuid.uuid4())

    tokens = await service.issue_token_pair(subject=subject, extra={"role": "user"})

    refresh_payload = decode_token(tokens["refresh_token"])
    assert tokens["token_type"] == "bearer"
    assert refresh_payload["token_type"] == "refresh"
    assert redis.store[f"auth:refresh:active:{subject}"] == refresh_payload["jti"]


@pytest.mark.asyncio
async def test_rotate_refresh_token_rejects_reuse_of_old_token():
    redis = InMemoryRedis()
    service = AuthTokenService(redis)
    subject = str(uuid.uuid4())

    original_tokens = await service.issue_token_pair(subject=subject)
    rotated_tokens = await service.rotate_refresh_token(original_tokens["refresh_token"])
    reused_tokens = await service.rotate_refresh_token(original_tokens["refresh_token"])

    assert rotated_tokens is not None
    assert rotated_tokens["refresh_token"] != original_tokens["refresh_token"]
    assert rotated_tokens["access_token"] != original_tokens["access_token"]
    assert reused_tokens is None


@pytest.mark.asyncio
async def test_revoke_access_token_by_jti_marks_token_as_revoked():
    redis = InMemoryRedis()
    service = AuthTokenService(redis)
    token = create_access_token(subject=str(uuid.uuid4()))

    assert await service.is_access_token_revoked(token) is False
    await service.revoke_access_token(token)
    assert await service.is_access_token_revoked(token) is True


@pytest.mark.asyncio
async def test_rotate_refresh_token_rejects_non_refresh_token():
    redis = InMemoryRedis()
    service = AuthTokenService(redis)
    token = create_access_token(subject=str(uuid.uuid4()))

    assert await service.rotate_refresh_token(token) is None


@pytest.mark.asyncio
async def test_is_access_payload_revoked_ignores_non_marker_values():
    redis = InMemoryRedis()
    service = AuthTokenService(redis)
    token = create_access_token(subject=str(uuid.uuid4()))
    payload = decode_token(token)
    assert payload is not None

    redis.store[f"auth:access:revoked:{payload['jti']}"] = "unexpected-value"
    assert await service.is_access_payload_revoked(payload) is False


@pytest.mark.asyncio
async def test_rotate_refresh_token_supports_bytes_redis_get_values():
    redis = BytesRedis()
    service = AuthTokenService(redis)
    subject = str(uuid.uuid4())

    tokens = await service.issue_token_pair(subject=subject)
    rotated = await service.rotate_refresh_token(tokens["refresh_token"])

    assert rotated is not None
