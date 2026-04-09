from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.logging import get_logger
from app.core.security import hash_password, verify_password
from app.models.user import User

logger = get_logger(__name__)


@dataclass(frozen=True)
class DevTestUserSpec:
    email: str
    password: str
    role: str


DEV_TEST_USERS: tuple[DevTestUserSpec, ...] = (
    DevTestUserSpec(email="admin@admin.com", password="12345678", role="admin"),
    DevTestUserSpec(email="admin01@admin.com", password="12345678", role="admin"),
    DevTestUserSpec(email="admin02@admin.com", password="12345678", role="admin"),
    DevTestUserSpec(email="admin03@admin.com", password="12345678", role="admin"),
    DevTestUserSpec(email="user@user.com", password="12345678", role="user"),
    DevTestUserSpec(email="user01@user.com", password="12345678", role="user"),
    DevTestUserSpec(email="user02@user.com", password="12345678", role="user"),
    DevTestUserSpec(email="user03@user.com", password="12345678", role="user"),
)


async def ensure_dev_test_users(session_factory: async_sessionmaker[AsyncSession]) -> None:
    async with session_factory() as session:
        created_count = 0
        updated_count = 0
        for spec in DEV_TEST_USERS:
            result = await session.execute(select(User).where(User.email == spec.email))
            user = result.scalar_one_or_none()
            password_hash = hash_password(spec.password)
            if user is None:
                session.add(
                    User(
                        email=spec.email,
                        password_hash=password_hash,
                        role=spec.role,
                        is_active=True,
                    )
                )
                created_count += 1
                continue

            changed = False
            if user.role != spec.role:
                user.role = spec.role
                changed = True
            if not user.is_active:
                user.is_active = True
                changed = True
            if not user.password_hash or not verify_password(spec.password, user.password_hash):
                user.password_hash = password_hash
                changed = True
            if changed:
                updated_count += 1

        await session.commit()
        logger.info(
            "dev_test_users_ensured",
            created_count=created_count,
            updated_count=updated_count,
            total_count=len(DEV_TEST_USERS),
        )
