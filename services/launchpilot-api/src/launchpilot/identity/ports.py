from typing import Protocol

from launchpilot.campaigns.public import ExternalCampaignBinding

from .models import ConnectedUser, PlatformConnection, WorkspaceAccess


class IdentityStore(Protocol):
    def upsert_user(
        self, *, google_subject: str, email: str, display_name: str | None
    ) -> ConnectedUser: ...

    def get_user(self, user_id: str) -> ConnectedUser | None: ...
    def list_workspaces(self, user_id: str) -> list[WorkspaceAccess]: ...
    def has_workspace_access(self, *, user_id: str, workspace_id: str) -> bool: ...

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

    def upsert_campaign_binding(
        self,
        *,
        user_id: str,
        campaign_id: str,
        connection_id: str,
        external_account_ref: str,
        external_campaign_ref: str,
        display_name: str,
        currency_code: str | None = None,
        timezone: str | None = None,
        attribution_setting: str | None = None,
    ) -> ExternalCampaignBinding: ...

    def list_campaign_bindings(
        self, *, user_id: str, campaign_id: str
    ) -> tuple[ExternalCampaignBinding, ...]: ...


class WorkspaceDirectory(Protocol):
    """Narrow collaboration boundary for workspace listing and authorization."""

    def list_workspaces(self, user_id: str) -> list[WorkspaceAccess]: ...
    def has_workspace_access(self, *, user_id: str, workspace_id: str) -> bool: ...
