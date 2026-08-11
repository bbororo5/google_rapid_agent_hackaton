import httpx
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from launchpilot.bootstrap.wiring import settings
from launchpilot.identity.oauth.google import GoogleOAuthClient
from launchpilot.identity.postgres import PostgresIdentityStore
from launchpilot.identity.security import (
    BrowserStateManager,
    InvalidSignedToken,
    SignedTokenCodec,
)
from launchpilot.main import app
from launchpilot.persistence.postgres import PostgresDatabase


def test_google_authorization_url_uses_state_pkce_callback_and_scopes() -> None:
    client = GoogleOAuthClient(
        client_id="client-id",
        client_secret="client-secret",
        public_base_url="http://127.0.0.1:8000",
    )

    url = client.authorization_url(
        state="csrf-state",
        scopes=("https://www.googleapis.com/auth/youtube.readonly",),
        callback_path="/connections/youtube/callback",
        code_challenge="pkce-challenge",
    )

    assert "state=csrf-state" in url
    assert (
        "redirect_uri=http%3A%2F%2F127.0.0.1%3A8000%2Fconnections%2Fyoutube%2Fcallback"
        in url
    )
    assert "code_challenge=pkce-challenge" in url
    assert "code_challenge_method=S256" in url


def test_oauth_state_is_bound_to_signed_browser_cookie() -> None:
    manager = BrowserStateManager(
        SignedTokenCodec("test-session-secret-with-at-least-32-characters")
    )
    transaction = manager.issue("LOGIN")

    assert (
        manager.consume(
            cookie_value=transaction.cookie_value,
            state=transaction.state,
            purpose="LOGIN",
        )
        == transaction.code_verifier
    )

    try:
        manager.consume(
            cookie_value=transaction.cookie_value,
            state="attacker-state",
            purpose="LOGIN",
        )
        raise AssertionError("mismatched state must be rejected")
    except InvalidSignedToken:
        pass


def test_control_plane_creates_workspace_and_keeps_refresh_token(
    postgres_database: PostgresDatabase,
) -> None:
    store = PostgresIdentityStore(postgres_database, Fernet.generate_key().decode())
    user = store.upsert_user(
        google_subject="google-sub", email="user@example.com", display_name="User"
    )

    workspaces = store.list_workspaces(user.id)
    assert len(workspaces) == 1
    assert workspaces[0].role == "OWNER"

    first = store.upsert_connection(
        user_id=user.id,
        provider="YOUTUBE",
        token={"access_token": "first", "refresh_token": "durable"},
        granted_scopes=("scope-a",),
    )
    store.upsert_connection(
        user_id=user.id,
        provider="YOUTUBE",
        token={"access_token": "second"},
        granted_scopes=("scope-a",),
    )

    connection, token = store.get_connection_token(
        connection_id=first.id, user_id=user.id
    ) or (None, None)
    assert connection is not None
    assert token == {"access_token": "second", "refresh_token": "durable"}


def test_refresh_token_grant_records_new_expiry(monkeypatch) -> None:
    def fake_post(*args, **kwargs):
        return httpx.Response(
            200,
            json={"access_token": "new-access", "expires_in": 3600},
            request=httpx.Request("POST", "https://oauth2.googleapis.com/token"),
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    client = GoogleOAuthClient(
        client_id="client-id",
        client_secret="client-secret",
        public_base_url="http://127.0.0.1:8000",
    )

    token = client.refresh_access_token("refresh-token")

    assert token["access_token"] == "new-access"
    assert isinstance(token["expires_at"], str)
    assert not client.access_token_expired(token)


def test_oauth_browser_cookie_is_secure_for_https_environment(monkeypatch) -> None:
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://api.example.com")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "client-id")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRET", "client-secret")
    monkeypatch.setenv(
        "APP_SESSION_SECRET", "test-session-secret-with-at-least-32-characters"
    )
    settings.cache_clear()

    response = TestClient(app).get("/auth/google/login", follow_redirects=False)

    assert response.status_code == 307
    assert "Secure" in response.headers["set-cookie"]
    settings.cache_clear()
