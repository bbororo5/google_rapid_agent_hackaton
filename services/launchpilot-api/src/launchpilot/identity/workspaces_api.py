from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from launchpilot.bootstrap.wiring import identity_store
from launchpilot.identity.models import ConnectedUser, WorkspaceAccess
from launchpilot.identity.ports import IdentityStore

from .auth_api import current_user

router = APIRouter(prefix="/workspaces", tags=["workspaces"])
UserDependency = Annotated[ConnectedUser, Depends(current_user)]
IdentityStoreDependency = Annotated[IdentityStore, Depends(identity_store)]


class WorkspaceOutput(BaseModel):
    id: str
    name: str
    role: str

    @classmethod
    def from_domain(cls, workspace: WorkspaceAccess) -> "WorkspaceOutput":
        return cls(id=workspace.id, name=workspace.name, role=workspace.role)


@router.get("", response_model=list[WorkspaceOutput])
def list_workspaces(
    user: UserDependency, store: IdentityStoreDependency
) -> list[WorkspaceOutput]:
    return [
        WorkspaceOutput.from_domain(item) for item in store.list_workspaces(user.id)
    ]
