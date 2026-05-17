"""Tests for SECRET_KEY enforcement and DEBUG default in core settings."""

from __future__ import annotations

import pytest

from app.core.settings import Settings, get_settings

# All env vars that pydantic-settings might pull in via .env / OS env and that
# could flip DEBUG or SECRET_KEY out from under a test. We clear them per test.
_RELEVANT_ENV_VARS = ("SECRET_KEY", "DEBUG")


@pytest.fixture(autouse=True)
def _isolate_settings_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Strip env + clear the get_settings cache so each test starts clean.

    `.env` is bypassed by passing `_env_file=None` when instantiating Settings()
    directly in tests below.
    """
    for var in _RELEVANT_ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _make_settings(**overrides: object) -> Settings:
    """Instantiate Settings without picking up the repo's .env file."""
    return Settings(_env_file=None, **overrides)  # type: ignore[call-arg]


def test_production_empty_secret_key_raises() -> None:
    """DEBUG=False + empty SECRET_KEY must fail loudly with a helpful message."""
    with pytest.raises(ValueError) as exc_info:
        _make_settings(DEBUG=False, SECRET_KEY="")

    message = str(exc_info.value)
    assert "SECRET_KEY" in message
    assert "secrets.token_urlsafe" in message


def test_production_placeholder_secret_key_raises() -> None:
    """Historical placeholder must be rejected when DEBUG=False."""
    with pytest.raises(ValueError) as exc_info:
        _make_settings(
            DEBUG=False, SECRET_KEY="dev-secret-change-in-production"
        )

    assert "SECRET_KEY" in str(exc_info.value)


def test_production_real_secret_key_succeeds() -> None:
    """A real secret in production must instantiate cleanly."""
    real_key = "a" * 64
    settings = _make_settings(DEBUG=False, SECRET_KEY=real_key)
    assert settings.SECRET_KEY == real_key
    assert settings.DEBUG is False


def test_debug_empty_secret_key_synthesized() -> None:
    """DEBUG=True + empty SECRET_KEY must auto-generate a non-empty key."""
    settings = _make_settings(DEBUG=True, SECRET_KEY="")
    assert settings.SECRET_KEY != ""
    # token_urlsafe(32) -> ~43 chars of url-safe base64
    assert len(settings.SECRET_KEY) >= 32
    assert settings.DEBUG is True


def test_debug_provided_secret_key_preserved() -> None:
    """DEBUG=True + an explicit SECRET_KEY must be preserved verbatim."""
    explicit_key = "explicit-dev-key-xyz"
    settings = _make_settings(DEBUG=True, SECRET_KEY=explicit_key)
    assert settings.SECRET_KEY == explicit_key


def test_debug_placeholder_tolerated_with_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """DEBUG=True must tolerate the legacy placeholder but warn."""
    with caplog.at_level("WARNING", logger="app.core.settings"):
        settings = _make_settings(
            DEBUG=True, SECRET_KEY="dev-secret-change-in-production"
        )
    assert settings.SECRET_KEY == "dev-secret-change-in-production"
    assert any("historical placeholder" in rec.message for rec in caplog.records)


def test_default_debug_is_false() -> None:
    """Safe-by-default: DEBUG must default to False when env isn't set."""
    # We have to provide SECRET_KEY because DEBUG=False without it would raise.
    settings = _make_settings(SECRET_KEY="a" * 64)
    assert settings.DEBUG is False


def test_default_no_env_and_no_secret_key_raises() -> None:
    """With no env at all (default DEBUG=False, default SECRET_KEY=''), instantiation must raise.

    This is the regression guard for C4: a production deployment that forgets
    `SECRET_KEY` no longer boots silently with a known weak key.
    """
    with pytest.raises(ValueError):
        _make_settings()
