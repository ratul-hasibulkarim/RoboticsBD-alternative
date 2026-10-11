"""Shared gate for official-API clients: legal approval + configured credentials."""

from __future__ import annotations

from crawler.registry import SourceConfig


class MissingCredentialsError(RuntimeError):
    pass


def require_api_access(source: SourceConfig, *secrets: str) -> None:
    source.require_approved()  # raises NotApprovedError
    if source.type != "api":
        raise ValueError(f"{source.name} is not an API source")
    if not all(secrets):
        raise MissingCredentialsError(f"credentials for {source.name} are not configured")
