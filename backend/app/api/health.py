from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

import redis.asyncio as redis

from app.core.database import get_db
from app.core.logging import get_logger
from app.core.redis import get_redis

logger = get_logger(__name__)

router = APIRouter()


class HealthResponse(BaseModel):
    status: str
    database: str
    redis: str


@router.get("/health", response_model=HealthResponse)
async def health_check(
    db: AsyncSession = Depends(get_db),
    r: redis.Redis = Depends(get_redis),
) -> HealthResponse:
    checks = {"status": "ok", "database": "ok", "redis": "ok"}

    try:
        await db.execute(text("SELECT 1"))
    except Exception as e:
        logger.error("Database health check failed", error=str(e))
        checks["database"] = "error"
        checks["status"] = "degraded"

    try:
        await r.ping()
    except Exception as e:
        logger.error("Redis health check failed", error=str(e))
        checks["redis"] = "error"
        checks["status"] = "degraded"

    return HealthResponse(**checks)
