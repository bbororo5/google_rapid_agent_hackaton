from dataclasses import dataclass

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from launchpilot.api.auth import SESSION_COOKIE
from launchpilot.api.dependencies import control_plane, repository_store, settings
from launchpilot.infrastructure.control_plane import ConnectedUser, SqliteControlPlane
from launchpilot.infrastructure.security import SessionManager, SignedTokenCodec
from launchpilot.main import app


@dataclass(frozen=True)
class AuthenticatedClient:
    client: TestClient
    store: SqliteControlPlane
    user: ConnectedUser
    workspace_id: str
    session_manager: SessionManager


@pytest.fixture
def authenticated_client(tmp_path, monkeypatch) -> AuthenticatedClient:
    secret = "test-session-secret-with-at-least-32-characters"
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "control-plane.db"))
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("APP_SESSION_SECRET", secret)
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "test-client")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRET", "test-secret")
    settings.cache_clear()
    control_plane.cache_clear()
    repository_store.cache_clear()

    store = control_plane()
    user = store.upsert_user(
        google_subject="user-a", email="a@example.com", display_name="User A"
    )
    workspace_id = store.list_workspaces(user.id)[0].id
    sessions = SessionManager(SignedTokenCodec(secret))
    client = TestClient(app)
    client.cookies.set(SESSION_COOKIE, sessions.issue(user.id))
    return AuthenticatedClient(client, store, user, workspace_id, sessions)


def campaign_payload(workspace_id: str) -> dict[str, object]:
    return {
        "workspace_id": workspace_id,
        "name": "A 캠페인",
        "goal": "신규 영상의 조회와 구독 전환을 분석한다.",
        "period": {"start": "2026-07-01", "end": "2026-07-31"},
        "target_metrics": ["views", "subscribersGained"],
    }


def test_health() -> None:
    response = TestClient(app).get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_campaign_and_campaign_scoped_conversation(
    authenticated_client: AuthenticatedClient,
) -> None:
    context = authenticated_client
    campaign_response = context.client.post(
        "/campaigns",
        json=campaign_payload(context.workspace_id),
    )

    assert campaign_response.status_code == 201
    campaign = campaign_response.json()
    assert campaign["workspace_id"] == context.workspace_id

    conversation_response = context.client.post(
        f"/campaigns/{campaign['id']}/conversations",
        json={"title": "7월 성과 분석"},
    )
    assert conversation_response.status_code == 201
    assert conversation_response.json()["campaign_id"] == campaign["id"]

    conversations_response = context.client.get(
        f"/campaigns/{campaign['id']}/conversations"
    )
    assert conversations_response.status_code == 200
    assert [item["title"] for item in conversations_response.json()] == [
        "7월 성과 분석"
    ]


def test_campaign_routes_require_authentication(
    authenticated_client: AuthenticatedClient,
) -> None:
    anonymous = TestClient(app)

    assert anonymous.get("/campaigns").status_code == 401
    assert (
        anonymous.post(
            "/campaigns", json=campaign_payload(authenticated_client.workspace_id)
        ).status_code
        == 401
    )


def test_cross_workspace_campaign_is_hidden(
    authenticated_client: AuthenticatedClient,
) -> None:
    context = authenticated_client
    campaign = context.client.post(
        "/campaigns", json=campaign_payload(context.workspace_id)
    ).json()
    other_user = context.store.upsert_user(
        google_subject="user-b",
        email="b@example.com",
        display_name="User B",
    )
    context.client.cookies.set(
        SESSION_COOKIE, context.session_manager.issue(other_user.id)
    )

    assert context.client.get(f"/campaigns/{campaign['id']}").status_code == 404
    assert context.client.get("/campaigns").json() == []
    assert (
        context.client.post(
            f"/campaigns/{campaign['id']}/conversations",
            json={"title": "접근하면 안 됨"},
        ).status_code
        == 404
    )


def test_invalid_campaign_period_is_rejected_at_http_boundary(
    authenticated_client: AuthenticatedClient,
) -> None:
    payload = campaign_payload(authenticated_client.workspace_id)
    payload["period"] = {"start": "2026-08-01", "end": "2026-07-01"}

    response = authenticated_client.client.post("/campaigns", json=payload)

    assert response.status_code == 422


def test_conversation_requires_an_existing_campaign(
    authenticated_client: AuthenticatedClient,
) -> None:
    response = authenticated_client.client.post(
        "/campaigns/00000000-0000-0000-0000-000000000001/conversations",
        json={"title": "없는 캠페인"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "campaign not found"


def test_campaign_can_bind_an_owned_platform_campaign(
    authenticated_client: AuthenticatedClient,
) -> None:
    context = authenticated_client
    campaign = context.client.post(
        "/campaigns", json=campaign_payload(context.workspace_id)
    ).json()
    connection = context.store.upsert_connection(
        user_id=context.user.id,
        provider="GOOGLE_ADS",
        token={"access_token": "encrypted-at-rest"},
        granted_scopes=("https://www.googleapis.com/auth/adwords",),
    )

    response = context.client.post(
        f"/campaigns/{campaign['id']}/bindings",
        json={
            "connection_id": connection.id,
            "external_account_ref": "customers/123",
            "external_campaign_ref": "456",
            "display_name": "Launch Search",
            "currency_code": "KRW",
            "timezone": "Asia/Seoul",
            "attribution_setting": "last-click",
        },
    )

    assert response.status_code == 201
    assert response.json()["provider"] == "GOOGLE_ADS"
    listed = context.client.get(f"/campaigns/{campaign['id']}/bindings")
    assert [item["external_campaign_ref"] for item in listed.json()] == ["456"]


def test_campaign_binding_rejects_blank_external_identity(
    authenticated_client: AuthenticatedClient,
) -> None:
    context = authenticated_client
    campaign = context.client.post(
        "/campaigns", json=campaign_payload(context.workspace_id)
    ).json()

    response = context.client.post(
        f"/campaigns/{campaign['id']}/bindings",
        json={
            "connection_id": " ",
            "external_account_ref": "act_123",
            "external_campaign_ref": "456",
            "display_name": "Launch",
        },
    )

    assert response.status_code == 422
