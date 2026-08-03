from __future__ import annotations

from typing import Annotated

import httpx
from fastapi import APIRouter, Cookie, Depends, HTTPException, Query, Response, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from launchpilot.config import Settings
from launchpilot.infrastructure.control_plane import ConnectedUser, SqliteControlPlane
from launchpilot.infrastructure.google_oauth import GoogleOAuthClient

from .dependencies import control_plane, google_oauth_client, settings

router = APIRouter(prefix="/auth", tags=["auth"])
SettingsDependency = Annotated[Settings, Depends(settings)]
ControlPlaneDependency = Annotated[SqliteControlPlane, Depends(control_plane)]
OAuthDependency = Annotated[GoogleOAuthClient, Depends(google_oauth_client)]
SESSION_COOKIE = "launchpilot_session"
LOGIN_SCOPES = ("openid", "email", "profile")


class UserOutput(BaseModel):
    id: str
    email: str
    display_name: str | None

    @classmethod
    def from_domain(cls, user: ConnectedUser) -> "UserOutput":
        return cls(id=user.id, email=user.email, display_name=user.display_name)


def current_user(
    store: ControlPlaneDependency,
    session_id: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
) -> ConnectedUser:
    if session_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sign in is required.")
    user = store.get_user(session_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session is invalid.")
    return user


@router.get("/google/login")
def start_google_login(store: ControlPlaneDependency, oauth: OAuthDependency) -> RedirectResponse:
    transaction = store.create_transaction(purpose="LOGIN", user_id=None)
    return RedirectResponse(oauth.authorization_url(state=transaction.state, scopes=LOGIN_SCOPES, callback_path="/auth/google/callback"))


@router.get("/google/callback", response_model=UserOutput)
def finish_google_login(
    response: Response,
    code: str = Query(min_length=1),
    state: str = Query(min_length=1),
    store: ControlPlaneDependency = None,  # type: ignore[assignment]
    oauth: OAuthDependency = None,  # type: ignore[assignment]
) -> UserOutput:
    if store.consume_transaction(state, "LOGIN") is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OAuth state is invalid or expired.")
    try:
        token = oauth.exchange_code(code=code, callback_path="/auth/google/callback")
        info = oauth.user_info(str(token["access_token"]))
    except (httpx.HTTPError, KeyError) as error:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Google login exchange failed.") from error
    user = store.upsert_user(google_subject=info["sub"], email=info["email"], display_name=info.get("name"))
    response.set_cookie(SESSION_COOKIE, user.id, httponly=True, samesite="lax")
    return UserOutput.from_domain(user)


@router.get("/me", response_model=UserOutput)
def read_current_user(user: Annotated[ConnectedUser, Depends(current_user)]) -> UserOutput:
    return UserOutput.from_domain(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response) -> Response:
    response.delete_cookie(SESSION_COOKIE)
    return response
