from __future__ import annotations

from typing import Annotated

import httpx
from fastapi import APIRouter, Cookie, Depends, HTTPException, Query, Response, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from launchpilot.bootstrap.config import Settings
from launchpilot.bootstrap.wiring import (
    browser_state_manager,
    control_plane,
    google_oauth_client,
    session_manager,
    settings,
)
from launchpilot.infrastructure.control_plane import ConnectedUser, PostgresControlPlane
from launchpilot.infrastructure.google_oauth import GoogleOAuthClient
from launchpilot.infrastructure.security import (
    BrowserStateManager,
    InvalidSignedToken,
    SessionManager,
)

router = APIRouter(prefix="/auth", tags=["auth"])
SettingsDependency = Annotated[Settings, Depends(settings)]
ControlPlaneDependency = Annotated[PostgresControlPlane, Depends(control_plane)]
OAuthDependency = Annotated[GoogleOAuthClient, Depends(google_oauth_client)]
BrowserStateDependency = Annotated[BrowserStateManager, Depends(browser_state_manager)]
SessionDependency = Annotated[SessionManager, Depends(session_manager)]
SESSION_COOKIE = "launchpilot_session"
LOGIN_STATE_COOKIE = "launchpilot_login_state"
LOGIN_SCOPES = ("openid", "email", "profile")


class UserOutput(BaseModel):
    id: str
    email: str
    display_name: str | None

    @classmethod
    def from_domain(cls, user: ConnectedUser) -> UserOutput:
        return cls(id=user.id, email=user.email, display_name=user.display_name)


def current_user(
    store: ControlPlaneDependency,
    sessions: SessionDependency,
    session_id: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
) -> ConnectedUser:
    if session_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Sign in is required."
        )
    try:
        user_id = sessions.read(session_id)
    except InvalidSignedToken as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Session is invalid."
        ) from error
    user = store.get_user(user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Session is invalid."
        )
    return user


@router.get("/google/login")
def start_google_login(
    oauth: OAuthDependency,
    browser_state: BrowserStateDependency,
    config: SettingsDependency,
) -> RedirectResponse:
    transaction = browser_state.issue("LOGIN")
    response = RedirectResponse(
        oauth.authorization_url(
            state=transaction.state,
            scopes=LOGIN_SCOPES,
            callback_path="/auth/google/callback",
            code_challenge=transaction.code_challenge,
        )
    )
    response.set_cookie(
        LOGIN_STATE_COOKIE,
        transaction.cookie_value,
        max_age=600,
        httponly=True,
        secure=config.cookie_secure,
        samesite="lax",
    )
    return response


@router.get("/google/callback", response_model=UserOutput)
def finish_google_login(
    response: Response,
    store: ControlPlaneDependency,
    oauth: OAuthDependency,
    browser_state: BrowserStateDependency,
    sessions: SessionDependency,
    config: SettingsDependency,
    code: Annotated[str, Query(min_length=1)],
    state: Annotated[str, Query(min_length=1)],
    browser_cookie: Annotated[str | None, Cookie(alias=LOGIN_STATE_COOKIE)] = None,
) -> UserOutput:
    response.delete_cookie(LOGIN_STATE_COOKIE)
    try:
        code_verifier = browser_state.consume(
            cookie_value=browser_cookie, state=state, purpose="LOGIN"
        )
    except InvalidSignedToken as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OAuth state is invalid or expired.",
        ) from error
    try:
        token = oauth.exchange_code(
            code=code,
            callback_path="/auth/google/callback",
            code_verifier=code_verifier,
        )
        info = oauth.user_info(str(token["access_token"]))
    except (httpx.HTTPError, KeyError) as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Google login exchange failed.",
        ) from error
    user = store.upsert_user(
        google_subject=info["sub"], email=info["email"], display_name=info.get("name")
    )
    response.set_cookie(
        SESSION_COOKIE,
        sessions.issue(user.id),
        max_age=43_200,
        httponly=True,
        secure=config.cookie_secure,
        samesite="lax",
    )
    return UserOutput.from_domain(user)


@router.get("/me", response_model=UserOutput)
def read_current_user(
    user: Annotated[ConnectedUser, Depends(current_user)],
) -> UserOutput:
    return UserOutput.from_domain(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response) -> Response:
    response.delete_cookie(SESSION_COOKIE)
    return response
