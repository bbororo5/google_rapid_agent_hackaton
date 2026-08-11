from typing import Protocol

from ..models import WorkspaceAccess


class WorkspaceDirectory(Protocol):
    """Workspace listing and authorization capability offered to other modules."""

    def list_workspaces(self, user_id: str) -> list[WorkspaceAccess]: ...
    def has_workspace_access(self, *, user_id: str, workspace_id: str) -> bool: ...
