from __future__ import annotations

from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from launchpilot.infrastructure.control_plane import ConnectedUser, PlatformConnection, SqliteControlPlane
from launchpilot.infrastructure.google_oauth import GoogleOAuthClient

from .auth import current_user
from .dependencies import control_plane, google_oauth_client

router = APIRouter(prefix="/connections", tags=["connections"])
ControlPlaneDependency = Annotated[SqliteControlPlane, Depends(control_plane)]
OAuthDependency = Annotated[GoogleOAuthClient, Depends(google_oauth_client)]
UserDependency = Annotated[ConnectedUser, Depends(current_user)]
YOUTUBE_SCOPES = (
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
)


class ConnectionOutput(BaseModel):
    id: str
    provider: str
    account_ref: str | None
    granted_scopes: list[str]

    @classmethod
    def from_domain(cls, connection: PlatformConnection) -> "ConnectionOutput":
        return cls(
            id=connection.id,
            provider=connection.provider,
            account_ref=connection.account_ref,
            granted_scopes=list(connection.granted_scopes),
        )


@router.get("/youtube/authorize")
def start_youtube_connection(user: UserDependency, store: ControlPlaneDependency, oauth: OAuthDependency) -> RedirectResponse:
    transaction = store.create_transaction(purpose="YOUTUBE_CONNECT", user_id=user.id)
    return RedirectResponse(oauth.authorization_url(state=transaction.state, scopes=YOUTUBE_SCOPES, callback_path="/connections/youtube/callback"))


@router.get("/youtube/callback", response_model=ConnectionOutput)
def finish_youtube_connection(
    code: str = Query(min_length=1),
    state: str = Query(min_length=1),
    store: ControlPlaneDependency = None,  # type: ignore[assignment]
    oauth: OAuthDependency = None,  # type: ignore[assignment]
) -> ConnectionOutput:
    transaction = store.consume_transaction(state, "YOUTUBE_CONNECT")
    if transaction is None or transaction.user_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OAuth state is invalid or expired.")
    try:
        token = oauth.exchange_code(code=code, callback_path="/connections/youtube/callback")
        connection = store.upsert_connection(
            user_id=transaction.user_id,
            provider="YOUTUBE",
            token=token,
            granted_scopes=YOUTUBE_SCOPES,
        )
    except httpx.HTTPError as error:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="YouTube connection exchange failed.") from error
    except RuntimeError as error:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)) from error
    return ConnectionOutput.from_domain(connection)


@router.get("", response_model=list[ConnectionOutput])
def list_connections(user: UserDependency, store: ControlPlaneDependency) -> list[ConnectionOutput]:
    return [ConnectionOutput.from_domain(item) for item in store.list_connections(user.id)]
