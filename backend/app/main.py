from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.api.health import router as health_router
from app.core.config import get_settings
from app.core.logging import setup_logging
from app.core.redis import close_redis, init_redis

settings = get_settings()


@asynccontextmanager
async def lifespan(application: FastAPI):
    setup_logging()
    init_redis(settings.redis_url)
    yield
    await close_redis()


limiter = Limiter(key_func=get_remote_address)

app = FastAPI(
    title="Words-Codex API",
    version="0.1.0",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(health_router, prefix="/api")
