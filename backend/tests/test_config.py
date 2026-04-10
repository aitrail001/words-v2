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


def test_settings_ignore_unrelated_env_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("POSTGRES_USER", "vocabapp")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    settings = Settings(_env_file=None)
    assert settings.environment == "development"


def test_dev_settings_allow_loopback_origin_regex(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "development")
    settings = Settings(_env_file=None)
    assert settings.cors_origin_regex == r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$"


def test_non_dev_settings_disable_loopback_origin_regex(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "test")
    settings = Settings(_env_file=None)
    assert settings.cors_origin_regex is None
