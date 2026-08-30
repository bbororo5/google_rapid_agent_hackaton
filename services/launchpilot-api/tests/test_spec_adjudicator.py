from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from launchpilot.evaluation.contracts import (
    Answerability,
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
from launchpilot.evaluation.judging.contracts import (
    JudgeCall,
    JudgeCallMetadata,
    SpecificationAdjudication,
    SpecificationAdjudicationVerdict,
)
from launchpilot.evaluation.judging.spec_adjudicator import (
    AdjudicationDecision,
    GeminiSpecificationAdjudicator,
    SpecificationAdjudicationRubric,
)
from launchpilot.evaluation.judging.world_evidence import WorldEvidenceResolver
from launchpilot.evaluation.task_dataset import WorldArtifact, WorldManifest


class _FakeClient:
    settings = SimpleNamespace(model="gemini-3.7-flash", thinking_level="medium")

    def __init__(self, verdicts: tuple[SpecificationAdjudication, ...]) -> None:
        self._verdicts = iter(verdicts)
        self.seeds: list[int | None] = []

    def judge(self, **kwargs) -> JudgeCall[SpecificationAdjudication]:
        self.seeds.append(kwargs["requested_seed"])
        payload = next(self._verdicts)
        return JudgeCall[SpecificationAdjudication](
            payload=payload,
            metadata=JudgeCallMetadata(
                model="gemini-3.7-flash",
                thinking_level="medium",
                requested_seed=kwargs["requested_seed"],
                latency_ms=10,
                retry_count=0,
                response_fingerprint="sha256:" + "a" * 64,
                response_status="completed",
            ),
        )


def test_two_pass_acceptance_requires_consensus(tmp_path: Path) -> None:
    accepted = _verdict(SpecificationAdjudicationVerdict.ACCEPT)
    client = _FakeClient((accepted, accepted))
    record = _adjudicator(tmp_path, client).adjudicate(
        problem=_problem(), specification=_spec(), base_seed=10
    )
    assert record.decision == AdjudicationDecision.ACCEPTED
    assert client.seeds == [11, 12]
    assert len(record.passes) == 2


def test_disagreement_needs_review_and_negative_spec_is_not_false_certified(
    tmp_path: Path,
) -> None:
    accept = _verdict(SpecificationAdjudicationVerdict.ACCEPT)
    indeterminate = _verdict(SpecificationAdjudicationVerdict.INDETERMINATE)
    record = _adjudicator(tmp_path, _FakeClient((accept, indeterminate))).adjudicate(
        problem=_problem(), specification=_spec()
    )
    assert record.decision == AdjudicationDecision.NEEDS_REVIEW

    negative = _spec().model_copy(
        update={
            "answerability": Answerability.INSUFFICIENT_EVIDENCE,
            "required_facts": (),
            "expected_behaviors": (ExpectedBehavior.ABSTAIN,),
            "evidence_assessments": (),
        }
    )
    with pytest.raises(ValueError, match="empty qrels cannot prove absence"):
        _adjudicator(tmp_path, _FakeClient((accept, accept))).adjudicate(
            problem=_problem(), specification=negative
        )


def _verdict(value: SpecificationAdjudicationVerdict) -> SpecificationAdjudication:
    accepted = value == SpecificationAdjudicationVerdict.ACCEPT
    return SpecificationAdjudication(
        verdict=value,
        problem_spec_aligned=accepted,
        required_facts_supported=accepted,
        answerability_consistent=accepted,
        behavior_consistent=accepted,
        tool_independent=accepted,
        rationale="독립 검토 결과이다.",
    )


def _problem() -> ProblemRecord:
    return ProblemRecord(
        problem_id="q1",
        user_utterance="왜 예산을 삭감했나요?",
        information_need="예산 삭감 원인을 확인한다.",
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
        spec_version="v1-draft",
        problem_id="q1",
        answerability=Answerability.ANSWERABLE,
        required_facts=(
            RequiredFact(
                fact_id="cause",
                description="예산 초과 소진이 원인이다.",
                grader=GraderKind.HUMAN,
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
        review_status=ReviewStatus.NEEDS_REVIEW,
        grader_rubric_version="task-required-facts-v1-draft",
    )


def _adjudicator(tmp_path: Path, client: _FakeClient):
    corpus = tmp_path / "documents.jsonl"
    corpus.write_text(
        json.dumps(
            {"document_key": "doc-1", "content": "예산 초과 소진으로 삭감했다."},
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    world = WorldManifest(
        world_id="world-1",
        world_version="v1",
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
    return GeminiSpecificationAdjudicator(
        client=client,  # type: ignore[arg-type]
        resolver=WorldEvidenceResolver(tmp_path, world),
        rubric=SpecificationAdjudicationRubric(
            rubric_version="spec-adjudication-v1",
            response_schema_version="specification-adjudication-v1",
            system_instruction="Audit the specification.",
        ),
    )
