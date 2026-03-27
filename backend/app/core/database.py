from collections.abc import AsyncGenerator

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.api.request_db_metrics import instrument_session_for_request, restore_session_after_request
from app.core.config import get_settings

settings = get_settings()

engine = create_async_engine(
    settings.database_url,
    echo=settings.environment == "development",
    pool_pre_ping=True,
)

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db(request: Request) -> AsyncGenerator[AsyncSession, None]:
    async with async_session() as session:
        instrument_session_for_request(request, session)
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            restore_session_after_request(session)
