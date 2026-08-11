from __future__ import annotations

from typing import Annotated

import httpx
from fastapi import APIRouter, Cookie, Depends, HTTPException, Query, Response, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from launchpilot.application.ingestion import PlatformAccessError
from launchpilot.bootstrap.config import Settings
from launchpilot.bootstrap.wiring import (
    ads_connector_factory,
    browser_state_manager,
    control_plane,
    google_oauth_client,
    meta_oauth_client,
    platform_access_tokens,
    settings,
)
from launchpilot.domain.integrations import ExternalAccount, ExternalCampaign
from launchpilot.infrastructure.ads_factory import AdsConnectorFactory
from launchpilot.infrastructure.control_plane import ConnectedUser, PostgresControlPlane
from launchpilot.infrastructure.google_oauth import GoogleOAuthClient
from launchpilot.infrastructure.meta_oauth import MetaOAuthClient
from launchpilot.infrastructure.platform_access import PlatformAccessTokenProvider
from launchpilot.infrastructure.security import BrowserStateManager, InvalidSignedToken

from .auth import current_user
from .connections import ConnectionOutput
from .platform_errors import platform_access_http_error

router = APIRouter(prefix="/connections", tags=["ad connections"])
ControlPlaneDependency = Annotated[PostgresControlPlane, Depends(control_plane)]
GoogleOAuthDependency = Annotated[GoogleOAuthClient, Depends(google_oauth_client)]
MetaOAuthDependency = Annotated[MetaOAuthClient, Depends(meta_oauth_client)]
UserDependency = Annotated[ConnectedUser, Depends(current_user)]
BrowserStateDependency = Annotated[BrowserStateManager, Depends(browser_state_manager)]
SettingsDependency = Annotated[Settings, Depends(settings)]
AccessTokensDependency = Annotated[
    PlatformAccessTokenProvider, Depends(platform_access_tokens)
]
AdsConnectorsDependency = Annotated[AdsConnectorFactory, Depends(ads_connector_factory)]

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


@router.get("/{connection_id}/accounts", response_model=list[ExternalAccountOutput])
def list_ad_accounts(
    connection_id: str,
    user: UserDependency,
    access_tokens: AccessTokensDependency,
    connectors: AdsConnectorsDependency,
) -> list[ExternalAccountOutput]:
    try:
        access = access_tokens.resolve(
            connection_id=connection_id,
            user_id=user.id,
            allowed_providers=frozenset({"GOOGLE_ADS", "META_ADS"}),
        )
        accounts = connectors.create(access.provider).list_accounts(
            access_token=access.access_token
        )
    except PlatformAccessError as error:
        raise platform_access_http_error(error) from error
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
    access_tokens: AccessTokensDependency,
    connectors: AdsConnectorsDependency,
) -> list[ExternalCampaignOutput]:
    try:
        access = access_tokens.resolve(
            connection_id=connection_id,
            user_id=user.id,
            allowed_providers=frozenset({"GOOGLE_ADS", "META_ADS"}),
        )
        campaigns = connectors.create(access.provider).list_campaigns(
            access_token=access.access_token, account_ref=account_ref
        )
    except PlatformAccessError as error:
        raise platform_access_http_error(error) from error
    except (httpx.HTTPError, RuntimeError) as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Advertising campaign discovery failed: {error}",
        ) from error
    return [ExternalCampaignOutput.from_domain(item) for item in campaigns]
