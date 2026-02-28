import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.database import get_db
from app.core.redis import get_redis
from app.core.security import hash_password
from app.main import app
from app.models.user import User


@pytest.fixture
def mock_db():
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.add = MagicMock()  # db.add is sync in SQLAlchemy
    return session


@pytest.fixture
def mock_redis():
    r = AsyncMock()
    r.ping = AsyncMock(return_value=True)
    r.set = AsyncMock()
    r.get = AsyncMock(return_value=None)
    r.delete = AsyncMock()
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


def make_user(
    email: str = "test@example.com",
    password: str = "password123",
    role: str = "user",
    is_active: bool = True,
) -> User:
    return User(
        id=uuid.uuid4(),
        email=email,
        password_hash=hash_password(password),
        role=role,
        is_active=is_active,
    )


class TestRegister:
    @pytest.mark.asyncio
    async def test_register_success(self, client, mock_db):
        # Mock: no existing user found
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = result

        response = await client.post("/api/auth/register", json={
            "email": "new@example.com",
            "password": "secure_pass_123",
        })
        assert response.status_code == 201
        data = response.json()
        assert "access_token" in data
        assert data["email"] == "new@example.com"

    @pytest.mark.asyncio
    async def test_register_duplicate_email(self, client, mock_db):
        existing_user = make_user(email="taken@example.com")
        result = MagicMock()
        result.scalar_one_or_none.return_value = existing_user
        mock_db.execute.return_value = result

        response = await client.post("/api/auth/register", json={
            "email": "taken@example.com",
            "password": "secure_pass_123",
        })
        assert response.status_code == 409

    @pytest.mark.asyncio
    async def test_register_invalid_email(self, client):
        response = await client.post("/api/auth/register", json={
            "email": "not-an-email",
            "password": "secure_pass_123",
        })
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_register_short_password(self, client):
        response = await client.post("/api/auth/register", json={
            "email": "test@example.com",
            "password": "short",
        })
        assert response.status_code == 422


class TestLogin:
    @pytest.mark.asyncio
    async def test_login_success(self, client, mock_db):
        user = make_user(email="test@example.com", password="correct_password")
        result = MagicMock()
        result.scalar_one_or_none.return_value = user
        mock_db.execute.return_value = result

        response = await client.post("/api/auth/login", json={
            "email": "test@example.com",
            "password": "correct_password",
        })
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data

    @pytest.mark.asyncio
    async def test_login_wrong_password(self, client, mock_db):
        user = make_user(email="test@example.com", password="correct_password")
        result = MagicMock()
        result.scalar_one_or_none.return_value = user
        mock_db.execute.return_value = result

        response = await client.post("/api/auth/login", json={
            "email": "test@example.com",
            "password": "wrong_password",
        })
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_login_nonexistent_user(self, client, mock_db):
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = result

        response = await client.post("/api/auth/login", json={
            "email": "nobody@example.com",
            "password": "any_password",
        })
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_login_inactive_user(self, client, mock_db):
        user = make_user(email="inactive@example.com", is_active=False)
        result = MagicMock()
        result.scalar_one_or_none.return_value = user
        mock_db.execute.return_value = result

        response = await client.post("/api/auth/login", json={
            "email": "inactive@example.com",
            "password": "password123",
        })
        assert response.status_code == 401


class TestMe:
    @pytest.mark.asyncio
    async def test_me_authenticated(self, client, mock_db):
        user = make_user(email="me@example.com")
        result = MagicMock()
        result.scalar_one_or_none.return_value = user
        mock_db.execute.return_value = result

        from app.core.security import create_access_token
        token = create_access_token(subject=str(user.id))

        response = await client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == "me@example.com"

    @pytest.mark.asyncio
    async def test_me_no_token(self, client):
        response = await client.get("/api/auth/me")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_me_invalid_token(self, client):
        response = await client.get(
            "/api/auth/me",
            headers={"Authorization": "Bearer invalid.token.here"},
        )
        assert response.status_code == 401
