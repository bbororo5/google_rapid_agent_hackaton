from __future__ import annotations

from uuid import UUID

from .ports import IdentityStore


class IdentityWorkspaceAccessReader:
    def __init__(self, identity_store: IdentityStore) -> None:
        self._identity_store = identity_store

    def allows(self, *, user_id: UUID, workspace_id: UUID) -> bool:
        return self._identity_store.has_workspace_access(
            user_id=str(user_id), workspace_id=str(workspace_id)
        )
