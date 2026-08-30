from __future__ import annotations

import pytest
from pydantic import ValidationError

from launchpilot.evaluation.contracts import (
    Answerability,
    ArtifactVersions,
    EfficiencyObservation,
    EvalSpecification,
    EvidenceAssessment,
    EvidenceJudgment,
    ExpectedBehavior,
    GraderEfficiencyObservation,
    GraderKind,
    InformationModality,
    OutcomeScores,
    PortfolioRole,
    ProblemProvenance,
    ProblemRecord,
    QueryCharacteristics,
    QueryRecord,
    QuerySource,
    RequiredFact,
    RetrievalDiagnostics,
    ReviewStatus,
    SourceCardinality,
    SuppliedContext,
    TaskShape,
    ToolCallStatus,
    ToolCallTrace,
    TrialRunResult,
)


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


def test_problem_is_the_canonical_serialized_unit_with_legacy_read_aliases() -> None:
    problem = ProblemRecord(
        problem_id="encounter.001",
        user_utterance="지난달 조정 원인을 알려줘",
        information_need="예산 조정의 원인과 근거를 확인한다.",
        world_id="marketing-world-v1",
        supplied_context=(
            SuppliedContext(key="active_campaign_ref", value="C0017"),
        ),
        source=QuerySource.PRODUCTION,
        portfolio=PortfolioRole.FRONTIER,
        characteristics=QueryCharacteristics(
            modalities=(InformationModality.MIXED,),
            task_shape=TaskShape.LOOKUP,
        ),
        provenance=ProblemProvenance(
            source_dataset="production-sample-2026-08",
            source_record_id="request-17",
            generation_method="production_sample",
        ),
    )

    assert problem.query_id == problem.problem_id
    assert problem.text == problem.user_utterance
    assert problem.model_dump(mode="json")["problem_id"] == "encounter.001"
    assert "query_id" not in problem.model_dump(mode="json")

    legacy = ProblemRecord.model_validate(
        {
            "query_id": "legacy.001",
            "text": "legacy query",
            "source": "synthetic",
            "portfolio": "frontier",
            "characteristics": {
                "modalities": ["unstructured"],
                "task_shape": "lookup",
            },
        }
    )
    assert legacy.problem_id == "legacy.001"


def test_unjudged_evidence_cannot_receive_a_relevance_grade() -> None:
    with pytest.raises(ValidationError, match="unjudged evidence"):
        EvidenceAssessment(
            evidence_ref="document:new-retriever-discovery",
            judgment=EvidenceJudgment.UNJUDGED,
            relevance_grade=1,
        )


def test_retrieval_metrics_require_an_explicit_cutoff_and_unknown_stays_none() -> None:
    assert RetrievalDiagnostics().unjudged_at_k is None
    with pytest.raises(ValidationError, match="require cutoff_k"):
        RetrievalDiagnostics(known_relevant_recall_at_k=0.5)
    with pytest.raises(ValidationError, match="cannot exceed cutoff_k"):
        RetrievalDiagnostics(cutoff_k=5, unjudged_at_k=6)


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


def test_evidence_and_human_review_provenance_invariants() -> None:
    relevant = EvidenceAssessment(
        evidence_ref="document:17",
        judgment=EvidenceJudgment.KNOWN_RELEVANT,
        relevance_grade=2,
    )
    duplicate_payload = _spec().model_dump(mode="json")
    duplicate_payload["evidence_assessments"] = [
        relevant.model_dump(mode="json"),
        relevant.model_dump(mode="json"),
    ]
    with pytest.raises(ValidationError, match="evidence_ref values must be unique"):
        EvalSpecification.model_validate(duplicate_payload)
    with pytest.raises(ValidationError, match="only known relevant"):
        EvidenceAssessment(
            evidence_ref="document:irrelevant",
            judgment=EvidenceJudgment.KNOWN_IRRELEVANT,
            supports_fact_ids=("budget_change",),
        )
    with pytest.raises(ValidationError, match="require reviewer_ids"):
        EvalSpecification.model_validate(
            _spec().model_dump(mode="json", exclude={"reviewer_ids"})
        )

    missing_rubric = _spec().model_dump(mode="json")
    missing_rubric["required_facts"][0]["grader"] = "human"
    with pytest.raises(ValidationError, match="require grader_rubric_version"):
        EvalSpecification.model_validate(missing_rubric)


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
        grader_efficiency=GraderEfficiencyObservation(
            latency_ms=240.0,
            input_tokens=500,
            output_tokens=80,
            thought_tokens=120,
            cost_usd=0.002,
            telemetry_complete=True,
        ),
    )

    assert trial.outcome.task_success is True
    assert [call.tool_name for call in trial.tool_trace] == [
        "keyword_search",
        "graph_search",
    ]
    assert trial.efficiency.cost_usd == 0.004
    assert trial.grader_efficiency.cost_usd == 0.002

    payload = trial.model_dump(mode="json")
    payload["started_at"] = "2026-08-27T12:00:00"
    with pytest.raises(ValidationError, match="must include a timezone"):
        TrialRunResult.model_validate(payload)

    contradictory_failure = trial.model_dump(mode="json")
    contradictory_failure.update(
        {
            "status": "system_failed",
            "failure_stage": "grading",
            "error_type": "ProviderError",
            "outcome": {
                "task_success": False,
                "required_fact_coverage": 0.0,
                "groundedness": None,
                "answer_relevance": None,
                "behavior_correct": False,
            },
        }
    )
    with pytest.raises(ValidationError, match="require execution stage"):
        TrialRunResult.model_validate(contradictory_failure)

    grading_failure = trial.model_dump(mode="json")
    grading_failure.update(
        {
            "status": "grading_failed",
            "failure_stage": "execution",
            "error_type": "JudgeProviderError",
            "outcome": {
                "task_success": False,
                "required_fact_coverage": 0.0,
                "groundedness": None,
                "answer_relevance": None,
                "behavior_correct": False,
            },
        }
    )
    with pytest.raises(ValidationError, match="require grading stage"):
        TrialRunResult.model_validate(grading_failure)


def test_machine_adjudication_is_distinct_from_human_review() -> None:
    payload = _spec().model_dump(mode="json")
    payload.update(
        {
            "review_status": "machine_adjudicated",
            "reviewer_ids": [],
        }
    )
    spec = EvalSpecification.model_validate(payload)
    assert spec.review_status == ReviewStatus.MACHINE_ADJUDICATED


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
