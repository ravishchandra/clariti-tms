from __future__ import annotations

from typing import Callable, Protocol, runtime_checkable

from app.models import Repository


@runtime_checkable
class SourceAdapter(Protocol):
    async def fetch_source_strings(self, repository: Repository) -> dict[str, str]: ...

    async def subscribe_to_changes(self, repository: Repository, callback: Callable) -> None: ...


@runtime_checkable
class PublicationAdapter(Protocol):
    async def publish_translations(
        self,
        repository: Repository,
        translations_by_locale: dict[str, dict[str, str]],
        branch_name: str,
    ) -> str:  # returns PR URL
        ...
