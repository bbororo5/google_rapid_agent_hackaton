from types import SimpleNamespace

from app.telemetry import service as telemetry_service
from app.telemetry import (
    TelemetryKey,
    decision_metadata,
    goal_metadata,
    guardrail_metadata,
    repository_metadata,
    scope_metadata,
    trace_metadata,
    turn_metadata,
)


class _FakeTracing:
    def __init__(self):
        self.metadata = []
        self.outputs = []
        self.documents = []

    def set_metadata(self, span, metadata):
        self.metadata.append((span, metadata))

    def set_output(self, span, output):
        self.outputs.append((span, output))

    def set_documents(self, span, documents):
        self.documents.append((span, documents))


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
    assert scope_metadata(workspace_id="workspace_1", campaign_id="campaign_1") == {
        "agent.scope.workspace_id": "workspace_1",
        "agent.scope.campaign_id": "campaign_1",
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


def test_telemetry_service_records_standard_turn_decision_metadata():
    fake = _FakeTracing()
    original = telemetry_service.tracing
    telemetry_service.tracing = fake
    try:
        goal = SimpleNamespace(
            kind=SimpleNamespace(value="turn"),
            budget_profile=SimpleNamespace(value="default"),
            budgets=SimpleNamespace(max_steps=4, max_llm_calls=8),
        )

        telemetry_service.record_turn_decision(
            "span",
            turn_metadata=turn_metadata(
                thread_id="thread_1",
                workspace_id="workspace_1",
                campaign_id="campaign_1",
            ),
            decision_metadata=decision_metadata(
                revision_before=2,
                revision_after=3,
                intent="analyze",
                response_mode="assistant",
                reducer_decision="accepted",
                delegation_mode="specialist",
                phase="ANALYSIS",
            ),
            workspace_id="workspace_1",
            campaign_id="campaign_1",
            repository_backend="hot-store",
            goal=goal,
        )
    finally:
        telemetry_service.tracing = original

    assert fake.metadata == [
        (
            "span",
            {
                "thread_id": "thread_1",
                "workspace_id": "workspace_1",
                "campaign_id": "campaign_1",
                "stage": "TURN",
                "agent.scope.workspace_id": "workspace_1",
                "agent.scope.campaign_id": "campaign_1",
                "agent.repository.backend": "hot-store",
                "agent.state.revision_before": 2,
                "agent.state.revision_after": 3,
                "agent.delta.intent": "analyze",
                "agent.delta.response_mode": "assistant",
                "agent.reducer.decision": "accepted",
                "agent.delegation.mode": "specialist",
                "phase": "ANALYSIS",
                "agent.goal.kind": "turn",
                "agent.goal.budget_profile": "default",
                "agent.goal.max_steps": 4,
                "agent.goal.max_llm_calls": 8,
            },
        )
    ]


def test_telemetry_service_records_standard_guardrail_and_evidence_metadata():
    fake = _FakeTracing()
    original = telemetry_service.tracing
    telemetry_service.tracing = fake
    try:
        report = SimpleNamespace(
            passed=True,
            model_dump=lambda mode: {"passed": True, "mode": mode},
        )
        telemetry_service.record_guardrail_result(
            "guardrail-span",
            report,
            guardrail_metadata(
                thread_id="thread_1",
                workspace_id="workspace_1",
                campaign_id="campaign_1",
            ),
        )
        telemetry_service.record_evidence_result(
            "evidence-span",
            {"ok": True, "tool_name": "search_content_posts", "evidence_refs": ["post_1", "post_2"]},
        )
    finally:
        telemetry_service.tracing = original

    assert fake.outputs[0] == ("guardrail-span", {"passed": True, "mode": "json"})
    assert fake.metadata[0] == (
        "guardrail-span",
        {
            "thread_id": "thread_1",
            "workspace_id": "workspace_1",
            "campaign_id": "campaign_1",
            "validator_passed": True,
            "backtrack_count": 0,
        },
    )
    assert fake.documents[0] == ("evidence-span", [{"id": "post_1"}, {"id": "post_2"}])
    assert fake.outputs[1] == (
        "evidence-span",
        {"ok": True, "tool_name": "search_content_posts", "evidence_ref_count": 2},
    )
