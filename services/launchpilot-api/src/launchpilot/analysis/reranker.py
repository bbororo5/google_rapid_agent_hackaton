from __future__ import annotations

import re
from collections import Counter
from datetime import datetime
from typing import Iterable, Sequence
from uuid import UUID

from launchpilot.knowledge.contracts.retrieval import TextSearchHit


_TERM_PATTERN = re.compile(r"[A-Za-z0-9_]+|[가-힣]+")
_NUMBER_PATTERN = re.compile(r"\d+(?:\.\d+)?")
_CAMPAIGN_CODE_PATTERN = re.compile(r"\bC\d{4}\b", re.IGNORECASE)

_CONCEPT_SYNONYMS: dict[str, tuple[str, ...]] = {
    "fatigue": ("소재 피로", "소재피로", "피로도", "크리에이티브 피로", "소재 털림", "털린", "털렸"),
    "ctr": ("ctr", "클릭률", "클릭율", "클릭 수", "클릭수"),
    "cvr": ("cvr", "전환율", "전환율", "전환 수", "전환수"),
    "roas": ("roas", "광고수익률", "투자수익률", "효율"),
    "spend": ("spend", "광고비", "소진액", "지출액", "비용"),
    "pacing": ("페이싱", "소진율", "예산 소진", "일 예산", "일예산"),
    "diagnosis": ("원인", "진단", "이유", "배경", "분석", "후보"),
    "recommendation": ("조치", "제안", "권고", "액션플랜", "개선안"),
}


class MarketingDomainReranker:
    """Feature-based ultra-low-latency domain reranker (Strategy A).

    Combines cross-attention lexical matching, marketing concept coverage,
    document type intention matching, and entity alignment.
    """

    def rerank(
        self,
        query: str,
        hits: Sequence[TextSearchHit],
        reference_now: datetime | None = None,
    ) -> tuple[TextSearchHit, ...]:
        if not hits:
            return ()

        query_terms = set(_terms(query))
        query_bigrams = set(_korean_ngrams(query, size=2))
        query_concepts = set(_concepts(query))
        query_numbers = set(_NUMBER_PATTERN.findall(query.lower()))
        query_codes = set(_CAMPAIGN_CODE_PATTERN.findall(query.upper()))

        scored_hits: list[tuple[float, TextSearchHit]] = []

        for hit in hits:
            text = getattr(hit, "excerpt", getattr(hit, "snippet", ""))
            doc_terms = set(_terms(text))
            doc_bigrams = set(_korean_ngrams(text, size=2))
            doc_concepts = set(_concepts(text))
            doc_numbers = set(_NUMBER_PATTERN.findall(text.lower()))
            doc_codes = set(_CAMPAIGN_CODE_PATTERN.findall(text.upper()))

            term_cov = _coverage(query_terms, doc_terms)
            concept_cov = _coverage(query_concepts, doc_concepts)
            bigram_jaccard = _jaccard(query_bigrams, doc_bigrams)
            number_cov = _coverage(query_numbers, doc_numbers)

            # 1. Lexical & Conceptual Match Score (0.0 ~ 1.0)
            text_score = (
                0.40 * term_cov
                + 0.30 * concept_cov
                + 0.15 * bigram_jaccard
                + 0.15 * number_cov
            )

            # 2. Document Type Alignment Boost
            doc_type = hit.document_type.value if hasattr(hit.document_type, "value") else str(hit.document_type)
            type_boost = 0.0
            q_lower = query.lower()
            if any(k in q_lower for k in ("브리프", "기획서", "페이싱", "목표")) and "brief" in doc_type:
                type_boost = 0.15
            elif any(k in q_lower for k in ("메모", "운영", "피로", "원인")) and "memo" in doc_type:
                type_boost = 0.15
            elif any(k in q_lower for k in ("분석", "결산", "조치", "제안", "권고")) and "analysis" in doc_type:
                type_boost = 0.15

            # 3. Exact Campaign Code Alignment Boost
            code_boost = 0.20 if (query_codes and (query_codes & doc_codes)) else 0.0

            # 4. Original Rank Signal (Reciprocal rank prior)
            rank_prior = hit.score if hit.score > 0 else (1.0 / (1.0 + hit.rank))

            final_score = (0.50 * text_score) + type_boost + code_boost + (0.20 * rank_prior)

            # Create updated hit with reranked score
            updated_hit = hit.model_copy(update={"score": float(final_score)})
            scored_hits.append((final_score, updated_hit))

        # Sort descending by final score
        scored_hits.sort(key=lambda x: x[0], reverse=True)

        # Re-assign ranks 1..N
        reranked = tuple(
            hit.model_copy(update={"rank": idx + 1})
            for idx, (_, hit) in enumerate(scored_hits)
        )
        return reranked


def _terms(text: str) -> Iterable[str]:
    yield from (term.lower() for term in _TERM_PATTERN.findall(text))


def _korean_ngrams(text: str, *, size: int) -> Iterable[str]:
    for term in _terms(text):
        if re.search(r"[가-힣]", term) and len(term) >= size:
            yield from (
                term[index : index + size] for index in range(len(term) - size + 1)
            )


def _concepts(text: str) -> Iterable[str]:
    normalized = " ".join(_terms(text))
    for concept, synonyms in _CONCEPT_SYNONYMS.items():
        if any(synonym in normalized for synonym in synonyms):
            yield concept


def _coverage(expected: set[str], actual: set[str]) -> float:
    if not expected:
        return 0.0
    return len(expected & actual) / len(expected)


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)
