from typing import Protocol

from launchpilot.campaigns.contracts.bindings import CampaignBindingDirectory

from .contracts.workspaces import WorkspaceDirectory
from .models import ConnectedUser, PlatformConnection


class UserIdentityStore(Protocol):
    def upsert_user(
        self, *, google_subject: str, email: str, display_name: str | None
    ) -> ConnectedUser: ...

    def get_user(self, user_id: str) -> ConnectedUser | None: ...


class PlatformConnectionStore(Protocol):
    def upsert_connection(
        self,
        *,
        user_id: str,
        provider: str,
        token: dict[str, object],
        granted_scopes: tuple[str, ...],
        account_ref: str | None = None,
    ) -> PlatformConnection: ...

    def list_connections(self, user_id: str) -> list[PlatformConnection]: ...
    def get_connection_token(
        self, *, connection_id: str, user_id: str
    ) -> tuple[PlatformConnection, dict[str, object]] | None: ...


class IdentityStore(
    UserIdentityStore,
    WorkspaceDirectory,
    PlatformConnectionStore,
    CampaignBindingDirectory,
    Protocol,
):
    """Composite implemented by persistence; consumers depend on narrower roles."""
