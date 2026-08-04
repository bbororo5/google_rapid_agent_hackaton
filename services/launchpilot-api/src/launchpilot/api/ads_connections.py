from __future__ import annotations

from typing import Annotated

import httpx
from fastapi import APIRouter, Cookie, Depends, HTTPException, Query, Response, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from launchpilot.application.ports import AdsConnector
from launchpilot.config import Settings
from launchpilot.domain.integrations import ExternalAccount, ExternalCampaign
from launchpilot.infrastructure.control_plane import ConnectedUser, SqliteControlPlane
from launchpilot.infrastructure.google_ads import GoogleAdsConnector
from launchpilot.infrastructure.google_oauth import GoogleOAuthClient
from launchpilot.infrastructure.meta_ads import MetaAdsConnector
from launchpilot.infrastructure.meta_oauth import MetaOAuthClient
from launchpilot.infrastructure.security import BrowserStateManager, InvalidSignedToken

from .auth import current_user
from .connections import ConnectionOutput
from .dependencies import (
    browser_state_manager,
    control_plane,
    google_oauth_client,
    meta_oauth_client,
    settings,
)

router = APIRouter(prefix="/connections", tags=["ad connections"])
ControlPlaneDependency = Annotated[SqliteControlPlane, Depends(control_plane)]
GoogleOAuthDependency = Annotated[GoogleOAuthClient, Depends(google_oauth_client)]
MetaOAuthDependency = Annotated[MetaOAuthClient, Depends(meta_oauth_client)]
UserDependency = Annotated[ConnectedUser, Depends(current_user)]
BrowserStateDependency = Annotated[BrowserStateManager, Depends(browser_state_manager)]
SettingsDependency = Annotated[Settings, Depends(settings)]

GOOGLE_ADS_STATE_COOKIE = "launchpilot_google_ads_state"
META_ADS_STATE_COOKIE = "launchpilot_meta_ads_state"
GOOGLE_ADS_SCOPES = ("https://www.googleapis.com/auth/adwords",)
META_ADS_SCOPES = ("ads_read",)


class ExternalAccountOutput(BaseModel):
    provider: str
    account_ref: str
    name: str
    currency_code: str | None
    timezone: str | None

    @classmethod
    def from_domain(cls, account: ExternalAccount) -> ExternalAccountOutput:
        return cls(
            provider=account.provider,
            account_ref=account.account_ref,
            name=account.name,
            currency_code=account.currency_code,
            timezone=account.timezone,
        )


class ExternalCampaignOutput(BaseModel):
    provider: str
    account_ref: str
    campaign_ref: str
    name: str
    status: str

    @classmethod
    def from_domain(cls, campaign: ExternalCampaign) -> ExternalCampaignOutput:
        return cls(
            provider=campaign.provider,
            account_ref=campaign.account_ref,
            campaign_ref=campaign.campaign_ref,
            name=campaign.name,
            status=campaign.status,
        )


def _set_state_cookie(
    response: RedirectResponse,
    *,
    name: str,
    value: str,
    secure: bool,
) -> None:
    response.set_cookie(
        name,
        value,
        max_age=600,
        httponly=True,
        secure=secure,
        samesite="lax",
    )


@router.get("/google-ads/authorize")
def start_google_ads_connection(
    user: UserDependency,
    oauth: GoogleOAuthDependency,
    browser_state: BrowserStateDependency,
    config: SettingsDependency,
) -> RedirectResponse:
    transaction = browser_state.issue("GOOGLE_ADS_CONNECT")
    response = RedirectResponse(
        oauth.authorization_url(
            state=transaction.state,
            scopes=GOOGLE_ADS_SCOPES,
            callback_path="/connections/google-ads/callback",
            code_challenge=transaction.code_challenge,
        )
    )
    _set_state_cookie(
        response,
        name=GOOGLE_ADS_STATE_COOKIE,
        value=transaction.cookie_value,
        secure=config.cookie_secure,
    )
    return response


@router.get("/google-ads/callback", response_model=ConnectionOutput)
def finish_google_ads_connection(
    response: Response,
    user: UserDependency,
    store: ControlPlaneDependency,
    oauth: GoogleOAuthDependency,
    browser_state: BrowserStateDependency,
    code: Annotated[str, Query(min_length=1)],
    state: Annotated[str, Query(min_length=1)],
    browser_cookie: Annotated[str | None, Cookie(alias=GOOGLE_ADS_STATE_COOKIE)] = None,
) -> ConnectionOutput:
    response.delete_cookie(GOOGLE_ADS_STATE_COOKIE)
    try:
        verifier = browser_state.consume(
            cookie_value=browser_cookie,
            state=state,
            purpose="GOOGLE_ADS_CONNECT",
        )
        token = oauth.exchange_code(
            code=code,
            callback_path="/connections/google-ads/callback",
            code_verifier=verifier,
        )
        connection = store.upsert_connection(
            user_id=user.id,
            provider="GOOGLE_ADS",
            token=token,
            granted_scopes=GOOGLE_ADS_SCOPES,
        )
    except InvalidSignedToken as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OAuth state is invalid or expired.",
        ) from error
    except httpx.HTTPError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Google Ads connection exchange failed.",
        ) from error
    return ConnectionOutput.from_domain(connection)


@router.get("/meta-ads/authorize")
def start_meta_ads_connection(
    user: UserDependency,
    oauth: MetaOAuthDependency,
    browser_state: BrowserStateDependency,
    config: SettingsDependency,
) -> RedirectResponse:
    transaction = browser_state.issue("META_ADS_CONNECT")
    response = RedirectResponse(
        oauth.authorization_url(
            state=transaction.state,
            scopes=META_ADS_SCOPES,
            callback_path="/connections/meta-ads/callback",
        )
    )
    _set_state_cookie(
        response,
        name=META_ADS_STATE_COOKIE,
        value=transaction.cookie_value,
        secure=config.cookie_secure,
    )
    return response


@router.get("/meta-ads/callback", response_model=ConnectionOutput)
def finish_meta_ads_connection(
    response: Response,
    user: UserDependency,
    store: ControlPlaneDependency,
    oauth: MetaOAuthDependency,
    browser_state: BrowserStateDependency,
    code: Annotated[str, Query(min_length=1)],
    state: Annotated[str, Query(min_length=1)],
    browser_cookie: Annotated[str | None, Cookie(alias=META_ADS_STATE_COOKIE)] = None,
) -> ConnectionOutput:
    response.delete_cookie(META_ADS_STATE_COOKIE)
    try:
        browser_state.consume(
            cookie_value=browser_cookie,
            state=state,
            purpose="META_ADS_CONNECT",
        )
        token = oauth.exchange_code(
            code=code, callback_path="/connections/meta-ads/callback"
        )
        connection = store.upsert_connection(
            user_id=user.id,
            provider="META_ADS",
            token=token,
            granted_scopes=META_ADS_SCOPES,
        )
    except InvalidSignedToken as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OAuth state is invalid or expired.",
        ) from error
    except httpx.HTTPError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Meta Ads connection exchange failed.",
        ) from error
    return ConnectionOutput.from_domain(connection)


def connector_for(provider: str, config: Settings) -> AdsConnector:
    if provider == "GOOGLE_ADS":
        return GoogleAdsConnector(
            developer_token=config.require_google_ads(),
            api_version=config.google_ads_api_version,
        )
    if provider == "META_ADS":
        return MetaAdsConnector(
            api_version=config.meta_graph_api_version,
            primary_conversion_action=config.meta_primary_conversion_action,
        )
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="Connection does not expose advertising campaigns.",
    )


def active_access_token(
    *,
    connection_id: str,
    user: ConnectedUser,
    store: SqliteControlPlane,
    google_oauth: GoogleOAuthClient,
) -> tuple[str, str]:
    stored = store.get_connection_token(connection_id=connection_id, user_id=user.id)
    if stored is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="platform connection not found",
        )
    connection, token = stored
    if google_oauth.access_token_expired(token):
        refresh_token = token.get("refresh_token")
        if connection.provider != "GOOGLE_ADS" or not isinstance(refresh_token, str):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Platform authorization expired. Reconnect the account.",
            )
        try:
            refreshed = google_oauth.refresh_access_token(refresh_token)
        except httpx.HTTPError as error:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Google Ads authorization refresh failed.",
            ) from error
        store.upsert_connection(
            user_id=user.id,
            provider=connection.provider,
            token=refreshed,
            granted_scopes=connection.granted_scopes,
            account_ref=connection.account_ref,
        )
        token = {**token, **refreshed}
    access_token = token.get("access_token")
    if not isinstance(access_token, str) or not access_token:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Connection cannot provide advertising read access.",
        )
    return connection.provider, access_token


@router.get("/{connection_id}/accounts", response_model=list[ExternalAccountOutput])
def list_ad_accounts(
    connection_id: str,
    user: UserDependency,
    store: ControlPlaneDependency,
    google_oauth: GoogleOAuthDependency,
    config: SettingsDependency,
) -> list[ExternalAccountOutput]:
    provider, access_token = active_access_token(
        connection_id=connection_id,
        user=user,
        store=store,
        google_oauth=google_oauth,
    )
    try:
        accounts = connector_for(provider, config).list_accounts(
            access_token=access_token
        )
    except (httpx.HTTPError, RuntimeError) as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Advertising account discovery failed: {error}",
        ) from error
    return [ExternalAccountOutput.from_domain(item) for item in accounts]


@router.get("/{connection_id}/campaigns", response_model=list[ExternalCampaignOutput])
def list_ad_campaigns(
    connection_id: str,
    account_ref: Annotated[str, Query(min_length=1)],
    user: UserDependency,
    store: ControlPlaneDependency,
    google_oauth: GoogleOAuthDependency,
    config: SettingsDependency,
) -> list[ExternalCampaignOutput]:
    provider, access_token = active_access_token(
        connection_id=connection_id,
        user=user,
        store=store,
        google_oauth=google_oauth,
    )
    try:
        campaigns = connector_for(provider, config).list_campaigns(
            access_token=access_token, account_ref=account_ref
        )
    except (httpx.HTTPError, RuntimeError) as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Advertising campaign discovery failed: {error}",
        ) from error
    return [ExternalCampaignOutput.from_domain(item) for item in campaigns]
