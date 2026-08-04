from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Settings:
    database_path: str
    public_base_url: str
    google_client_id: str | None
    google_client_secret: str | None
    token_encryption_key: str | None
    app_session_secret: str | None
    cookie_secure: bool
    google_ads_developer_token: str | None
    google_ads_api_version: str
    meta_graph_api_version: str
    meta_app_id: str | None
    meta_app_secret: str | None

    @classmethod
    def from_environment(cls) -> Settings:
        public_base_url = os.getenv("PUBLIC_BASE_URL", "http://127.0.0.1:8000").rstrip(
            "/"
        )
        cookie_secure_value = os.getenv("COOKIE_SECURE")
        cookie_secure = (
            cookie_secure_value.lower() in {"1", "true", "yes"}
            if cookie_secure_value is not None
            else public_base_url.startswith("https://")
        )
        return cls(
            database_path=os.getenv("DATABASE_PATH", "./data/launchpilot.db"),
            public_base_url=public_base_url,
            google_client_id=os.getenv("GOOGLE_OAUTH_CLIENT_ID"),
            google_client_secret=os.getenv("GOOGLE_OAUTH_CLIENT_SECRET"),
            token_encryption_key=os.getenv("TOKEN_ENCRYPTION_KEY"),
            app_session_secret=os.getenv("APP_SESSION_SECRET"),
            cookie_secure=cookie_secure,
            google_ads_developer_token=os.getenv("GOOGLE_ADS_DEVELOPER_TOKEN"),
            google_ads_api_version=os.getenv("GOOGLE_ADS_API_VERSION", "v25"),
            meta_graph_api_version=os.getenv("META_GRAPH_API_VERSION", "v24.0"),
            meta_app_id=os.getenv("META_APP_ID"),
            meta_app_secret=os.getenv("META_APP_SECRET"),
        )

    def require_google_oauth(self) -> None:
        if not self.google_client_id or not self.google_client_secret:
            raise RuntimeError(
                "Google OAuth is not configured. Set GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET."
            )

    def require_token_key(self) -> str:
        if not self.token_encryption_key:
            raise RuntimeError(
                "Token encryption is not configured. Set TOKEN_ENCRYPTION_KEY."
            )
        return self.token_encryption_key

    def require_session_secret(self) -> str:
        if not self.app_session_secret or len(self.app_session_secret) < 32:
            raise RuntimeError(
                "Session signing is not configured. Set APP_SESSION_SECRET to at least 32 characters."
            )
        return self.app_session_secret

    def require_google_ads(self) -> str:
        if not self.google_ads_developer_token:
            raise RuntimeError(
                "Google Ads is not configured. Set GOOGLE_ADS_DEVELOPER_TOKEN."
            )
        return self.google_ads_developer_token

    def require_meta_oauth(self) -> tuple[str, str]:
        if not self.meta_app_id or not self.meta_app_secret:
            raise RuntimeError(
                "Meta OAuth is not configured. Set META_APP_ID and META_APP_SECRET."
            )
        return self.meta_app_id, self.meta_app_secret
