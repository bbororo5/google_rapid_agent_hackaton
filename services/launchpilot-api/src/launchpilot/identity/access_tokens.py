from __future__ import annotations

import httpx

from launchpilot.performance.contracts.access import (
    PlatformAccess,
    PlatformAccessUnavailable,
    PlatformAuthorizationExpired,
    PlatformConnectionNotFound,
    PlatformProviderMismatch,
    PlatformTokenRefreshFailed,
    PlatformTokenUnavailable,
)

from .contracts.tokens import GoogleTokenLifecycle
from .models import PlatformConnection
from .ports import PlatformConnectionStore


class PlatformAccessTokenProvider:
    """Owns connection lookup, provider validation, token refresh, and extraction."""

    _refreshable_providers = frozenset({"GOOGLE_ADS", "YOUTUBE"})

    def __init__(
        self, store: PlatformConnectionStore, google_oauth: GoogleTokenLifecycle
    ) -> None:
        self._store = store
        self._google_oauth = google_oauth

    def resolve(
        self,
        *,
        connection_id: str,
        user_id: str,
        allowed_providers: frozenset[str],
    ) -> PlatformAccess:
        try:
            stored = self._store.get_connection_token(
                connection_id=connection_id, user_id=user_id
            )
        except RuntimeError as error:
            raise PlatformAccessUnavailable(
                "platform connection storage is unavailable"
            ) from error
        if stored is None:
            raise PlatformConnectionNotFound("platform connection not found")
        connection, token = stored
        if connection.provider not in allowed_providers:
            raise PlatformProviderMismatch("connection does not support this operation")
        if self._google_oauth.access_token_expired(token):
            token = self._refresh(connection=connection, token=token, user_id=user_id)
        access_token = token.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise PlatformTokenUnavailable("connection does not provide read access")
        return PlatformAccess(
            provider=connection.provider,
            access_token=access_token,
        )

    def _refresh(
        self,
        *,
        connection: PlatformConnection,
        token: dict[str, object],
        user_id: str,
    ) -> dict[str, object]:
        refresh_token = token.get("refresh_token")
        if connection.provider not in self._refreshable_providers or not isinstance(
            refresh_token, str
        ):
            raise PlatformAuthorizationExpired(
                "authorization expired; reconnect the account"
            )
        try:
            refreshed = self._google_oauth.refresh_access_token(refresh_token)
        except httpx.HTTPError as error:
            raise PlatformTokenRefreshFailed("authorization refresh failed") from error
        self._store.upsert_connection(
            user_id=user_id,
            provider=connection.provider,
            token=refreshed,
            granted_scopes=connection.granted_scopes,
            account_ref=connection.account_ref,
        )
        return {**token, **refreshed}
