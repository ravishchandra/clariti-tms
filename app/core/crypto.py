"""Symmetric encryption helpers for at-rest secrets stored in DB columns.

We use Fernet (AES-128-CBC + HMAC-SHA256) from `cryptography`. The key comes
from `Settings.FERNET_KEY`. See `app/core/settings.py` for the bootstrap rules
(required in production, transient in DEBUG).

These helpers are deliberately tiny: callers shouldn't be reaching for
`Fernet` directly. Both `encrypt` and `decrypt` accept and return `None`
unchanged so call sites for nullable secret columns stay simple.
"""

from __future__ import annotations

from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from app.core.settings import get_settings


@lru_cache(maxsize=1)
def _cipher() -> Fernet:
    """Cached Fernet instance built from FERNET_KEY."""
    key = get_settings().FERNET_KEY
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt(plaintext: str | None) -> str | None:
    """Encrypt a string; `None` passes through unchanged.

    Returns the Fernet token as a url-safe ASCII string, safe to store in a
    Postgres `text` column.
    """
    if plaintext is None:
        return None
    if not isinstance(plaintext, str):
        raise TypeError(f"encrypt() expects str or None, got {type(plaintext).__name__}")
    return _cipher().encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt(ciphertext: str | None) -> str | None:
    """Decrypt a Fernet token previously produced by `encrypt`.

    Returns `None` if the input is `None`. Raises `cryptography.fernet.InvalidToken`
    if the value cannot be decrypted (wrong key, corrupted ciphertext, or — most
    commonly during the C3 migration — a legacy plaintext value still sitting
    in the column). Callers that must tolerate legacy plaintext should catch
    `InvalidToken` and fall back; we don't do that silently here because it would
    hide real key-rotation bugs.
    """
    if ciphertext is None:
        return None
    if not isinstance(ciphertext, str):
        raise TypeError(f"decrypt() expects str or None, got {type(ciphertext).__name__}")
    return _cipher().decrypt(ciphertext.encode("ascii")).decode("utf-8")


__all__ = ["encrypt", "decrypt", "InvalidToken"]
