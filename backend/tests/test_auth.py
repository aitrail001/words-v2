import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.database import get_db
from app.core.redis import get_redis
from app.core.security import create_access_token, create_refresh_token, hash_password
from app.main import app
from app.models.user import User


class InMemoryRedis:
    def __init__(self):
        self._store: dict[str, str] = {}

    async def ping(self):
        return True

    async def set(self, name: str, value: str, ex: int | None = None, nx: bool = False):
        if nx and name in self._store:
            return False
        self._store[name] = value
        return True

    async def get(self, name: str):
        return self._store.get(name)

    async def delete(self, *names: str):
        deleted = 0
        for name in names:
            if name in self._store:
                deleted += 1
                del self._store[name]
        return deleted


@pytest.fixture
def mock_db():
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.add = MagicMock()  # db.add is sync in SQLAlchemy
    return session


@pytest.fixture
def mock_redis():
    return InMemoryRedis()


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
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"
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
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"

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

    @pytest.mark.asyncio
    async def test_me_rejects_refresh_token(self, client):
        token = create_refresh_token(subject=str(uuid.uuid4()))
        response = await client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_me_malformed_subject_returns_401(self, client):
        token = create_access_token(subject="not-a-uuid")
        response = await client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 401


class TestRefreshAndLogout:
    @pytest.mark.asyncio
    async def test_refresh_rotates_refresh_token(self, client, mock_db):
        user = make_user(email="rotate@example.com", password="correct_password")
        result = MagicMock()
        result.scalar_one_or_none.return_value = user
        mock_db.execute.return_value = result

        login_response = await client.post("/api/auth/login", json={
            "email": "rotate@example.com",
            "password": "correct_password",
        })
        assert login_response.status_code == 200
        tokens = login_response.json()

        refresh_response = await client.post("/api/auth/refresh", json={
            "refresh_token": tokens["refresh_token"],
        })
        assert refresh_response.status_code == 200
        refreshed_tokens = refresh_response.json()
        assert refreshed_tokens["refresh_token"] != tokens["refresh_token"]
        assert refreshed_tokens["access_token"] != tokens["access_token"]

        old_refresh_response = await client.post("/api/auth/refresh", json={
            "refresh_token": tokens["refresh_token"],
        })
        assert old_refresh_response.status_code == 401

    @pytest.mark.asyncio
    async def test_logout_revokes_access_token_by_jti(self, client, mock_db):
        user = make_user(email="logout@example.com", password="correct_password")
        result = MagicMock()
        result.scalar_one_or_none.return_value = user
        mock_db.execute.return_value = result

        login_response = await client.post("/api/auth/login", json={
            "email": "logout@example.com",
            "password": "correct_password",
        })
        assert login_response.status_code == 200
        access_token = login_response.json()["access_token"]

        me_before_logout = await client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert me_before_logout.status_code == 200

        logout_response = await client.post(
            "/api/auth/logout",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert logout_response.status_code == 204

        me_after_logout = await client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert me_after_logout.status_code == 401


class TestDevTestUserBootstrap:
    @pytest.mark.asyncio
    async def test_middleware_seeds_dev_test_users_when_enabled(self, client, mock_db, mock_redis, monkeypatch):
        from app import main as app_main

        seeded = AsyncMock()
        monkeypatch.setattr(app_main, "ensure_dev_test_users", seeded)
        monkeypatch.setattr(app_main.settings, "environment", "development")
        monkeypatch.setattr(app_main.settings, "dev_test_users_enabled", True)
        app.state.dev_test_users_seeded = False

        result = MagicMock()
        result.scalar_one_or_none.return_value = make_user(email="me@example.com")
        mock_db.execute.return_value = result
        token = create_access_token(subject=str(result.scalar_one_or_none.return_value.id))

        response = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})

        assert response.status_code == 200
        seeded.assert_awaited_once_with(app_main.async_session)
        assert app.state.dev_test_users_seeded is True

    @pytest.mark.asyncio
    async def test_middleware_skips_dev_test_users_when_disabled(self, client, mock_db, monkeypatch):
        from app import main as app_main

        seeded = AsyncMock()
        monkeypatch.setattr(app_main, "ensure_dev_test_users", seeded)
        monkeypatch.setattr(app_main.settings, "environment", "development")
        monkeypatch.setattr(app_main.settings, "dev_test_users_enabled", False)
        app.state.dev_test_users_seeded = False

        result = MagicMock()
        result.scalar_one_or_none.return_value = make_user(email="me@example.com")
        mock_db.execute.return_value = result
        token = create_access_token(subject=str(result.scalar_one_or_none.return_value.id))

        response = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})

        assert response.status_code == 200
        seeded.assert_not_awaited()


    @pytest.mark.asyncio
    async def test_middleware_tolerates_database_not_ready_for_dev_test_users(self, client, mock_db, monkeypatch):
        from app import main as app_main
        from sqlalchemy.exc import ProgrammingError

        seeded = AsyncMock(side_effect=ProgrammingError("stmt", {}, Exception("missing users table")))
        monkeypatch.setattr(app_main, "ensure_dev_test_users", seeded)
        monkeypatch.setattr(app_main.settings, "environment", "development")
        monkeypatch.setattr(app_main.settings, "dev_test_users_enabled", True)
        app.state.dev_test_users_seeded = False

        result = MagicMock()
        result.scalar_one_or_none.return_value = make_user(email="me@example.com")
        mock_db.execute.return_value = result
        token = create_access_token(subject=str(result.scalar_one_or_none.return_value.id))

        response = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})

        assert response.status_code == 200
        seeded.assert_awaited_once_with(app_main.async_session)
        assert app.state.dev_test_users_seeded is False
