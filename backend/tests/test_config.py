import pytest
from codeact.config import Settings


def test_settings_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "CODEACT_ENVIRONMENT",
        "CODEACT_MAX_STEPS",
        "CODEACT_MAX_CONSECUTIVE_FAILURES",
        "CODEACT_EXECUTION_TIMEOUT_SECONDS",
        "CODEACT_MAX_OUTPUT_CHARS",
    ):
        monkeypatch.delenv(name, raising=False)
    settings = Settings.from_env()
    assert settings.max_steps == 10
    assert settings.docker_image == "python:3.12.10-slim"


def test_settings_environment_override_and_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CODEACT_MAX_STEPS", "4")
    assert Settings.from_env().max_steps == 4
    monkeypatch.setenv("CODEACT_MAX_STEPS", "0")
    with pytest.raises(ValueError, match="at least 1"):
        Settings.from_env()
