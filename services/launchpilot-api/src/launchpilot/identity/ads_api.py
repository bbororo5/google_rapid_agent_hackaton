from __future__ import annotations

from typing import Annotated

import httpx
from fastapi import APIRouter, Cookie, Depends, HTTPException, Query, Response, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from launchpilot.bootstrap.config import Settings
from launchpilot.bootstrap.platform_http_errors import platform_access_http_error
from launchpilot.bootstrap.wiring import (
    advertising_catalog_service,
    browser_state_manager,
    google_oauth_client,
    identity_store,
    meta_oauth_client,
    settings,
)
from launchpilot.identity.models import ConnectedUser
from launchpilot.identity.oauth.google import GoogleOAuthClient
from launchpilot.identity.oauth.meta import MetaOAuthClient
from launchpilot.identity.ports import PlatformConnectionStore
from launchpilot.identity.security import BrowserStateManager, InvalidSignedToken
from launchpilot.performance.contracts.access import PlatformAccessError
from launchpilot.performance.contracts.catalog import (
    AdvertisingCatalog,
    ListAdvertisingAccounts,
    ListAdvertisingCampaigns,
)
from launchpilot.performance.contracts.platform import (
    ExternalAccount,
    ExternalCampaign,
)

from .auth_api import current_user
from .connections_api import ConnectionOutput

router = APIRouter(prefix="/connections", tags=["ad connections"])
PlatformConnectionStoreDependency = Annotated[
    PlatformConnectionStore, Depends(identity_store)
]
GoogleOAuthDependency = Annotated[GoogleOAuthClient, Depends(google_oauth_client)]
MetaOAuthDependency = Annotated[MetaOAuthClient, Depends(meta_oauth_client)]
UserDependency = Annotated[ConnectedUser, Depends(current_user)]
BrowserStateDependency = Annotated[BrowserStateManager, Depends(browser_state_manager)]
SettingsDependency = Annotated[Settings, Depends(settings)]
AdvertisingCatalogDependency = Annotated[
    AdvertisingCatalog, Depends(advertising_catalog_service)
]

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
    store: PlatformConnectionStoreDependency,
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
    store: PlatformConnectionStoreDependency,
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
    catalog: AdvertisingCatalogDependency,
) -> list[ExternalAccountOutput]:
    try:
        accounts = catalog.list_accounts(
            ListAdvertisingAccounts(
                connection_id=connection_id,
                user_id=user.id,
            )
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
    catalog: AdvertisingCatalogDependency,
) -> list[ExternalCampaignOutput]:
    try:
        campaigns = catalog.list_campaigns(
            ListAdvertisingCampaigns(
                connection_id=connection_id,
                user_id=user.id,
                account_ref=account_ref,
            )
        )
    except PlatformAccessError as error:
        raise platform_access_http_error(error) from error
    except (httpx.HTTPError, RuntimeError) as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Advertising campaign discovery failed: {error}",
        ) from error
    return [ExternalCampaignOutput.from_domain(item) for item in campaigns]
