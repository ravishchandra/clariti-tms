"""On-demand provider connection check (Settings → Providers "Test connection").

Validates a provider + credential with the cheapest authenticated call we can
make, so an admin can confirm a key works before trusting it. Returns
``(ok, error)`` — error messages are deliberately short and never echo the raw
provider response, to avoid leaking account details. Any unexpected failure is
funnelled into ``(False, message)`` rather than bubbling a 500.

Note: named ``connection_check`` (not ``*_test``) and the public function
``check_*`` (not ``test_*``) so pytest never mistakes this app module for a
test file.
"""

from __future__ import annotations

import httpx

_TIMEOUT = httpx.Timeout(15.0)


def _short(exc: Exception) -> str:
    msg = str(exc).strip() or exc.__class__.__name__
    return msg[:200]


async def check_provider_connection(
    provider: str,
    *,
    api_key: str | None = None,
    ollama_host: str | None = None,
) -> tuple[bool, str | None]:
    """Return ``(ok, error)``. ``ok=True`` means the credential authenticated."""
    try:
        if provider == "anthropic":
            return await _check_anthropic(api_key)
        if provider == "openai":
            return await _check_openai_compatible(api_key, base_url=None)
        if provider == "openrouter":
            return await _check_openai_compatible(api_key, base_url="https://openrouter.ai/api/v1")
        if provider == "ollama":
            return await _check_ollama(ollama_host)
        if provider == "deepl":
            return await _check_deepl(api_key)
        return False, f"Unknown provider {provider!r}."
    except Exception as exc:  # noqa: BLE001 — any failure is a failed check, not a 500
        return False, _short(exc)


async def _check_anthropic(api_key: str | None) -> tuple[bool, str | None]:
    if not api_key:
        return False, "No Anthropic API key configured."
    import anthropic

    client = anthropic.AsyncAnthropic(api_key=api_key, timeout=15.0)
    try:
        await client.models.list()
    except anthropic.AuthenticationError:
        return False, "Authentication failed — check the Anthropic API key."
    except anthropic.APIError as exc:
        return False, f"Anthropic API error: {_short(exc)}"
    return True, None


async def _check_openai_compatible(api_key: str | None, *, base_url: str | None) -> tuple[bool, str | None]:
    if not api_key:
        return False, "No API key configured."
    import openai

    client = (
        openai.AsyncOpenAI(api_key=api_key, base_url=base_url, timeout=15.0)
        if base_url
        else openai.AsyncOpenAI(api_key=api_key, timeout=15.0)
    )
    try:
        await client.models.list()
    except openai.AuthenticationError:
        return False, "Authentication failed — check the API key."
    except openai.APIError as exc:
        return False, f"API error: {_short(exc)}"
    return True, None


async def _check_ollama(host: str | None) -> tuple[bool, str | None]:
    base = (host or "http://localhost:11434").rstrip("/")
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        try:
            resp = await client.get(f"{base}/api/tags")
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            return False, f"Couldn't reach Ollama at {base}: {_short(exc)}"
    return True, None


async def _check_deepl(api_key: str | None) -> tuple[bool, str | None]:
    if not api_key:
        return False, "No DeepL API key configured."
    # Free-tier keys end in ":fx" and use the api-free host.
    base = "https://api-free.deepl.com/v2" if api_key.endswith(":fx") else "https://api.deepl.com/v2"
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        try:
            resp = await client.get(f"{base}/usage", headers={"Authorization": f"DeepL-Auth-Key {api_key}"})
            if resp.status_code in (401, 403):
                return False, "Authentication failed — check the DeepL API key."
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            return False, f"Couldn't reach DeepL: {_short(exc)}"
    return True, None
