from __future__ import annotations

import math
from dataclasses import dataclass

from launchpilot.evaluation.contracts import (
    Answerability,
    EvalSpecification,
    EvidenceJudgment,
    OutcomeScores,
    RetrievalDiagnostics,
)

from .contracts import (
    ClaimSupport,
    JudgeVerdict,
    RelevanceJudgment,
    TaskJudgment,
)


@dataclass(frozen=True, slots=True)
class TaskGradingPolicy:
    policy_version: str = "task-answer-policy-v1"
    minimum_groundedness: float = 0.9
    minimum_answer_relevance: float = 0.5

    def aggregate(
        self,
        specification: EvalSpecification,
        judgment: TaskJudgment,
    ) -> OutcomeScores:
        expected_fact_ids = {fact.fact_id for fact in specification.required_facts}
        actual_fact_ids = {fact.fact_id for fact in judgment.fact_judgments}
        if expected_fact_ids != actual_fact_ids:
            raise ValueError(
                "judge fact ids do not match specification: "
                f"expected={sorted(expected_fact_ids)} actual={sorted(actual_fact_ids)}"
            )
        coverage = _fact_coverage(judgment)
        groundedness = _groundedness(judgment)
        relevance = _answer_relevance(judgment.answer_relevance)
        behavior_correct = judgment.behavior.correct

        if specification.answerability == Answerability.ANSWERABLE:
            task_success = (
                behavior_correct
                and coverage == 1.0
                and relevance is not None
                and relevance >= self.minimum_answer_relevance
                and groundedness is not None
                and groundedness >= self.minimum_groundedness
                and not judgment.indeterminate_reason
            )
        else:
            fabricated_claim = any(
                claim.support in {ClaimSupport.UNSUPPORTED, ClaimSupport.CONTRADICTED}
                for claim in judgment.claim_judgments
            )
            task_success = (
                behavior_correct
                and not fabricated_claim
                and not judgment.indeterminate_reason
            )
        return OutcomeScores(
            task_success=task_success,
            required_fact_coverage=coverage,
            groundedness=groundedness,
            answer_relevance=relevance,
            behavior_correct=behavior_correct,
        )


def retrieval_diagnostics(
    specification: EvalSpecification,
    retrieved_evidence_refs: tuple[str, ...],
) -> RetrievalDiagnostics:
    cutoff = len(retrieved_evidence_refs)
    assessments = {
        item.evidence_ref: item for item in specification.evidence_assessments
    }
    relevant = {
        ref
        for ref, item in assessments.items()
        if item.judgment == EvidenceJudgment.KNOWN_RELEVANT
    }
    retrieved = set(retrieved_evidence_refs)
    known_recall = len(retrieved & relevant) / len(relevant) if relevant else None
    judged_retrieved = [
        ref
        for ref in retrieved_evidence_refs
        if ref in assessments
        and assessments[ref].judgment
        in {EvidenceJudgment.KNOWN_RELEVANT, EvidenceJudgment.KNOWN_IRRELEVANT}
    ]
    judged_relevant = sum(ref in relevant for ref in judged_retrieved)
    judged_precision = (
        judged_relevant / len(judged_retrieved) if judged_retrieved else None
    )
    unjudged = sum(
        ref not in assessments
        or assessments[ref].judgment == EvidenceJudgment.UNJUDGED
        for ref in retrieved_evidence_refs
    )
    ndcg = _ndcg(retrieved_evidence_refs, assessments) if relevant else None
    answer_bearing = any(
        ref in assessments
        and assessments[ref].judgment == EvidenceJudgment.KNOWN_RELEVANT
        and bool(assessments[ref].supports_fact_ids)
        for ref in retrieved_evidence_refs
    )
    return RetrievalDiagnostics(
        cutoff_k=cutoff or None,
        known_relevant_recall_at_k=known_recall if cutoff else None,
        judged_precision_at_k=judged_precision if cutoff else None,
        ndcg_at_k=ndcg if cutoff else None,
        unjudged_at_k=unjudged if cutoff else None,
        answer_bearing_evidence_retrieved=answer_bearing,
    )


def _fact_coverage(judgment: TaskJudgment) -> float:
    if not judgment.fact_judgments:
        return 1.0
    weights = {
        JudgeVerdict.ENTAILED: 1.0,
        JudgeVerdict.PARTIALLY_ENTAILED: 0.5,
        JudgeVerdict.NOT_ENTAILED: 0.0,
        JudgeVerdict.CONTRADICTED: 0.0,
        JudgeVerdict.INDETERMINATE: 0.0,
    }
    return sum(weights[item.verdict] for item in judgment.fact_judgments) / len(
        judgment.fact_judgments
    )


def _groundedness(judgment: TaskJudgment) -> float | None:
    if not judgment.claim_judgments:
        return None
    supported = sum(
        claim.support == ClaimSupport.SUPPORTED for claim in judgment.claim_judgments
    )
    return supported / len(judgment.claim_judgments)


def _answer_relevance(verdict: RelevanceJudgment) -> float | None:
    return {
        RelevanceJudgment.RELEVANT: 1.0,
        RelevanceJudgment.PARTIALLY_RELEVANT: 0.5,
        RelevanceJudgment.IRRELEVANT: 0.0,
        RelevanceJudgment.INDETERMINATE: None,
    }[verdict]


def _ndcg(retrieved, assessments) -> float:
    gains = [
        assessments[ref].relevance_grade or 0
        if ref in assessments
        and assessments[ref].judgment == EvidenceJudgment.KNOWN_RELEVANT
        else 0
        for ref in retrieved
    ]
    ideal = sorted(
        [
            item.relevance_grade or 0
            for item in assessments.values()
            if item.judgment == EvidenceJudgment.KNOWN_RELEVANT
        ],
        reverse=True,
    )[: len(retrieved)]

    def dcg(values) -> float:
        return sum((2**gain - 1) / math.log2(index + 2) for index, gain in enumerate(values))

    ideal_dcg = dcg(ideal)
    return dcg(gains) / ideal_dcg if ideal_dcg else 0.0
