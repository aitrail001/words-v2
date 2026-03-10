from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.dev_test_users import DEV_TEST_USERS, ensure_dev_test_users
from app.models.user import User


@pytest.mark.asyncio
async def test_ensure_dev_test_users_creates_missing_users():
    session = AsyncMock()
    session.add = MagicMock()
    session.execute.side_effect = [MagicMock(scalar_one_or_none=MagicMock(return_value=None)) for _ in DEV_TEST_USERS]
    session_factory = MagicMock()
    session_factory.return_value.__aenter__.return_value = session
    session_factory.return_value.__aexit__.return_value = False

    await ensure_dev_test_users(session_factory)

    assert session.add.call_count == len(DEV_TEST_USERS)
    added_users = [call.args[0] for call in session.add.call_args_list]
    assert [user.email for user in added_users] == [spec.email for spec in DEV_TEST_USERS]
    assert [user.role for user in added_users] == [spec.role for spec in DEV_TEST_USERS]
    assert all(isinstance(user, User) for user in added_users)
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_ensure_dev_test_users_updates_role_and_activation_for_existing_users():
    existing_admin = User(email="admin@admin.com", password_hash="not-bcrypt", role="user", is_active=False)
    existing_user = User(email="user@user.com", password_hash="not-bcrypt", role="admin", is_active=False)

    session = AsyncMock()
    session.add = MagicMock()
    session.execute.side_effect = [
        MagicMock(scalar_one_or_none=MagicMock(return_value=existing_admin)),
        MagicMock(scalar_one_or_none=MagicMock(return_value=existing_user)),
    ]
    session_factory = MagicMock()
    session_factory.return_value.__aenter__.return_value = session
    session_factory.return_value.__aexit__.return_value = False

    await ensure_dev_test_users(session_factory)

    assert session.add.call_count == 0
    assert existing_admin.role == "admin"
    assert existing_admin.is_active is True
    assert existing_admin.password_hash.startswith("$2")
    assert existing_user.role == "user"
    assert existing_user.is_active is True
    assert existing_user.password_hash.startswith("$2")
    session.commit.assert_awaited_once()
