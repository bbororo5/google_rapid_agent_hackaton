from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ConnectedUser:
    id: str
    google_subject: str
    email: str
    display_name: str | None


@dataclass(frozen=True, slots=True)
class PlatformConnection:
    id: str
    user_id: str
    provider: str
    account_ref: str | None
    granted_scopes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class WorkspaceAccess:
    id: str
    name: str
    role: str
