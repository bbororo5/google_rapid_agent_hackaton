from __future__ import annotations

from typing import Annotated

import httpx
from fastapi import APIRouter, Cookie, Depends, HTTPException, Query, Response, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from launchpilot.config import Settings
from launchpilot.infrastructure.control_plane import (
    ConnectedUser,
    PlatformConnection,
    SqliteControlPlane,
)
from launchpilot.infrastructure.google_oauth import GoogleOAuthClient
from launchpilot.infrastructure.security import BrowserStateManager, InvalidSignedToken

from .auth import current_user
from .dependencies import (
    browser_state_manager,
    control_plane,
    google_oauth_client,
    settings,
)

router = APIRouter(prefix="/connections", tags=["connections"])
ControlPlaneDependency = Annotated[SqliteControlPlane, Depends(control_plane)]
OAuthDependency = Annotated[GoogleOAuthClient, Depends(google_oauth_client)]
UserDependency = Annotated[ConnectedUser, Depends(current_user)]
BrowserStateDependency = Annotated[BrowserStateManager, Depends(browser_state_manager)]
SettingsDependency = Annotated[Settings, Depends(settings)]
YOUTUBE_STATE_COOKIE = "launchpilot_youtube_state"
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
    def from_domain(cls, connection: PlatformConnection) -> ConnectionOutput:
        return cls(
            id=connection.id,
            provider=connection.provider,
            account_ref=connection.account_ref,
            granted_scopes=list(connection.granted_scopes),
        )


@router.get("/youtube/authorize")
def start_youtube_connection(
    user: UserDependency,
    oauth: OAuthDependency,
    browser_state: BrowserStateDependency,
    config: SettingsDependency,
) -> RedirectResponse:
    transaction = browser_state.issue("YOUTUBE_CONNECT")
    response = RedirectResponse(
        oauth.authorization_url(
            state=transaction.state,
            scopes=YOUTUBE_SCOPES,
            callback_path="/connections/youtube/callback",
            code_challenge=transaction.code_challenge,
        )
    )
    response.set_cookie(
        YOUTUBE_STATE_COOKIE,
        transaction.cookie_value,
        max_age=600,
        httponly=True,
        secure=config.cookie_secure,
        samesite="lax",
    )
    return response


@router.get("/youtube/callback", response_model=ConnectionOutput)
def finish_youtube_connection(
    response: Response,
    user: UserDependency,
    store: ControlPlaneDependency,
    oauth: OAuthDependency,
    browser_state: BrowserStateDependency,
    code: Annotated[str, Query(min_length=1)],
    state: Annotated[str, Query(min_length=1)],
    browser_cookie: Annotated[str | None, Cookie(alias=YOUTUBE_STATE_COOKIE)] = None,
) -> ConnectionOutput:
    response.delete_cookie(YOUTUBE_STATE_COOKIE)
    try:
        code_verifier = browser_state.consume(
            cookie_value=browser_cookie,
            state=state,
            purpose="YOUTUBE_CONNECT",
        )
    except InvalidSignedToken as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OAuth state is invalid or expired.",
        ) from error
    try:
        token = oauth.exchange_code(
            code=code,
            callback_path="/connections/youtube/callback",
            code_verifier=code_verifier,
        )
        connection = store.upsert_connection(
            user_id=user.id,
            provider="YOUTUBE",
            token=token,
            granted_scopes=YOUTUBE_SCOPES,
        )
    except httpx.HTTPError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="YouTube connection exchange failed.",
        ) from error
    except RuntimeError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)
        ) from error
    return ConnectionOutput.from_domain(connection)


@router.get("", response_model=list[ConnectionOutput])
def list_connections(
    user: UserDependency, store: ControlPlaneDependency
) -> list[ConnectionOutput]:
    return [
        ConnectionOutput.from_domain(item) for item in store.list_connections(user.id)
    ]
