import pytest
from pydantic import ValidationError

from app.core.config import Settings, get_settings


def test_settings_accepts_test_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "test")
    settings = Settings(_env_file=None)
    assert settings.environment == "test"


def test_settings_rejects_unknown_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "qa")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_dev_test_users_enabled_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEV_TEST_USERS_ENABLED", "true")
    monkeypatch.setenv("ENVIRONMENT", "development")
    get_settings.cache_clear()
    settings = get_settings()
    assert settings.dev_test_users_enabled is True
    get_settings.cache_clear()
