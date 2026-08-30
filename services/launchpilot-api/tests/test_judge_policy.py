from __future__ import annotations

import hashlib
import json
from pathlib import Path

from launchpilot.evaluation.contracts import (
    Answerability,
    EvalSpecification,
    EvidenceAssessment,
    EvidenceJudgment,
    ExpectedBehavior,
    GraderKind,
    RequiredFact,
    ReviewStatus,
)
from launchpilot.evaluation.judging.contracts import (
    BehaviorJudgment,
    ClaimJudgment,
    ClaimSupport,
    ConfidenceLevel,
    FactJudgment,
    JudgeVerdict,
    RelevanceJudgment,
    TaskJudgment,
)
from launchpilot.evaluation.judging.policy import (
    TaskGradingPolicy,
    retrieval_diagnostics,
)
from launchpilot.evaluation.judging.world_evidence import WorldEvidenceResolver
from launchpilot.evaluation.task_dataset import WorldArtifact, WorldManifest


def _spec() -> EvalSpecification:
    return EvalSpecification(
        spec_id="q1.spec",
        spec_version="judge-ready-2026-08",
        problem_id="q1",
        answerability=Answerability.ANSWERABLE,
        required_facts=(
            RequiredFact(
                fact_id="cause",
                description="예산 초과 소진",
                grader=GraderKind.LLM_JUDGE,
            ),
        ),
        expected_behaviors=(ExpectedBehavior.ANSWER,),
        evidence_assessments=(
            EvidenceAssessment(
                evidence_ref="c0001:memo_01",
                judgment=EvidenceJudgment.KNOWN_RELEVANT,
                relevance_grade=3,
                supports_fact_ids=("cause",),
            ),
            EvidenceAssessment(
                evidence_ref="c0001:memo_02",
                judgment=EvidenceJudgment.KNOWN_IRRELEVANT,
                relevance_grade=0,
            ),
        ),
        review_status=ReviewStatus.MACHINE_ADJUDICATED,
        grader_rubric_version="task-answer-v1",
    )


def _judgment(fact_verdict=JudgeVerdict.ENTAILED) -> TaskJudgment:
    return TaskJudgment(
        fact_judgments=(
            FactJudgment(
                fact_id="cause",
                verdict=fact_verdict,
                confidence=ConfidenceLevel.HIGH,
                answer_spans=("초과 소진",),
                evidence_refs=("c0001:memo_01",),
                rationale="답과 근거가 일치한다.",
            ),
        ),
        claim_judgments=(
            ClaimJudgment(
                claim="예산이 초과 소진되었다.",
                answer_span="예산이 초과 소진",
                support=ClaimSupport.SUPPORTED,
                confidence=ConfidenceLevel.HIGH,
                evidence_refs=("c0001:memo_01",),
                rationale="근거가 직접 지지한다.",
            ),
        ),
        behavior=BehaviorJudgment(
            observed_behavior=ExpectedBehavior.ANSWER,
            correct=True,
            confidence=ConfidenceLevel.HIGH,
            rationale="질문에 답했다.",
        ),
        answer_relevance=RelevanceJudgment.RELEVANT,
        answer_relevance_rationale="질문을 직접 해결한다.",
    )


def test_policy_aggregates_atomic_verdicts_in_code() -> None:
    passed = TaskGradingPolicy().aggregate(_spec(), _judgment())
    assert passed.task_success is True
    assert passed.required_fact_coverage == 1.0
    assert passed.groundedness == 1.0

    partial = TaskGradingPolicy().aggregate(
        _spec(), _judgment(JudgeVerdict.PARTIALLY_ENTAILED)
    )
    assert partial.task_success is False
    assert partial.required_fact_coverage == 0.5


def test_retrieval_diagnostics_preserve_unjudged_results() -> None:
    diagnostics = retrieval_diagnostics(
        _spec(),
        ("c0001:memo_01", "new:dense-discovery", "c0001:memo_02"),
    )
    assert diagnostics.cutoff_k == 3
    assert diagnostics.known_relevant_recall_at_k == 1.0
    assert diagnostics.judged_precision_at_k == 0.5
    assert diagnostics.unjudged_at_k == 1
    assert diagnostics.answer_bearing_evidence_retrieved is True


def test_world_evidence_resolver_uses_canonical_artifact_and_rejects_unknown(
    tmp_path: Path,
) -> None:
    root = tmp_path / "dataset"
    corpus = root / "corpus" / "documents.jsonl"
    corpus.parent.mkdir(parents=True)
    record = {
        "id": "uuid-1",
        "document_key": "c0001:memo_01",
        "title": "예산 조정 메모",
        "document_type": "MEMO",
        "content": "예산 초과 소진으로 일 예산을 삭감했다.",
    }
    corpus.write_text(json.dumps(record, ensure_ascii=False) + "\n", encoding="utf-8")
    world = WorldManifest(
        world_id="world-1",
        world_version="snapshot-1",
        source_type="synthetic",
        description="fixture",
        artifacts=(
            WorldArtifact(
                role="documents",
                path="corpus/documents.jsonl",
                sha256=hashlib.sha256(corpus.read_bytes()).hexdigest(),
                record_count=1,
            ),
        ),
    )
    resolver = WorldEvidenceResolver(root, world)

    resolved = resolver.resolve(("c0001:memo_01",))[0]
    assert resolved.title == "예산 조정 메모"
    assert "예산 초과 소진" in resolved.content
    assert resolver.resolve(("uuid-1",))[0].record_fingerprint == resolved.record_fingerprint
    observation = resolver.resolve_observation(
        ("c0001:memo_01", "hallucinated-ref")
    )
    assert tuple(item.evidence_ref for item in observation.resolved) == (
        "c0001:memo_01",
    )
    assert observation.unknown_refs == ("hallucinated-ref",)

    try:
        resolver.resolve(("missing",))
    except KeyError as error:
        assert "unknown canonical evidence refs" in str(error)
    else:
        raise AssertionError("unknown evidence ref should fail closed")
