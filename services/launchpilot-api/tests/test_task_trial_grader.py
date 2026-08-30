from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from launchpilot.evaluation.contracts import (
    Answerability,
    EfficiencyObservation,
    EvalSpecification,
    EvidenceAssessment,
    EvidenceJudgment,
    ExpectedBehavior,
    GraderKind,
    InformationModality,
    PortfolioRole,
    ProblemRecord,
    QueryCharacteristics,
    QuerySource,
    RequiredFact,
    ReviewStatus,
    TaskShape,
)
from launchpilot.evaluation.controlled_runner import (
    GraderProvenance,
    TrialObservation,
)
from launchpilot.evaluation.judging.contracts import (
    BehaviorJudgment,
    ClaimJudgment,
    ClaimSupport,
    ConfidenceLevel,
    FactJudgment,
    JudgeCall,
    JudgeCallMetadata,
    JudgeVerdict,
    RelevanceJudgment,
    TaskJudgment,
)
from launchpilot.evaluation.judging.task_grader import (
    GeminiTaskTrialGrader,
    TaskAnswerRubric,
)
from launchpilot.evaluation.judging.world_evidence import WorldEvidenceResolver
from launchpilot.evaluation.task_dataset import WorldArtifact, WorldManifest


class _FakeJudgeClient:
    def __init__(self, judgment: TaskJudgment) -> None:
        self.settings = SimpleNamespace(
            model="gemini-3.7-flash", thinking_level="medium"
        )
        self.judgment = judgment
        self.input_payload: dict[str, object] | None = None

    def judge(self, **kwargs) -> JudgeCall[TaskJudgment]:
        self.input_payload = json.loads(kwargs["input_text"])
        return JudgeCall[TaskJudgment](
            payload=self.judgment,
            metadata=JudgeCallMetadata(
                model="gemini-3.7-flash",
                thinking_level="medium",
                request_id="judge-request-1",
                requested_seed=kwargs["requested_seed"],
                latency_ms=25.0,
                input_tokens=100,
                output_tokens=40,
                thought_tokens=15,
                retry_count=0,
                response_fingerprint="sha256:" + "a" * 64,
                response_status="completed",
            ),
        )


def test_task_grader_keeps_gold_hidden_and_aggregates_atomic_judgment(
    tmp_path: Path,
) -> None:
    client = _FakeJudgeClient(_judgment())
    grader = GeminiTaskTrialGrader(
        client=client,  # type: ignore[arg-type]
        resolver=_resolver(tmp_path),
        rubric=_rubric(),
    )
    observation = TrialObservation(
        final_answer="예산 초과 소진 때문에 삭감했습니다.",
        retrieved_evidence_refs=("doc-1", "hallucinated-ref"),
        efficiency=EfficiencyObservation(end_to_end_latency_ms=10),
    )
    grade = grader.grade(
        query=_problem(),
        specification=_spec(),
        observation=observation,
        provenance=_provenance(),
        requested_seed=7,
    )

    assert grade.outcome.task_success is True
    assert grade.grader_request_id == "judge-request-1"
    assert grade.grader_efficiency is not None
    assert grade.grader_efficiency.thought_tokens == 15
    assert grade.grade_artifact_ref is not None
    assert grade.grade_details is not None
    assert grade.grade_details["unknown_evidence_refs"] == ["hallucinated-ref"]
    assert client.input_payload is not None
    serialized = json.dumps(client.input_payload, ensure_ascii=False)
    assert "known_relevant" not in serialized
    assert "reference_answer" not in serialized
    retrieved = client.input_payload["run_result"]["retrieved_evidence"]  # type: ignore[index]
    assert [item["evidence_ref"] for item in retrieved] == ["doc-1"]


def test_task_grader_rejects_judge_citation_not_present_in_context(
    tmp_path: Path,
) -> None:
    payload = _judgment().model_dump(mode="json")
    payload["fact_judgments"][0]["evidence_refs"] = ["foreign-doc"]
    grader = GeminiTaskTrialGrader(
        client=_FakeJudgeClient(TaskJudgment.model_validate(payload)),  # type: ignore[arg-type]
        resolver=_resolver(tmp_path),
        rubric=_rubric(),
    )
    with pytest.raises(ValueError, match="absent from trial context"):
        grader.grade(
            query=_problem(),
            specification=_spec(),
            observation=TrialObservation(
                final_answer="답변",
                retrieved_evidence_refs=("doc-1",),
                efficiency=EfficiencyObservation(end_to_end_latency_ms=10),
            ),
            provenance=_provenance(),
            requested_seed=7,
        )


def _problem() -> ProblemRecord:
    return ProblemRecord(
        problem_id="q1",
        user_utterance="왜 예산을 삭감했나요?",
        information_need="예산 삭감 원인을 설명한다.",
        world_id="world-1",
        source=QuerySource.SYNTHETIC,
        portfolio=PortfolioRole.FRONTIER,
        characteristics=QueryCharacteristics(
            modalities=(InformationModality.UNSTRUCTURED,),
            task_shape=TaskShape.LOOKUP,
        ),
    )


def _spec() -> EvalSpecification:
    return EvalSpecification(
        spec_id="q1.spec",
        spec_version="judge-ready-2026-08",
        problem_id="q1",
        answerability=Answerability.ANSWERABLE,
        required_facts=(
            RequiredFact(
                fact_id="cause",
                description="예산 초과 소진이 원인이다.",
                grader=GraderKind.LLM_JUDGE,
            ),
        ),
        expected_behaviors=(ExpectedBehavior.ANSWER,),
        evidence_assessments=(
            EvidenceAssessment(
                evidence_ref="doc-1",
                judgment=EvidenceJudgment.KNOWN_RELEVANT,
                relevance_grade=3,
                supports_fact_ids=("cause",),
            ),
        ),
        review_status=ReviewStatus.MACHINE_ADJUDICATED,
        grader_rubric_version="task-answer-v1",
    )


def _judgment() -> TaskJudgment:
    return TaskJudgment(
        fact_judgments=(
            FactJudgment(
                fact_id="cause",
                verdict=JudgeVerdict.ENTAILED,
                confidence=ConfidenceLevel.HIGH,
                answer_spans=("예산 초과 소진",),
                evidence_refs=("doc-1",),
                rationale="답과 근거가 직접 일치한다.",
            ),
        ),
        claim_judgments=(
            ClaimJudgment(
                claim="예산 초과 소진이 원인이다.",
                support=ClaimSupport.SUPPORTED,
                confidence=ConfidenceLevel.HIGH,
                answer_span="예산 초과 소진 때문에",
                evidence_refs=("doc-1",),
                rationale="문서가 지지한다.",
            ),
        ),
        behavior=BehaviorJudgment(
            observed_behavior=ExpectedBehavior.ANSWER,
            correct=True,
            confidence=ConfidenceLevel.HIGH,
            rationale="질문에 직접 답했다.",
        ),
        answer_relevance=RelevanceJudgment.RELEVANT,
        answer_relevance_rationale="질문의 원인을 설명한다.",
    )


def _resolver(tmp_path: Path) -> WorldEvidenceResolver:
    corpus = tmp_path / "documents.jsonl"
    corpus.write_text(
        json.dumps(
            {
                "document_key": "doc-1",
                "title": "예산 메모",
                "content": "예산 초과 소진 때문에 예산을 삭감했다.",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    world = WorldManifest(
        world_id="world-1",
        world_version="snapshot-1",
        source_type="synthetic",
        description="fixture",
        artifacts=(
            WorldArtifact(
                role="documents",
                path="documents.jsonl",
                sha256=hashlib.sha256(corpus.read_bytes()).hexdigest(),
                record_count=1,
            ),
        ),
    )
    return WorldEvidenceResolver(tmp_path, world)


def _rubric() -> TaskAnswerRubric:
    return TaskAnswerRubric(
        rubric_version="task-answer-v1",
        response_schema_version="task-judgment-v1",
        system_instruction="Judge only the supplied evidence.",
    )


def _provenance() -> GraderProvenance:
    return GraderProvenance(
        grader_id="gemini-task-judge",
        code_commit="test",
        rubric_version="task-answer-v1",
        model="gemini-3.7-flash",
        provider="vertex_ai",
        thinking_level="medium",
        prompt_version="task-answer-v1",
        response_schema_version="task-judgment-v1",
        compatible_spec_rubric_versions=("task-answer-v1",),
        seed=7,
    )
