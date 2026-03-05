import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_settings_accepts_test_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "test")
    settings = Settings(_env_file=None)
    assert settings.environment == "test"


def test_settings_rejects_unknown_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "qa")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)
