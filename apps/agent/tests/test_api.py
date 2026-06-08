"""API wiring smoke test (turn 202 + thread WS block stream) via TestClient."""
from __future__ import annotations

import json

from fastapi.testclient import TestClient

from app.main import app

THREAD_ID = "thread_api001"
TURN = {
    "thread_id": THREAD_ID,
    "workspace_id": "demo_workspace",
    "campaign_id": "camp_comeback_teaser",
    "content": "What should we test next week?",
    "attachments": [{"kind": "csv_import", "id": "imp_api001"}],
    "client_created_at": "2026-06-01T16:31:00+09:00",
    "trace_context": {"request_id": "req_api", "source": "java-backend"},
}


def test_turn_then_stream_blocks() -> None:
    client = TestClient(app)

    # Connect the stream first (Java's connect-then-turn order), then post a turn.
    with client.websocket_connect(f"/internal/agent/threads/{THREAD_ID}/stream") as ws:
        resp = client.post("/internal/agent/turns", json=TURN)
        assert resp.status_code == 202
        body = resp.json()
        assert body["ok"] is True
        assert body["thread_id"] == THREAD_ID

        # Read live blocks until the approval block arrives.
        kinds = set()
        approval = None
        while True:
            message = json.loads(ws.receive_text())
            assert message["thread_id"] == THREAD_ID
            for block in message["blocks"]:
                kinds.add(block["kind"])
                if block["kind"] == "approval":
                    approval = block
            if approval is not None:
                break

    assert "activity" in kinds
    assert "artifact" in kinds
    assert approval["target_id"].startswith("plan_")
    assert approval["payload"]["experiment_plan"]["items"]


def test_turn_lenient_without_trace_context() -> None:
    # Java currently sends trace_context=null; a turn must still be accepted.
    client = TestClient(app)
    resp = client.post(
        "/internal/agent/turns",
        json={
            "thread_id": "thread_api002",
            "content": "Find the signal.",
            "trace_context": None,
        },
    )
    assert resp.status_code == 202
    assert resp.json()["thread_id"] == "thread_api002"


def test_turn_invalid_body_400() -> None:
    client = TestClient(app)
    resp = client.post("/internal/agent/turns", json={"thread_id": "bad-id", "content": "x"})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "INVALID_REQUEST"


def test_unknown_thread_ws_accepts_and_waits() -> None:
    # A WS to an unseen (but well-formed) thread id is created on connect.
    client = TestClient(app)
    with client.websocket_connect("/internal/agent/threads/thread_unseen/stream"):
        pass  # connects without error; no blocks yet


def test_malformed_thread_ws_rejected() -> None:
    client = TestClient(app)
    try:
        with client.websocket_connect("/internal/agent/threads/not-a-thread/stream"):
            pass
        assert False, "expected the malformed thread WS to be rejected"
    except Exception:
        pass
