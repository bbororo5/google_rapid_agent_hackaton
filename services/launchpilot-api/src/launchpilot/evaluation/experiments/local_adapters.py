from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence

_TERM_PATTERN = re.compile(r"[0-9a-zA-Z가-힣]+")
_NUMBER_PATTERN = re.compile(r"\d+(?:\.\d+)?%?")
_CONCEPT_SYNONYMS = {
    "metric:ctr": ("ctr", "클릭률", "클릭 율"),
    "metric:cvr": ("cvr", "전환율", "전환 율"),
    "metric:roas": ("roas", "광고수익률", "광고 수익률"),
    "metric:cpc": ("cpc", "클릭당비용", "클릭당 비용"),
    "metric:cpa": ("cpa", "전환당비용", "획득비용", "전환당 비용"),
    "metric:spend": ("spend", "광고비", "지출", "비용", "예산 소진"),
    "metric:clicks": ("clicks", "클릭 수", "클릭수"),
    "metric:impressions": ("impressions", "노출 수", "노출수"),
    "metric:conversions": ("conversions", "전환 수", "전환수"),
    "trend:decline": ("하락", "감소", "떨어", "악화", "저하"),
    "trend:growth": ("상승", "증가", "개선", "성장", "회복"),
    "diagnosis:fatigue": ("피로", "소재 소진", "creative fatigue"),
    "diagnosis:tracking": ("추적 누락", "트래킹", "tracking", "계측"),
    "action:increase": ("증액", "확대", "늘려", "상향"),
    "action:decrease": ("감액", "축소", "줄여", "하향"),
    "action:recommendation": ("권고", "추천", "조치", "무엇을 해야"),
    "time:week": ("지난주", "주간", "주별", "4주", "일주일"),
    "time:month": ("지난달", "월간", "월별", "한 달"),
    "platform:google": ("google ads", "google", "구글"),
    "platform:meta": ("meta ads", "meta", "메타"),
    "platform:youtube": ("youtube", "유튜브"),
}


class MarketingDenseEncoder:
    """Domain-semantic feature hashing into a fixed dense vector."""

    def __init__(self, *, dimensions: int = 512) -> None:
        if dimensions < 64:
            raise ValueError("dense feature dimensions must be at least 64")
        self._dimensions = dimensions
        self._cache: dict[str, tuple[float, ...]] = {}

    @property
    def version(self) -> str:
        return f"marketing-concept-hash-dense-{self._dimensions}-v1"

    def encode_documents(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        return tuple(self._encode(text) for text in texts)

    def encode_query(self, text: str) -> Sequence[float]:
        return self._encode(text)

    def _encode(self, text: str) -> tuple[float, ...]:
        cached = self._cache.get(text)
        if cached is not None:
            return cached
        vector = [0.0] * self._dimensions
        for feature, weight in _weighted_features(text).items():
            digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
            index = int.from_bytes(digest, "big") % self._dimensions
            sign = 1.0 if digest[0] & 1 else -1.0
            vector[index] += sign * weight
        norm = math.sqrt(sum(value * value for value in vector))
        if norm:
            vector = [value / norm for value in vector]
        encoded = tuple(vector)
        self._cache[text] = encoded
        return encoded


class KoreanTfidfSparseEncoder:
    """Korean word/subword sparse features; corpus IDF is applied by the retriever."""

    requires_idf = True

    @property
    def version(self) -> str:
        return "ko-word-bigram-tfidf-v1"

    def encode_documents(self, texts: Sequence[str]) -> Sequence[Mapping[str, float]]:
        return tuple(_weighted_features(text) for text in texts)

    def encode_query(self, text: str) -> Mapping[str, float]:
        return _weighted_features(text)


class MarketingCrossFeatureReranker:
    """Joint query-passage feature scorer for a dependency-free rerank baseline."""

    @property
    def version(self) -> str:
        return "ko-marketing-cross-feature-reranker-v1"

    def score(self, query: str, texts: Sequence[str]) -> Sequence[float]:
        query_terms = set(_terms(query))
        query_bigrams = set(_korean_ngrams(query, size=2))
        query_concepts = set(_concepts(query))
        query_numbers = set(_NUMBER_PATTERN.findall(query.lower()))
        return tuple(
            _pair_score(
                query_terms=query_terms,
                query_bigrams=query_bigrams,
                query_concepts=query_concepts,
                query_numbers=query_numbers,
                text=text,
            )
            for text in texts
        )


def _pair_score(
    *,
    query_terms: set[str],
    query_bigrams: set[str],
    query_concepts: set[str],
    query_numbers: set[str],
    text: str,
) -> float:
    document_terms = set(_terms(text))
    document_bigrams = set(_korean_ngrams(text, size=2))
    document_concepts = set(_concepts(text))
    document_numbers = set(_NUMBER_PATTERN.findall(text.lower()))
    term_coverage = _coverage(query_terms, document_terms)
    concept_coverage = _coverage(query_concepts, document_concepts)
    number_coverage = _coverage(query_numbers, document_numbers)
    bigram_jaccard = _jaccard(query_bigrams, document_bigrams)
    return (
        0.45 * term_coverage
        + 0.3 * concept_coverage
        + 0.15 * bigram_jaccard
        + 0.1 * number_coverage
    )


def _weighted_features(text: str) -> dict[str, float]:
    frequencies = Counter(_terms(text))
    features = {
        f"term:{term}": 1.0 + math.log(float(frequency))
        for term, frequency in frequencies.items()
    }
    for ngram, frequency in Counter(_korean_ngrams(text, size=2)).items():
        features[f"ko2:{ngram}"] = 0.55 * (1.0 + math.log(float(frequency)))
    for ngram, frequency in Counter(_korean_ngrams(text, size=3)).items():
        features[f"ko3:{ngram}"] = 0.35 * (1.0 + math.log(float(frequency)))
    for concept in _concepts(text):
        features[f"concept:{concept}"] = 3.0
    return features


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
