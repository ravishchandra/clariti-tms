"""Tests for app.integrations.github.webhook.handle_github_push.

Focus: installation_id resolution — the bug C5 fixed. We assert that
``handle_github_push`` derives the installation id from the Repository row when
present, falls back to ``payload['installation']['id']``, and refuses to mint
a token when neither is available.

We mock ``get_installation_token`` and the surrounding GitHub HTTP client so
tests don't touch real GitHub.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.integrations.github import webhook as gh_webhook
from app.models import Repository


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_repository(
    *,
    installation_id: int | None,
    project_id: uuid.UUID | None = None,
) -> Repository:
    """Build a Repository with the bare minimum fields the webhook uses.

    We intentionally don't go through the DB — the webhook just reads
    attributes on the Repository instance.
    """
    repo = Repository()
    repo.id = uuid.uuid4()
    repo.project_id = project_id or uuid.uuid4()
    repo.name = "test-repo"
    repo.platform = "web"
    repo.file_format = "i18next"
    repo.plural_convention = "icu"
    repo.github_repo = "acme/example"
    repo.github_path = "locales/"
    repo.source_file = "locales/en.json"
    repo.github_installation_id = installation_id
    repo.default_branch = "main"
    # Empty project — handle_github_push will see target_locales=[]
    repo.project = None
    return repo


def _push_payload(
    *,
    after: str = "deadbeef",
    installation_id: int | None = None,
    changed_files: list[str] | None = None,
) -> dict:
    commits = [
        {
            "added": [],
            "removed": [],
            "modified": changed_files or ["locales/en.json"],
        }
    ]
    body: dict = {
        "ref": "refs/heads/main",
        "after": after,
        "commits": commits,
        "repository": {"full_name": "acme/example"},
    }
    if installation_id is not None:
        body["installation"] = {"id": installation_id}
    return body


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestHandleGithubPushInstallationResolution:
    @pytest.mark.asyncio
    async def test_uses_repository_installation_id_when_set(self) -> None:
        repo = _make_repository(installation_id=4242)
        payload = _push_payload(installation_id=9999)  # payload differs

        token_mock = AsyncMock(return_value="ghs_from_repo_install")
        client_mock = MagicMock()
        client_mock.get_file_content = AsyncMock(return_value="{}")
        client_cls_mock = MagicMock(return_value=client_mock)

        with (
            patch(
                "app.integrations.github.auth.get_installation_token",
                token_mock,
            ),
            patch(
                "app.integrations.github.webhook.GitHubClient",
                client_cls_mock,
            ),
            patch(
                "app.integrations.github.webhook.parse_file",
                return_value=MagicMock(keys=[]),
            ),
            patch(
                "app.integrations.github.webhook.upsert_keys",
                AsyncMock(),
            ),
            patch(
                "app.integrations.github.webhook.assemble_batches",
                AsyncMock(),
            ),
        ):
            db = MagicMock()
            await gh_webhook.handle_github_push(db, payload, repo)

        # Repository's installation_id wins over payload's.
        token_mock.assert_awaited_once_with(4242)
        # Token is passed to the GitHubClient — not GITHUB_WEBHOOK_SECRET.
        client_cls_mock.assert_called_once_with(token="ghs_from_repo_install")

    @pytest.mark.asyncio
    async def test_falls_back_to_payload_installation_id(self) -> None:
        repo = _make_repository(installation_id=None)
        payload = _push_payload(installation_id=8888)

        token_mock = AsyncMock(return_value="ghs_from_payload_install")
        client_mock = MagicMock()
        client_mock.get_file_content = AsyncMock(return_value="{}")
        client_cls_mock = MagicMock(return_value=client_mock)

        with (
            patch(
                "app.integrations.github.auth.get_installation_token",
                token_mock,
            ),
            patch(
                "app.integrations.github.webhook.GitHubClient",
                client_cls_mock,
            ),
            patch(
                "app.integrations.github.webhook.parse_file",
                return_value=MagicMock(keys=[]),
            ),
            patch(
                "app.integrations.github.webhook.upsert_keys",
                AsyncMock(),
            ),
            patch(
                "app.integrations.github.webhook.assemble_batches",
                AsyncMock(),
            ),
        ):
            db = MagicMock()
            await gh_webhook.handle_github_push(db, payload, repo)

        token_mock.assert_awaited_once_with(8888)
        client_cls_mock.assert_called_once_with(token="ghs_from_payload_install")

    @pytest.mark.asyncio
    async def test_skips_when_no_installation_id_anywhere(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        repo = _make_repository(installation_id=None)
        payload = _push_payload(installation_id=None)

        token_mock = AsyncMock()
        client_cls_mock = MagicMock()

        with (
            patch(
                "app.integrations.github.auth.get_installation_token",
                token_mock,
            ),
            patch(
                "app.integrations.github.webhook.GitHubClient",
                client_cls_mock,
            ),
            caplog.at_level("ERROR"),
        ):
            db = MagicMock()
            await gh_webhook.handle_github_push(db, payload, repo)

        # No token minted, no client constructed.
        token_mock.assert_not_awaited()
        client_cls_mock.assert_not_called()
        # Structured error logged so operators can find the gap.
        assert any(
            "no installation_id available" in rec.message for rec in caplog.records
        )

    @pytest.mark.asyncio
    async def test_webhook_secret_is_not_passed_as_bearer_token(self) -> None:
        """Regression test for C5: GITHUB_WEBHOOK_SECRET must never be used as
        a bearer token for GitHub API calls."""
        repo = _make_repository(installation_id=1234)
        payload = _push_payload(installation_id=1234)

        token_mock = AsyncMock(return_value="ghs_real_install_token")
        client_mock = MagicMock()
        client_mock.get_file_content = AsyncMock(return_value="{}")
        client_cls_mock = MagicMock(return_value=client_mock)

        with (
            patch(
                "app.integrations.github.auth.get_installation_token",
                token_mock,
            ),
            patch(
                "app.integrations.github.webhook.GitHubClient",
                client_cls_mock,
            ),
            patch(
                "app.integrations.github.webhook.parse_file",
                return_value=MagicMock(keys=[]),
            ),
            patch(
                "app.integrations.github.webhook.upsert_keys",
                AsyncMock(),
            ),
            patch(
                "app.integrations.github.webhook.assemble_batches",
                AsyncMock(),
            ),
        ):
            from app.core.settings import get_settings

            db = MagicMock()
            settings = get_settings()
            # Set a recognizable webhook secret. Test asserts it's NEVER passed.
            secret_marker = "WEBHOOK_SECRET_SHOULD_NEVER_REACH_GITHUB_API"
            original = settings.GITHUB_WEBHOOK_SECRET
            settings.GITHUB_WEBHOOK_SECRET = secret_marker
            try:
                await gh_webhook.handle_github_push(db, payload, repo)
            finally:
                settings.GITHUB_WEBHOOK_SECRET = original

        # Confirm the marker is nowhere in any GitHubClient invocation.
        for call in client_cls_mock.call_args_list:
            assert secret_marker not in str(call)
        client_cls_mock.assert_called_once_with(token="ghs_real_install_token")


class TestVerifyGithubSignature:
    """Sanity: signature verification (HMAC) still works after the refactor."""

    def test_valid_signature_accepted(self) -> None:
        import hashlib
        import hmac as _hmac

        body = b'{"hello":"world"}'
        secret = "topsecret"
        sig = _hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        assert gh_webhook.verify_github_signature(body, f"sha256={sig}", secret)

    def test_wrong_signature_rejected(self) -> None:
        assert not gh_webhook.verify_github_signature(
            b'{"x":1}', "sha256=deadbeef", "topsecret"
        )

    def test_missing_prefix_rejected(self) -> None:
        assert not gh_webhook.verify_github_signature(b"{}", "deadbeef", "s")
