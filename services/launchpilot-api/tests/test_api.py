from fastapi.testclient import TestClient

from launchpilot.api.dependencies import repository_store
from launchpilot.main import app


def setup_function() -> None:
    repository_store.cache_clear()


def test_health() -> None:
    response = TestClient(app).get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_campaign_and_campaign_scoped_conversation() -> None:
    client = TestClient(app)
    campaign_response = client.post(
        "/campaigns",
        json={
            "name": "A 캠페인",
            "goal": "신규 영상의 조회와 구독 전환을 분석한다.",
            "period": {"start": "2026-07-01", "end": "2026-07-31"},
            "target_metrics": ["views", "subscribersGained"],
        },
    )

    assert campaign_response.status_code == 201
    campaign = campaign_response.json()
    assert campaign["name"] == "A 캠페인"

    conversation_response = client.post(
        f"/campaigns/{campaign['id']}/conversations",
        json={"title": "7월 성과 분석"},
    )
    assert conversation_response.status_code == 201
    assert conversation_response.json()["campaign_id"] == campaign["id"]

    conversations_response = client.get(f"/campaigns/{campaign['id']}/conversations")
    assert conversations_response.status_code == 200
    assert [item["title"] for item in conversations_response.json()] == ["7월 성과 분석"]


def test_invalid_campaign_period_is_rejected_at_http_boundary() -> None:
    response = TestClient(app).post(
        "/campaigns",
        json={
            "name": "A 캠페인",
            "goal": "분석",
            "period": {"start": "2026-08-01", "end": "2026-07-01"},
        },
    )

    assert response.status_code == 422


def test_conversation_requires_an_existing_campaign() -> None:
    response = TestClient(app).post(
        "/campaigns/00000000-0000-0000-0000-000000000001/conversations",
        json={"title": "없는 캠페인"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "campaign not found"

