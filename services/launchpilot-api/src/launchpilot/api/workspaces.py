from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from launchpilot.infrastructure.control_plane import (
    ConnectedUser,
    PostgresControlPlane,
    WorkspaceAccess,
)

from .auth import current_user
from .dependencies import control_plane

router = APIRouter(prefix="/workspaces", tags=["workspaces"])
UserDependency = Annotated[ConnectedUser, Depends(current_user)]
ControlPlaneDependency = Annotated[PostgresControlPlane, Depends(control_plane)]


class WorkspaceOutput(BaseModel):
    id: str
    name: str
    role: str

    @classmethod
    def from_domain(cls, workspace: WorkspaceAccess) -> "WorkspaceOutput":
        return cls(id=workspace.id, name=workspace.name, role=workspace.role)


@router.get("", response_model=list[WorkspaceOutput])
def list_workspaces(
    user: UserDependency, store: ControlPlaneDependency
) -> list[WorkspaceOutput]:
    return [
        WorkspaceOutput.from_domain(item) for item in store.list_workspaces(user.id)
    ]
