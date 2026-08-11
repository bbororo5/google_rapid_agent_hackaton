from __future__ import annotations

from uuid import UUID

from .contracts.workspaces import WorkspaceDirectory


class IdentityWorkspaceAccessReader:
    def __init__(self, identity_store: WorkspaceDirectory) -> None:
        self._identity_store = identity_store

    def allows(self, *, user_id: UUID, workspace_id: UUID) -> bool:
        return self._identity_store.has_workspace_access(
            user_id=str(user_id), workspace_id=str(workspace_id)
        )
