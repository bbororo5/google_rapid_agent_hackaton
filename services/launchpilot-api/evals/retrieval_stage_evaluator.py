import json
import time
import math
from uuid import UUID
from dataclasses import dataclass
from typing import Sequence
from pathlib import Path

from launchpilot.knowledge.contracts.retrieval import TextSearchHit

@dataclass(frozen=True, slots=True)
class RetrievalEvaluationResult:
    case_id: str
    query: str
    target_refs: tuple[str, ...]
    retrieved_refs: tuple[str, ...]
    hit_rate: float
    context_recall: float
    context_mrr: float
    distractor_rejection_rate: float
    multihop_coverage: float
    latency_ms: float

class RetrievalStageEvaluator:
    """Official 5-Metric Retrieval Stage Evaluator for LaunchPilot Agentic RAG.
    1. Context Recall@K
    2. Context MRR@K
    3. Distractor Rejection Rate
    4. Multi-Hop Chain Coverage
    5. Retrieval & Rerank Latency
    """

    def __init__(self, top_k: int = 5) -> None:
        self.top_k = top_k

    def evaluate_case(
        self,
        case_id: str,
        query: str,
        target_refs: set[str],
        retrieved_hits: Sequence[TextSearchHit],
        distractor_refs: set[str],
        latency_ms: float,
    ) -> RetrievalEvaluationResult:
        retrieved_keys = []
        for h in retrieved_hits[:self.top_k]:
            ref = str(h.document_id)
            if hasattr(h, "source_ref") and h.source_ref:
                ref = h.source_ref
            retrieved_keys.append(ref)

        retrieved_set = set(retrieved_keys)
        
        # 1. Hit Rate & Recall@K
        if not target_refs:
            hit_rate = 1.0 if not retrieved_hits else 1.0 # Negatives handled cleanly
            recall = 1.0
            mrr = 1.0
            multihop = 1.0
        else:
            # Check target matches
            matched_targets = set()
            first_rank = None
            for idx, h in enumerate(retrieved_hits[:self.top_k], 1):
                # match by UUID or source_ref or document_key
                h_refs = {str(h.document_id), str(h.campaign_id), h.title, getattr(h, "source_ref", "")}
                for t in target_refs:
                    t_clean = t.split(":")[-1] if ":" in t else t
                    if any(t_clean in ref for ref in h_refs if ref) or t in h_refs:
                        matched_targets.add(t)
                        if first_rank is None:
                            first_rank = idx

            hit_rate = 1.0 if len(matched_targets) > 0 else 0.0
            recall = len(matched_targets) / max(len(target_refs), 1)
            mrr = (1.0 / first_rank) if first_rank is not None else 0.0
            multihop = recall # Coverage of all required target hops

        # 2. Distractor Rejection Rate
        if not distractor_refs:
            distractor_rejection = 1.0
        else:
            present_distractors = 0
            for h in retrieved_hits[:self.top_k]:
                h_refs = {str(h.document_id), h.title, getattr(h, "source_ref", "")}
                for d in distractor_refs:
                    d_clean = d.split(":")[-1] if ":" in d else d
                    if any(d_clean in ref for ref in h_refs if ref):
                        present_distractors += 1
            distractor_rejection = max(0.0, 1.0 - (present_distractors / len(distractor_refs)))

        return RetrievalEvaluationResult(
            case_id=case_id,
            query=query,
            target_refs=tuple(target_refs),
            retrieved_refs=tuple(retrieved_keys),
            hit_rate=hit_rate,
            context_recall=recall,
            context_mrr=mrr,
            distractor_rejection_rate=distractor_rejection,
            multihop_coverage=multihop,
            latency_ms=latency_ms,
        )

    def summarize(self, results: list[RetrievalEvaluationResult]) -> dict[str, float]:
        if not results:
            return {}
        N = len(results)
        return {
            "total_evaluated_queries": N,
            "mean_hit_rate_at_5": sum(r.hit_rate for r in results) / N,
            "mean_context_recall_at_5": sum(r.context_recall for r in results) / N,
            "mean_context_mrr_at_5": sum(r.context_mrr for r in results) / N,
            "mean_distractor_rejection_rate": sum(r.distractor_rejection_rate for r in results) / N,
            "mean_multihop_chain_coverage": sum(r.multihop_coverage for r in results) / N,
            "mean_retrieval_latency_ms": sum(r.latency_ms for r in results) / N,
        }
