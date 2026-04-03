from contextlib import asynccontextmanager
from time import perf_counter
from uuid import uuid4

import structlog
from sqlalchemy.exc import SQLAlchemyError
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.api.auth import router as auth_router
from app.api.admin_import_batches import router as admin_import_batches_router
from app.api.admin_import_sources import router as admin_import_sources_router
from app.api.health import router as health_router
from app.api.import_jobs import router as import_jobs_router
from app.api.lexicon_compiled_reviews import router as lexicon_compiled_reviews_router
from app.api.lexicon_inspector import router as lexicon_inspector_router
from app.api.lexicon_imports import router as lexicon_imports_router
from app.api.lexicon_jobs import router as lexicon_jobs_router
from app.api.lexicon_jsonl_reviews import router as lexicon_jsonl_reviews_router
from app.api.lexicon_ops import router as lexicon_ops_router
from app.api.knowledge_map import router as knowledge_map_router
from app.api.imports import router as imports_router
from app.api.reviews import router as reviews_router
from app.api.user_preferences import router as user_preferences_router
from app.api.word_lists import router as word_lists_router
from app.api.words import router as words_router
from app.core.config import get_settings
from app.core.logging import get_logger, setup_logging
from app.core.redis import close_redis, init_redis
from app.core.database import async_session
from app.services.dev_test_users import ensure_dev_test_users

settings = get_settings()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(application: FastAPI):
    setup_logging()
    init_redis(settings.redis_url)
    application.state.dev_test_users_seeded = False
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


@app.middleware("http")
async def request_observability_middleware(request: Request, call_next):
    if (
        settings.environment == "development"
        and settings.dev_test_users_enabled
        and not getattr(app.state, "dev_test_users_seeded", False)
    ):
        try:
            await ensure_dev_test_users(async_session)
            app.state.dev_test_users_seeded = True
        except SQLAlchemyError:
            logger.warning("dev_test_users_seed_skipped", reason="database_not_ready")

    request_id = request.headers.get("x-request-id") or str(uuid4())
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(request_id=request_id)

    start = perf_counter()
    status_code = 500

    try:
        response = await call_next(request)
        status_code = response.status_code
        response.headers["X-Request-ID"] = request_id
        return response
    finally:
        duration_ms = round((perf_counter() - start) * 1000, 2)
        logger.info(
            "http_access",
            method=request.method,
            path=request.url.path,
            status_code=status_code,
            duration_ms=duration_ms,
        )
        structlog.contextvars.clear_contextvars()


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
)

app.include_router(health_router, prefix="/api")
app.include_router(auth_router, prefix="/api/auth", tags=["auth"])
app.include_router(words_router, prefix="/api/words", tags=["words"])
app.include_router(knowledge_map_router, prefix="/api/knowledge-map", tags=["knowledge-map"])
app.include_router(reviews_router, prefix="/api/reviews", tags=["reviews"])
app.include_router(imports_router, prefix="/api/imports", tags=["imports"])
app.include_router(word_lists_router, prefix="/api/word-lists", tags=["word-lists"])
app.include_router(user_preferences_router, prefix="/api/user-preferences", tags=["user-preferences"])
app.include_router(import_jobs_router, prefix="/api/import-jobs", tags=["import-jobs"])
app.include_router(admin_import_sources_router, prefix="/api/admin/import-sources", tags=["admin-import-sources"])
app.include_router(admin_import_batches_router, prefix="/api/admin/import-batches", tags=["admin-import-batches"])
app.include_router(lexicon_compiled_reviews_router, prefix="/api/lexicon-compiled-reviews", tags=["lexicon-compiled-reviews"])
app.include_router(lexicon_jsonl_reviews_router, prefix="/api/lexicon-jsonl-reviews", tags=["lexicon-jsonl-reviews"])
app.include_router(lexicon_ops_router, prefix="/api/lexicon-ops", tags=["lexicon-ops"])
app.include_router(lexicon_imports_router, prefix="/api/lexicon-imports", tags=["lexicon-imports"])
app.include_router(lexicon_jobs_router, prefix="/api/lexicon-jobs", tags=["lexicon-jobs"])
app.include_router(lexicon_inspector_router, prefix="/api/lexicon-inspector", tags=["lexicon-inspector"])
