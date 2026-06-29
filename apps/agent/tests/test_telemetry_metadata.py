from app.telemetry import (
    TelemetryKey,
    decision_metadata,
    goal_metadata,
    guardrail_metadata,
    repository_metadata,
    trace_metadata,
    turn_metadata,
)


def test_public_keys_preserve_standard_names():
    assert TelemetryKey.THREAD_ID.value == "thread_id"
    assert TelemetryKey.WORKSPACE_ID.value == "workspace_id"
    assert TelemetryKey.CAMPAIGN_ID.value == "campaign_id"
    assert TelemetryKey.PHASE.value == "phase"
    assert TelemetryKey.VALIDATOR_PASSED.value == "validator_passed"
    assert TelemetryKey.AGENT_REDUCER_DECISION.value == "agent.reducer.decision"


def test_turn_metadata_builds_base_shape():
    assert turn_metadata(
        thread_id="thread_1",
        workspace_id="workspace_1",
        campaign_id="campaign_1",
    ) == {
        "thread_id": "thread_1",
        "workspace_id": "workspace_1",
        "campaign_id": "campaign_1",
        "stage": "TURN",
    }


def test_trace_metadata_adds_optional_otel_trace_id():
    assert trace_metadata(
        request_id="req_1",
        trace_id="trace_1",
        trace_source="java-backend",
        thread_id="thread_1",
        workspace_id="workspace_1",
        campaign_id="campaign_1",
        otel_trace_id="otel_1",
    ) == {
        "request_id": "req_1",
        "trace_id": "trace_1",
        "trace_source": "java-backend",
        "thread_id": "thread_1",
        "workspace_id": "workspace_1",
        "campaign_id": "campaign_1",
        "otel_trace_id": "otel_1",
    }


def test_decision_metadata_builds_orchestrator_shape():
    assert decision_metadata(
        revision_before=2,
        revision_after=3,
        intent="analyze",
        response_mode="assistant",
        reducer_decision="accepted",
        delegation_mode="specialist",
        phase="ANALYSIS",
    ) == {
        "agent.state.revision_before": 2,
        "agent.state.revision_after": 3,
        "agent.delta.intent": "analyze",
        "agent.delta.response_mode": "assistant",
        "agent.reducer.decision": "accepted",
        "agent.delegation.mode": "specialist",
        "phase": "ANALYSIS",
    }


def test_infrastructure_metadata_builders_omit_unknown_repository_fields():
    assert guardrail_metadata(
        thread_id="thread_1",
        workspace_id="workspace_1",
        campaign_id="campaign_1",
    )["validator_passed"] is None
    assert repository_metadata(backend="hot-store") == {
        "agent.repository.backend": "hot-store",
    }
    assert goal_metadata(
        kind="turn",
        budget_profile="default",
        max_steps=4,
        max_llm_calls=8,
    ) == {
        "agent.goal.kind": "turn",
        "agent.goal.budget_profile": "default",
        "agent.goal.max_steps": 4,
        "agent.goal.max_llm_calls": 8,
    }
