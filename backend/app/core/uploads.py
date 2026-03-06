import os
from pathlib import Path

from app.core.logging import get_logger

logger = get_logger(__name__)

DEFAULT_UPLOAD_DIR = "/app/uploads"
FALLBACK_UPLOAD_DIR = "/tmp/words_uploads"


def resolve_upload_dir() -> Path:
    configured = Path(os.getenv("UPLOAD_DIR", DEFAULT_UPLOAD_DIR))
    try:
        configured.mkdir(parents=True, exist_ok=True)
        return configured
    except OSError as error:
        logger.warning(
            "Configured upload directory unavailable, using fallback",
            configured_path=str(configured),
            fallback_path=FALLBACK_UPLOAD_DIR,
            error=str(error),
        )
        fallback = Path(FALLBACK_UPLOAD_DIR)
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback
