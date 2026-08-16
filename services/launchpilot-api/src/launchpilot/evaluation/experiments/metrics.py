from __future__ import annotations

import math
from collections.abc import Sequence

from .contracts import CaseMetrics, Chunk, GoldEvidence, ScoredChunk


def retrieval_metrics(
    hits: Sequence[ScoredChunk],
    evidence: Sequence[GoldEvidence],
    *,
    top_k: int,
) -> CaseMetrics:
    selected = tuple(hits[:top_k])
    matched_evidence = {
        index
        for index, gold in enumerate(evidence)
        if any(_matches(hit.chunk, gold) for hit in selected)
    }
    recall = len(matched_evidence) / len(evidence)
    gains = _deduplicated_gains(selected, evidence)
    first_relevant = next(
        (rank for rank, gain in enumerate(gains, start=1) if gain > 0), None
    )
    reciprocal_rank = 1.0 / first_relevant if first_relevant else 0.0
    actual_dcg = _dcg(gains)
    ideal_gains = sorted((item.relevance for item in evidence), reverse=True)[:top_k]
    ideal_dcg = _dcg(ideal_gains)
    ndcg = actual_dcg / ideal_dcg if ideal_dcg else 0.0
    precision = sum(gain > 0 for gain in gains) / top_k
    return CaseMetrics(
        recall_at_k=recall,
        reciprocal_rank=reciprocal_rank,
        ndcg_at_k=ndcg,
        context_precision_at_k=precision,
    )


def _deduplicated_gains(
    hits: Sequence[ScoredChunk], evidence: Sequence[GoldEvidence]
) -> list[int]:
    used: set[int] = set()
    gains: list[int] = []
    for hit in hits:
        candidates = [
            (gold.relevance, index)
            for index, gold in enumerate(evidence)
            if index not in used and _matches(hit.chunk, gold)
        ]
        if not candidates:
            gains.append(0)
            continue
        relevance, index = max(candidates)
        used.add(index)
        gains.append(relevance)
    return gains


def _matches(chunk: Chunk, evidence: GoldEvidence) -> bool:
    if chunk.document_ref != evidence.document_ref:
        return False
    if evidence.char_start is None:
        return True
    return chunk.char_start < evidence.char_end and chunk.char_end > evidence.char_start


def _dcg(gains: Sequence[int]) -> float:
    return sum(
        (2**gain - 1) / math.log2(rank + 1) for rank, gain in enumerate(gains, start=1)
    )
