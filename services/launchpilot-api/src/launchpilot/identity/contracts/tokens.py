from typing import Protocol


class GoogleTokenLifecycle(Protocol):
    """Google token behavior required by the connection access component."""

    def access_token_expired(self, token: dict[str, object]) -> bool: ...

    def refresh_access_token(self, refresh_token: str) -> dict[str, object]: ...
