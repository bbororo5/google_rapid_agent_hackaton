from cryptography.fernet import Fernet

from launchpilot.infrastructure.control_plane import SqliteControlPlane
from launchpilot.infrastructure.google_oauth import GoogleOAuthClient


def test_google_authorization_url_is_bound_to_callback_scopes_and_state() -> None:
    client = GoogleOAuthClient(
        client_id="client-id",
        client_secret="client-secret",
        public_base_url="http://127.0.0.1:8000",
    )

    url = client.authorization_url(
        state="csrf-state",
        scopes=("https://www.googleapis.com/auth/youtube.readonly",),
        callback_path="/connections/youtube/callback",
    )

    assert "state=csrf-state" in url
    assert "redirect_uri=http%3A%2F%2F127.0.0.1%3A8000%2Fconnections%2Fyoutube%2Fcallback" in url
    assert "access_type=offline" in url


def test_control_plane_consumes_oauth_state_once_and_keeps_refresh_token(tmp_path) -> None:
    store = SqliteControlPlane(str(tmp_path / "control-plane.db"), Fernet.generate_key().decode())
    transaction = store.create_transaction(purpose="LOGIN", user_id=None)

    assert store.consume_transaction(transaction.state, "LOGIN") is not None
    assert store.consume_transaction(transaction.state, "LOGIN") is None

    user = store.upsert_user(google_subject="google-sub", email="user@example.com", display_name="User")
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

    connection, token = store.get_connection_token(connection_id=first.id, user_id=user.id) or (None, None)
    assert connection is not None
    assert token == {"access_token": "second", "refresh_token": "durable"}
