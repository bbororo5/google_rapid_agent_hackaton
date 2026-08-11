from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode

import httpx

GOOGLE_AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"


class GoogleOAuthClient:
    def __init__(
        self,
        *,
        client_id: str,
        client_secret: str,
        public_base_url: str,
        authorize_url: str = GOOGLE_AUTHORIZE_URL,
        token_url: str = GOOGLE_TOKEN_URL,
        userinfo_url: str = GOOGLE_USERINFO_URL,
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._public_base_url = public_base_url
        self._authorize_url = authorize_url
        self._token_url = token_url
        self._userinfo_url = userinfo_url

    def authorization_url(
        self,
        *,
        state: str,
        scopes: tuple[str, ...],
        callback_path: str,
        code_challenge: str,
    ) -> str:
        params = {
            "client_id": self._client_id,
            "redirect_uri": f"{self._public_base_url}{callback_path}",
            "response_type": "code",
            "scope": " ".join(scopes),
            "state": state,
            "access_type": "offline",
            "include_granted_scopes": "true",
            "prompt": "consent",
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
        return f"{self._authorize_url}?{urlencode(params)}"

    def exchange_code(
        self, *, code: str, callback_path: str, code_verifier: str
    ) -> dict[str, Any]:
        response = httpx.post(
            self._token_url,
            data={
                "code": code,
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "redirect_uri": f"{self._public_base_url}{callback_path}",
                "grant_type": "authorization_code",
                "code_verifier": code_verifier,
            },
            timeout=15,
        )
        response.raise_for_status()
        return self._with_expiry(response.json())

    def refresh_access_token(self, refresh_token: str) -> dict[str, Any]:
        response = httpx.post(
            self._token_url,
            data={
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
            timeout=15,
        )
        response.raise_for_status()
        return self._with_expiry(response.json())

    @staticmethod
    def access_token_expired(token: dict[str, object]) -> bool:
        expires_at = token.get("expires_at")
        if not isinstance(expires_at, str):
            return True
        try:
            return datetime.fromisoformat(expires_at) <= datetime.now(UTC) + timedelta(
                minutes=1
            )
        except ValueError:
            return True

    @staticmethod
    def _with_expiry(token: dict[str, Any]) -> dict[str, Any]:
        expires_in = token.get("expires_in")
        if isinstance(expires_in, (int, float)):
            token["expires_at"] = (
                datetime.now(UTC) + timedelta(seconds=float(expires_in))
            ).isoformat()
        return token

    def user_info(self, access_token: str) -> dict[str, Any]:
        response = httpx.get(
            self._userinfo_url,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=15,
        )
        response.raise_for_status()
        return response.json()
