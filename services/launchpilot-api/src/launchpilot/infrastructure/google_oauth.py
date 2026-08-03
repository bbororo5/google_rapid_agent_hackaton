from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

import httpx

GOOGLE_AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"


class GoogleOAuthClient:
    def __init__(self, *, client_id: str, client_secret: str, public_base_url: str) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._public_base_url = public_base_url

    def authorization_url(self, *, state: str, scopes: tuple[str, ...], callback_path: str) -> str:
        params = {
            "client_id": self._client_id,
            "redirect_uri": f"{self._public_base_url}{callback_path}",
            "response_type": "code",
            "scope": " ".join(scopes),
            "state": state,
            "access_type": "offline",
            "include_granted_scopes": "true",
            "prompt": "consent",
        }
        return f"{GOOGLE_AUTHORIZE_URL}?{urlencode(params)}"

    def exchange_code(self, *, code: str, callback_path: str) -> dict[str, Any]:
        response = httpx.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "redirect_uri": f"{self._public_base_url}{callback_path}",
                "grant_type": "authorization_code",
            },
            timeout=15,
        )
        response.raise_for_status()
        return response.json()

    def user_info(self, access_token: str) -> dict[str, Any]:
        response = httpx.get(GOOGLE_USERINFO_URL, headers={"Authorization": f"Bearer {access_token}"}, timeout=15)
        response.raise_for_status()
        return response.json()

