"""API wiring smoke test (REST 202 + snapshot + WS replay) via TestClient."""
from __future__ import annotations

import json

from fastapi.testclient import TestClient

from app.main import app

REQUEST = {
    "agent_run_id": "run_api001",
    "workspace_id": "demo_workspace",
    "campaign_id": "camp_comeback_teaser",
    "question": "What should we test next week?",
    "date_range": {"start": "2026-05-25", "end": "2026-05-31"},
    "trace_context": {"request_id": "req_api", "source": "java-backend"},
}


def test_start_then_stream_then_snapshot() -> None:
    client = TestClient(app)

    resp = client.post("/internal/agent/runs", json=REQUEST)
    assert resp.status_code == 202
    body = resp.json()
    assert body["ok"] is True
    assert body["status"] == "PENDING"
    assert body["stream_url"] == "/internal/agent/runs/run_api001/stream"

    # WS replays the full run; read until the final draft event.
    types = []
    with client.websocket_connect("/internal/agent/runs/run_api001/stream") as ws:
        while True:
            event = json.loads(ws.receive_text())
            types.append(event["type"])
            if event["type"] == "experiment_plan.drafted":
                assert event["status"] == "WAITING_FOR_APPROVAL"
                assert event["payload"]["experiment_plan"]["items"]
                break

    assert "run.started" in types

    snap = client.get("/internal/agent/runs/run_api001").json()
    assert snap["status"] == "WAITING_FOR_APPROVAL"
    assert snap["payload"]["experiment_plan"]["items"]


def test_unknown_run_404_contract_error() -> None:
    client = TestClient(app)
    resp = client.get("/internal/agent/runs/run_missing")
    assert resp.status_code == 404
    body = resp.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "RUN_NOT_FOUND"


def test_run_id_conflict_409() -> None:
    client = TestClient(app)
    client.post("/internal/agent/runs", json={**REQUEST, "agent_run_id": "run_conf01"})
    different = {**REQUEST, "agent_run_id": "run_conf01", "question": "different body"}
    resp = client.post("/internal/agent/runs", json=different)
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "RUN_ID_CONFLICT"
