from urllib.parse import parse_qs, urlparse

from launchpilot.infrastructure.google_oauth import GoogleOAuthClient
from launchpilot.infrastructure.meta_oauth import MetaOAuthClient


def test_google_ads_authorization_uses_dedicated_scope_and_callback() -> None:
    client = GoogleOAuthClient(
        client_id="client-id",
        client_secret="client-secret",
        public_base_url="http://127.0.0.1:8000",
    )

    url = client.authorization_url(
        state="state",
        scopes=("https://www.googleapis.com/auth/adwords",),
        callback_path="/connections/google-ads/callback",
        code_challenge="challenge",
    )
    query = parse_qs(urlparse(url).query)

    assert query["scope"] == ["https://www.googleapis.com/auth/adwords"]
    assert query["redirect_uri"] == [
        "http://127.0.0.1:8000/connections/google-ads/callback"
    ]
    assert query["code_challenge"] == ["challenge"]


def test_meta_ads_authorization_uses_ads_read_and_state() -> None:
    client = MetaOAuthClient(
        app_id="app-id",
        app_secret="app-secret",
        public_base_url="http://127.0.0.1:8000",
    )

    url = client.authorization_url(
        state="state",
        scopes=("ads_read",),
        callback_path="/connections/meta-ads/callback",
    )
    query = parse_qs(urlparse(url).query)

    assert query["client_id"] == ["app-id"]
    assert query["scope"] == ["ads_read"]
    assert query["state"] == ["state"]
    assert query["redirect_uri"] == [
        "http://127.0.0.1:8000/connections/meta-ads/callback"
    ]
