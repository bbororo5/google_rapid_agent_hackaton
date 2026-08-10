from __future__ import annotations

from uuid import UUID

from .control_plane import PostgresControlPlane


class ControlPlaneWorkspaceAccessReader:
    def __init__(self, control_plane: PostgresControlPlane) -> None:
        self._control_plane = control_plane

    def allows(self, *, user_id: UUID, workspace_id: UUID) -> bool:
        return self._control_plane.has_workspace_access(
            user_id=str(user_id), workspace_id=str(workspace_id)
        )
