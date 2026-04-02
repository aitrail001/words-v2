from celery import Celery

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "words_codex",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.tasks.epub_processing", "app.tasks.lexicon_jobs"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_default_queue="default",
    task_routes={
        "process_source_import": {"queue": "imports"},
        "process_word_list_import": {"queue": "imports"},
        "extract_epub_vocabulary": {"queue": "imports"},
    },
    task_time_limit=3600,  # 1 hour max
    task_soft_time_limit=3300,  # 55 minutes soft limit
)
