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


@pytest.mark.parametrize(
    "placeholder",
    [
        "dev-secret-change-in-production",  # the old code default
        "change-me-in-production",  # the old .env.example value (C4 codex find)
    ],
)
def test_production_placeholder_secret_key_raises(placeholder: str) -> None:
    """Every known historical placeholder must be rejected when DEBUG=False."""
    with pytest.raises(ValueError) as exc_info:
        _make_settings(DEBUG=False, SECRET_KEY=placeholder)

    msg = str(exc_info.value)
    assert "SECRET_KEY" in msg
    assert placeholder in msg


@pytest.mark.parametrize(
    "trivial",
    [
        "x",
        "password",
        "12345",
        "short-key",  # 9 chars
        "a" * 31,  # just below the floor
        "   ",  # whitespace only — stripped to ""
        "\t",
    ],
)
def test_production_trivial_secret_key_raises(trivial: str) -> None:
    """Short / blank-looking secrets must not pass production validation."""
    with pytest.raises(ValueError):
        _make_settings(DEBUG=False, SECRET_KEY=trivial)


def test_production_real_secret_key_succeeds() -> None:
    """A real secret in production must instantiate cleanly."""
    real_key = "a" * 64
    settings = _make_settings(DEBUG=False, SECRET_KEY=real_key)
    assert settings.SECRET_KEY == real_key
    assert settings.DEBUG is False


def test_production_min_length_secret_key_succeeds() -> None:
    """Exactly _MIN_SECRET_KEY_LENGTH (32) chars must pass the floor."""
    key = "a" * 32
    settings = _make_settings(DEBUG=False, SECRET_KEY=key)
    assert settings.SECRET_KEY == key


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
        settings = _make_settings(DEBUG=True, SECRET_KEY="dev-secret-change-in-production")
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


def test_get_settings_rejects_env_backed_bad_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The cached `get_settings()` entrypoint must run the validator too.

    Previously the test suite only exercised `Settings()` directly, leaving open
    the question of whether env-backed loads (the real production path) honor
    the validator. This proves they do.
    """
    monkeypatch.setenv("DEBUG", "false")
    monkeypatch.setenv("SECRET_KEY", "change-me-in-production")
    # Avoid the repo's .env file leaking values into env-backed construction
    monkeypatch.chdir("/")
    with pytest.raises(ValueError):
        get_settings()
    # Failed construction must not poison the cache: a later good call succeeds.
    get_settings.cache_clear()
    monkeypatch.setenv("SECRET_KEY", "a" * 64)
    settings = get_settings()
    assert settings.SECRET_KEY == "a" * 64
    assert settings.DEBUG is False


def test_get_settings_accepts_env_backed_dev(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`get_settings()` in DEBUG=true with an empty key must synthesize one."""
    monkeypatch.setenv("DEBUG", "true")
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.chdir("/")
    settings = get_settings()
    assert settings.DEBUG is True
    assert len(settings.SECRET_KEY) >= 32
