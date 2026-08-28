from __future__ import annotations

import statistics
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from launchpilot.knowledge.contracts.retrieval import TextSearchHit


@dataclass(frozen=True, slots=True)
class RetrievalEvaluationResult:
    case_id: str
    query: str
    is_negative: bool
    target_refs: tuple[str, ...]
    retrieved_refs: tuple[str, ...]
    known_relevant_hit: bool | None
    known_relevant_recall: float | None
    reciprocal_rank: float | None
    judged_precision: float | None
    known_irrelevant_rejection_rate: float | None
    multihop_coverage: float | None
    unjudged_count: int
    negative_retrieval_abstained: bool | None
    latency_ms: float | None


class RetrievalStageEvaluator:
    """Query-to-retrieval diagnostics over explicitly judged evidence.

    Evidence absent from both target_refs and distractor_refs is unjudged.
    It is reported separately and is never silently treated as irrelevant.
    """

    def __init__(self, top_k: int = 5) -> None:
        if top_k < 1:
            raise ValueError("top_k must be positive")
        self.top_k = top_k

    def evaluate_case(
        self,
        case_id: str,
        query: str,
        target_refs: set[str],
        retrieved_hits: Sequence[TextSearchHit],
        distractor_refs: set[str],
        latency_ms: float | None,
    ) -> RetrievalEvaluationResult:
        selected = tuple(retrieved_hits[: self.top_k])
        hit_refs = tuple(_hit_refs(hit) for hit in selected)
        display_refs = tuple(_display_ref(refs) for refs in hit_refs)
        matched_targets = {
            target
            for target in target_refs
            if any(_matches_ref(target, refs) for refs in hit_refs)
        }
        matched_irrelevant = {
            irrelevant
            for irrelevant in distractor_refs
            if any(_matches_ref(irrelevant, refs) for refs in hit_refs)
        }
        relevant_hit_count = sum(
            any(_matches_ref(target, refs) for target in target_refs)
            for refs in hit_refs
        )
        irrelevant_hit_count = sum(
            any(_matches_ref(item, refs) for item in distractor_refs)
            for refs in hit_refs
        )
        unjudged_count = len(selected) - relevant_hit_count - irrelevant_hit_count
        judged_count = relevant_hit_count + irrelevant_hit_count
        judged_precision = relevant_hit_count / judged_count if judged_count else None
        irrelevant_rejection = (
            1.0 - (len(matched_irrelevant) / len(distractor_refs))
            if distractor_refs
            else None
        )

        if not target_refs:
            return RetrievalEvaluationResult(
                case_id=case_id,
                query=query,
                is_negative=True,
                target_refs=(),
                retrieved_refs=display_refs,
                known_relevant_hit=None,
                known_relevant_recall=None,
                reciprocal_rank=None,
                judged_precision=judged_precision,
                known_irrelevant_rejection_rate=irrelevant_rejection,
                multihop_coverage=None,
                unjudged_count=max(unjudged_count, 0),
                negative_retrieval_abstained=not selected,
                latency_ms=latency_ms,
            )

        first_relevant_rank = next(
            (
                rank
                for rank, refs in enumerate(hit_refs, start=1)
                if any(_matches_ref(target, refs) for target in target_refs)
            ),
            None,
        )
        recall = len(matched_targets) / len(target_refs)
        return RetrievalEvaluationResult(
            case_id=case_id,
            query=query,
            is_negative=False,
            target_refs=tuple(sorted(target_refs)),
            retrieved_refs=display_refs,
            known_relevant_hit=bool(matched_targets),
            known_relevant_recall=recall,
            reciprocal_rank=(
                1.0 / first_relevant_rank if first_relevant_rank is not None else 0.0
            ),
            judged_precision=judged_precision,
            known_irrelevant_rejection_rate=irrelevant_rejection,
            multihop_coverage=recall if len(target_refs) > 1 else None,
            unjudged_count=max(unjudged_count, 0),
            negative_retrieval_abstained=None,
            latency_ms=latency_ms,
        )

    def summarize(
        self, results: Sequence[RetrievalEvaluationResult]
    ) -> dict[str, int | float | None]:
        if not results:
            return {}
        positive = [result for result in results if not result.is_negative]
        negative = [result for result in results if result.is_negative]
        return {
            "total_evaluated_queries": len(results),
            "positive_queries": len(positive),
            "negative_queries": len(negative),
            "top_k": self.top_k,
            "known_relevant_hit_rate_at_k": _mean_optional(
                1.0 if result.known_relevant_hit else 0.0 for result in positive
            ),
            "known_relevant_recall_at_k": _mean_optional(
                result.known_relevant_recall for result in positive
            ),
            "mean_reciprocal_rank_at_k": _mean_optional(
                result.reciprocal_rank for result in positive
            ),
            "judged_precision_at_k": _mean_optional(
                result.judged_precision for result in results
            ),
            "known_irrelevant_rejection_rate": _mean_optional(
                result.known_irrelevant_rejection_rate for result in results
            ),
            "multihop_coverage": _mean_optional(
                result.multihop_coverage for result in positive
            ),
            "mean_unjudged_at_k": statistics.fmean(
                result.unjudged_count for result in results
            ),
            "negative_retrieval_abstention_rate": _mean_optional(
                1.0 if result.negative_retrieval_abstained else 0.0
                for result in negative
            ),
            "mean_retrieval_latency_ms": _mean_optional(
                result.latency_ms for result in results
            ),
        }


def _hit_refs(hit: TextSearchHit) -> frozenset[str]:
    refs = {str(hit.document_id).casefold()}
    source_ref = getattr(hit, "source_ref", None)
    if source_ref:
        refs.add(str(source_ref).casefold())
    return frozenset(refs)


def _display_ref(refs: frozenset[str]) -> str:
    return min(refs, key=lambda ref: (":" not in ref, ref))


def _matches_ref(expected: str, actual_refs: frozenset[str]) -> bool:
    return expected.casefold() in actual_refs


def _mean_optional(values: Iterable[float | None]) -> float | None:
    present = [value for value in values if value is not None]
    return statistics.fmean(present) if present else None
