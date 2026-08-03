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

    @classmethod
    def from_environment(cls) -> "Settings":
        return cls(
            database_path=os.getenv("DATABASE_PATH", "./data/launchpilot.db"),
            public_base_url=os.getenv("PUBLIC_BASE_URL", "http://127.0.0.1:8000").rstrip("/"),
            google_client_id=os.getenv("GOOGLE_OAUTH_CLIENT_ID"),
            google_client_secret=os.getenv("GOOGLE_OAUTH_CLIENT_SECRET"),
            token_encryption_key=os.getenv("TOKEN_ENCRYPTION_KEY"),
        )

    def require_google_oauth(self) -> None:
        if not self.google_client_id or not self.google_client_secret:
            raise RuntimeError("Google OAuth is not configured. Set GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET.")

    def require_token_key(self) -> str:
        if not self.token_encryption_key:
            raise RuntimeError("Token encryption is not configured. Set TOKEN_ENCRYPTION_KEY.")
        return self.token_encryption_key

