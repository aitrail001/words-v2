from functools import lru_cache
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database (required — no defaults for credentials)
    database_url: str = "postgresql+asyncpg://vocabapp:devpassword@localhost:5432/vocabapp_dev"
    database_url_sync: str = "postgresql://vocabapp:devpassword@localhost:5432/vocabapp_dev"

    # Redis
    redis_url: str = "redis://localhost:6379"

    # JWT (required in production — validated below)
    jwt_secret: str = "dev-secret-key-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expiration_minutes: int = 30
    refresh_token_expiration_days: int = 7

    # Environment
    environment: Literal["development", "staging", "production", "test"] = (
        "development"
    )

    # Logging
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    # CORS
    allowed_origins: str = "http://localhost:3000,http://localhost:3001"

    # Security
    bcrypt_rounds: int = 12

    # Local dev bootstrap
    dev_test_users_enabled: bool = False

    # Rate limiting
    rate_limit_per_minute: int = 60
    max_active_imports_per_user: int = 3
    max_active_admin_preimports_per_request: int = 10

    # Lexicon artifact root (admin read-only ops API)
    lexicon_snapshot_root: str = "data/lexicon/snapshots"
    lexicon_voice_root: str = "data/lexicon/voice"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}

    @model_validator(mode="after")
    def validate_production_secrets(self) -> "Settings":
        """Refuse to start in production with known-bad secrets."""
        if self.environment == "production":
            if self.jwt_secret == "dev-secret-key-change-in-production":
                raise ValueError(
                    "JWT_SECRET must be changed from the default in production"
                )
            if "devpassword" in self.database_url:
                raise ValueError(
                    "DATABASE_URL must not use default password in production"
                )
        return self

    @property
    def cors_origins(self) -> list[str]:
        """Parse and strip whitespace from allowed origins."""
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
