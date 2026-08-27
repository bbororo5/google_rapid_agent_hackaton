from __future__ import annotations

import pytest
from launchpilot.evaluation.contracts import (
    Answerability,
    ArtifactVersions,
    EfficiencyObservation,
    EvalSpecification,
    EvidenceAssessment,
    EvidenceJudgment,
    ExpectedBehavior,
    GraderKind,
    InformationModality,
    OutcomeScores,
    PortfolioRole,
    QueryCharacteristics,
    QueryRecord,
    QuerySource,
    RequiredFact,
    ReviewStatus,
    SourceCardinality,
    TaskShape,
    ToolCallStatus,
    ToolCallTrace,
    TrialRunResult,
)
from pydantic import ValidationError


def _query() -> QueryRecord:
    return QueryRecord(
        query_id="production.001",
        text="지난달 예산 변경 원인과 이후 성과를 근거와 함께 비교해줘",
        source=QuerySource.PRODUCTION,
        portfolio=PortfolioRole.FROZEN,
        characteristics=QueryCharacteristics(
            modalities=(InformationModality.MIXED, InformationModality.RELATIONAL),
            entity_centric=True,
            hop_count=2,
            task_shape=TaskShape.COMPARISON,
            source_cardinality=SourceCardinality.MULTIPLE,
        ),
        leakage_group_ids=("campaign:17", "template:budget-comparison"),
    )


def _spec() -> EvalSpecification:
    return EvalSpecification(
        spec_id="production.001.spec",
        spec_version="v1",
        query_id="production.001",
        answerability=Answerability.ANSWERABLE,
        required_facts=(
            RequiredFact(
                fact_id="budget_change",
                description="변경 전후 예산과 변경 시점",
                grader=GraderKind.DETERMINISTIC,
                expected_values=("15%", "2026-07-12"),
            ),
        ),
        expected_behaviors=(ExpectedBehavior.ANSWER,),
        evidence_assessments=(
            EvidenceAssessment(
                evidence_ref="document:17",
                judgment=EvidenceJudgment.KNOWN_RELEVANT,
                relevance_grade=3,
                supports_fact_ids=("budget_change",),
            ),
            EvidenceAssessment(
                evidence_ref="document:18",
                judgment=EvidenceJudgment.UNJUDGED,
            ),
        ),
        review_status=ReviewStatus.HUMAN_REVIEWED,
        reviewer_ids=("reviewer-a", "reviewer-b"),
    )


def test_query_is_independent_from_tool_and_success_definition() -> None:
    query = _query()
    assert "expected_tool" not in QueryRecord.model_fields
    assert "route" not in QueryRecord.model_fields
    assert "answerability" not in QueryRecord.model_fields
    assert query.query_id == _spec().query_id


def test_unjudged_evidence_cannot_receive_a_relevance_grade() -> None:
    with pytest.raises(ValidationError, match="unjudged evidence"):
        EvidenceAssessment(
            evidence_ref="document:new-retriever-discovery",
            judgment=EvidenceJudgment.UNJUDGED,
            relevance_grade=1,
        )


def test_evidence_can_only_support_declared_required_facts() -> None:
    with pytest.raises(ValidationError, match="unknown required facts"):
        EvalSpecification(
            spec_id="production.001.spec",
            spec_version="v1",
            query_id="production.001",
            answerability=Answerability.ANSWERABLE,
            expected_behaviors=(ExpectedBehavior.ANSWER,),
            evidence_assessments=(
                EvidenceAssessment(
                    evidence_ref="document:17",
                    judgment=EvidenceJudgment.KNOWN_RELEVANT,
                    relevance_grade=3,
                    supports_fact_ids=("missing_fact",),
                ),
            ),
            review_status=ReviewStatus.NEEDS_REVIEW,
        )


def test_trial_keeps_outcome_process_and_efficiency_separate() -> None:
    trial = TrialRunResult(
        run_id="run-v1",
        system_version="sql-bm25-dense-graph-v2",
        query_id="production.001",
        spec_id="production.001.spec",
        spec_version="v1",
        trial_id="trial-03",
        versions=ArtifactVersions(
            corpus="corpus-v4",
            index="index-v8",
            model="model-v2",
            prompt="prompt-v9",
            toolset="toolset-v5",
            code_commit="abc1234",
        ),
        retrieved_evidence_refs=("document:17", "document:18"),
        final_answer="예산은 7월 12일에 15% 조정되었고 이후 효율이 회복되었습니다.",
        outcome=OutcomeScores(
            task_success=True,
            required_fact_coverage=1.0,
            groundedness=0.9,
            answer_relevance=1.0,
            behavior_correct=True,
        ),
        tool_trace=(
            ToolCallTrace(
                sequence=1,
                tool_name="keyword_search",
                status=ToolCallStatus.SUCCEEDED,
                latency_ms=12.0,
            ),
            ToolCallTrace(
                sequence=2,
                tool_name="graph_search",
                status=ToolCallStatus.SUCCEEDED,
                latency_ms=20.0,
                recovered=True,
            ),
        ),
        efficiency=EfficiencyObservation(
            end_to_end_latency_ms=950.0,
            retrieval_latency_ms=32.0,
            input_tokens=800,
            output_tokens=120,
            retrieval_context_tokens=500,
            cost_usd=0.004,
        ),
    )

    assert trial.outcome.task_success is True
    assert [call.tool_name for call in trial.tool_trace] == [
        "keyword_search",
        "graph_search",
    ]
    assert trial.efficiency.cost_usd == 0.004


def test_tool_trace_requires_contiguous_sequence() -> None:
    with pytest.raises(ValidationError, match="contiguous"):
        TrialRunResult(
            run_id="run-v1",
            system_version="v1",
            query_id="production.001",
            spec_id="production.001.spec",
            spec_version="v1",
            trial_id="trial-01",
            versions=ArtifactVersions(
                corpus="c",
                index="i",
                model="m",
                prompt="p",
                toolset="t",
                code_commit="abc",
            ),
            final_answer="",
            outcome=OutcomeScores(
                task_success=False,
                required_fact_coverage=0.0,
                behavior_correct=False,
            ),
            tool_trace=(
                ToolCallTrace(
                    sequence=2,
                    tool_name="dense_search",
                    status=ToolCallStatus.FAILED,
                    latency_ms=10,
                ),
            ),
            efficiency=EfficiencyObservation(end_to_end_latency_ms=15),
        )
