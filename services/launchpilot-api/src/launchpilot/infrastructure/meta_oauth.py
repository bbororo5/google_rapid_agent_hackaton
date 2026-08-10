from __future__ import annotations

from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import httpx


class MetaOAuthClient:
    def __init__(
        self,
        *,
        app_id: str,
        app_secret: str,
        public_base_url: str,
        api_version: str = "v24.0",
        authorize_base_url: str = "https://www.facebook.com",
        graph_base_url: str = "https://graph.facebook.com",
    ) -> None:
        self._app_id = app_id
        self._app_secret = app_secret
        self._public_base_url = public_base_url.rstrip("/")
        self._api_version = api_version
        self._authorize_base_url = authorize_base_url.rstrip("/")
        self._graph_base_url = graph_base_url.rstrip("/")

    def authorization_url(
        self, *, state: str, scopes: tuple[str, ...], callback_path: str
    ) -> str:
        return (
            f"{self._authorize_base_url}/{self._api_version}/dialog/oauth?"
            + urlencode(
                {
                    "client_id": self._app_id,
                    "redirect_uri": f"{self._public_base_url}{callback_path}",
                    "state": state,
                    "scope": ",".join(scopes),
                    "response_type": "code",
                }
            )
        )

    def exchange_code(self, *, code: str, callback_path: str) -> dict[str, object]:
        response = httpx.get(
            f"{self._graph_base_url}/{self._api_version}/oauth/access_token",
            params={
                "client_id": self._app_id,
                "client_secret": self._app_secret,
                "redirect_uri": f"{self._public_base_url}{callback_path}",
                "code": code,
            },
            timeout=20,
        )
        response.raise_for_status()
        short_lived = response.json()
        extended_response = httpx.get(
            f"{self._graph_base_url}/{self._api_version}/oauth/access_token",
            params={
                "grant_type": "fb_exchange_token",
                "client_id": self._app_id,
                "client_secret": self._app_secret,
                "fb_exchange_token": short_lived["access_token"],
            },
            timeout=20,
        )
        extended_response.raise_for_status()
        token = extended_response.json()
        expires_in = int(token.get("expires_in", 0))
        if expires_in:
            token["expires_at"] = (
                datetime.now(UTC) + timedelta(seconds=expires_in)
            ).isoformat()
        return token
