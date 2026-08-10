from dataclasses import dataclass
from datetime import date

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.runnables import RunnableLambda

from launchpilot.api.auth import SESSION_COOKIE
from launchpilot.api.dependencies import (
    agent_model,
    control_plane,
    repository_store,
    settings,
)
from launchpilot.domain.integrations import (
    CampaignMetricRequest,
    ConnectorFetchResult,
    PlatformProvider,
)
from launchpilot.domain.models import MetricObservation, PlatformSlice
from launchpilot.infrastructure.control_plane import ConnectedUser, PostgresControlPlane
from launchpilot.infrastructure.postgres_database import PostgresDatabase
from launchpilot.infrastructure.security import SessionManager, SignedTokenCodec
from launchpilot.main import app


@dataclass(frozen=True)
class AuthenticatedClient:
    client: TestClient
    store: PostgresControlPlane
    user: ConnectedUser
    workspace_id: str
    session_manager: SessionManager


@pytest.fixture
def authenticated_client(
    postgres_database: PostgresDatabase, monkeypatch
) -> AuthenticatedClient:
    secret = "test-session-secret-with-at-least-32-characters"
    monkeypatch.setenv("DATABASE_URL", postgres_database.database_url)
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


def test_campaign_survives_repository_dependency_recreation(
    authenticated_client: AuthenticatedClient,
) -> None:
    context = authenticated_client
    campaign = context.client.post(
        "/campaigns", json=campaign_payload(context.workspace_id)
    ).json()

    repository_store.cache_clear()

    response = context.client.get(f"/campaigns/{campaign['id']}")
    assert response.status_code == 200
    assert response.json()["name"] == "A 캠페인"


def test_campaign_analysis_runs_through_agent_tool_loop(
    authenticated_client: AuthenticatedClient,
) -> None:
    context = authenticated_client
    campaign = context.client.post(
        "/campaigns", json=campaign_payload(context.workspace_id)
    ).json()

    class ScriptedAgentModel:
        def bind_tools(self, tools):
            def respond(messages):
                if any(isinstance(message, ToolMessage) for message in messages):
                    return AIMessage(content="저장된 성과 데이터가 아직 없습니다.")
                return AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "get_campaign_performance",
                            "args": {},
                            "id": "api-call-1",
                            "type": "tool_call",
                        }
                    ],
                )

            return RunnableLambda(respond)

    app.dependency_overrides[agent_model] = ScriptedAgentModel
    try:
        response = context.client.post(
            f"/campaigns/{campaign['id']}/analysis",
            json={"question": "현재 캠페인 성과를 분석해줘"},
        )
    finally:
        app.dependency_overrides.pop(agent_model, None)

    assert response.status_code == 200
    assert response.json() == {
        "answer": "저장된 성과 데이터가 아직 없습니다.",
        "evidence": [],
    }


class ApiFixtureAdsConnector:
    def __init__(self, provider: PlatformProvider) -> None:
        self._provider = provider

    @property
    def provider(self) -> PlatformProvider:
        return self._provider

    def list_accounts(self, *, access_token: str):
        return ()

    def list_campaigns(self, *, access_token: str, account_ref: str):
        return ()

    def fetch_campaign_metrics(
        self, *, access_token: str, request: CampaignMetricRequest
    ) -> ConnectorFetchResult:
        metric = MetricObservation(
            subject_ref=f"{self.provider.value}:{request.campaign_ref}",
            subject_level="CAMPAIGN",
            metric_key="spend",
            value=100,
            unit="currency:KRW",
            period=request.period,
            provenance_ref=request.fetch_run_ref,
        )
        return ConnectorFetchResult(
            platform_slice=PlatformSlice(
                surface=self.provider,
                connector=f"{self.provider.value.lower()}-fixture",
                account_ref=request.account_ref,
                external_campaign_ref=request.campaign_ref,
                fetch_run_ref=request.fetch_run_ref,
                currency_code="KRW",
                timezone="Asia/Seoul",
                metrics=(metric,),
            )
        )


def test_multiplatform_api_persists_observation_across_repository_recreation(
    authenticated_client: AuthenticatedClient, monkeypatch
) -> None:
    context = authenticated_client
    campaign = context.client.post(
        "/campaigns", json=campaign_payload(context.workspace_id)
    ).json()
    for provider, account_ref, campaign_ref in (
        ("GOOGLE_ADS", "customers/123", "456"),
        ("META_ADS", "act_789", "101112"),
    ):
        connection = context.store.upsert_connection(
            user_id=context.user.id,
            provider=provider,
            token={
                "access_token": f"{provider.lower()}-token",
                "expires_at": "2099-01-01T00:00:00+00:00",
            },
            granted_scopes=("read",),
        )
        binding_response = context.client.post(
            f"/campaigns/{campaign['id']}/bindings",
            json={
                "connection_id": connection.id,
                "external_account_ref": account_ref,
                "external_campaign_ref": campaign_ref,
                "display_name": f"{provider} Campaign",
                "currency_code": "KRW",
                "timezone": "Asia/Seoul",
            },
        )
        assert binding_response.status_code == 201

    monkeypatch.setattr(
        "launchpilot.infrastructure.ads_factory.AdsConnectorFactory.create",
        lambda self, provider: ApiFixtureAdsConnector(PlatformProvider(provider)),
    )
    response = context.client.post(
        f"/campaigns/{campaign['id']}/observations/ads",
        json={"start": date(2026, 7, 1).isoformat(), "end": "2026-07-31"},
    )

    assert response.status_code == 201
    assert response.json()["completeness"] == "COMPLETE"
    assert response.json()["platform_slice_count"] == 2

    repository_store.cache_clear()
    restored = context.client.get(f"/campaigns/{campaign['id']}/observations")
    assert restored.status_code == 200
    assert restored.json()[0]["platform_slice_count"] == 2
