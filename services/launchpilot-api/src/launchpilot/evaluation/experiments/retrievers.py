from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Protocol

from launchpilot.knowledge.contracts.search_profile import RetrievalMethod

from .contracts import Chunk, FusionMethod, RetrievalConfig, ScoredChunk

_TERM_PATTERN = re.compile(r"[0-9a-zA-Z가-힣]+")


class ExperimentDependencyUnavailable(RuntimeError):
    pass


class DenseEncoder(Protocol):
    @property
    def version(self) -> str: ...

    def encode_documents(self, texts: Sequence[str]) -> Sequence[Sequence[float]]: ...

    def encode_query(self, text: str) -> Sequence[float]: ...


class SparseEncoder(Protocol):
    @property
    def version(self) -> str: ...

    def encode_documents(
        self, texts: Sequence[str]
    ) -> Sequence[Mapping[str, float]]: ...

    def encode_query(self, text: str) -> Mapping[str, float]: ...

    @property
    def requires_idf(self) -> bool: ...


class Reranker(Protocol):
    @property
    def version(self) -> str: ...

    def score(self, query: str, texts: Sequence[str]) -> Sequence[float]: ...


class ExperimentRetriever(Protocol):
    @property
    def method(self) -> RetrievalMethod: ...

    def index(self, chunks: Sequence[Chunk]) -> None: ...

    def search(
        self,
        query: str,
        *,
        top_k: int,
        filters: Mapping[str, object] | None = None,
    ) -> tuple[ScoredChunk, ...]: ...


class BM25Retriever:
    def __init__(self, *, k1: float = 1.2, b: float = 0.75) -> None:
        self._k1 = k1
        self._b = b
        self._chunks: tuple[Chunk, ...] = ()
        self._term_frequencies: tuple[Counter[str], ...] = ()
        self._document_frequencies: Counter[str] = Counter()
        self._lengths: tuple[int, ...] = ()
        self._average_length = 0.0

    @property
    def method(self) -> RetrievalMethod:
        return RetrievalMethod.BM25

    def index(self, chunks: Sequence[Chunk]) -> None:
        self._chunks = tuple(chunks)
        frequencies = [Counter(_analyze(chunk.text)) for chunk in self._chunks]
        self._term_frequencies = tuple(frequencies)
        self._document_frequencies = Counter(
            term for frequency in frequencies for term in frequency
        )
        self._lengths = tuple(sum(frequency.values()) for frequency in frequencies)
        self._average_length = (
            sum(self._lengths) / len(self._lengths) if self._lengths else 0.0
        )

    def search(
        self,
        query: str,
        *,
        top_k: int,
        filters: Mapping[str, object] | None = None,
    ) -> tuple[ScoredChunk, ...]:
        if not self._chunks:
            return ()
        query_terms = Counter(_analyze(query))
        scored = []
        total = len(self._chunks)
        for index, frequency in enumerate(self._term_frequencies):
            if not _matches_filters(self._chunks[index], filters):
                continue
            score = 0.0
            length = self._lengths[index]
            for term, query_frequency in query_terms.items():
                term_frequency = frequency.get(term, 0)
                if not term_frequency:
                    continue
                document_frequency = self._document_frequencies[term]
                inverse_document_frequency = math.log(
                    1.0
                    + (total - document_frequency + 0.5) / (document_frequency + 0.5)
                )
                denominator = term_frequency + self._k1 * (
                    1.0 - self._b + self._b * length / max(self._average_length, 1.0)
                )
                score += (
                    inverse_document_frequency
                    * term_frequency
                    * (self._k1 + 1.0)
                    / denominator
                    * query_frequency
                )
            if score > 0:
                scored.append((score, self._chunks[index]))
        return _rank(scored, top_k=top_k, component="bm25")


class DenseRetriever:
    def __init__(self, encoder: DenseEncoder) -> None:
        self._encoder = encoder
        self._chunks: tuple[Chunk, ...] = ()
        self._vectors: tuple[tuple[float, ...], ...] = ()

    @property
    def method(self) -> RetrievalMethod:
        return RetrievalMethod.DENSE

    def index(self, chunks: Sequence[Chunk]) -> None:
        self._chunks = tuple(chunks)
        vectors = self._encoder.encode_documents([chunk.text for chunk in chunks])
        if len(vectors) != len(chunks):
            raise ValueError("dense encoder returned the wrong number of vectors")
        self._vectors = tuple(
            tuple(float(value) for value in vector) for vector in vectors
        )

    def search(
        self,
        query: str,
        *,
        top_k: int,
        filters: Mapping[str, object] | None = None,
    ) -> tuple[ScoredChunk, ...]:
        query_vector = tuple(
            float(value) for value in self._encoder.encode_query(query)
        )
        scored = [
            (_cosine(query_vector, vector), chunk)
            for chunk, vector in zip(self._chunks, self._vectors, strict=True)
            if _matches_filters(chunk, filters)
        ]
        return _rank(scored, top_k=top_k, component="dense")


class SparseRetriever:
    def __init__(self, encoder: SparseEncoder) -> None:
        self._encoder = encoder
        self._chunks: tuple[Chunk, ...] = ()
        self._vectors: tuple[dict[str, float], ...] = ()
        self._inverse_document_frequencies: dict[str, float] = {}

    @property
    def method(self) -> RetrievalMethod:
        return RetrievalMethod.SPARSE

    def index(self, chunks: Sequence[Chunk]) -> None:
        self._chunks = tuple(chunks)
        vectors = self._encoder.encode_documents([chunk.text for chunk in chunks])
        if len(vectors) != len(chunks):
            raise ValueError("sparse encoder returned the wrong number of vectors")
        self._vectors = tuple(dict(vector) for vector in vectors)
        if self._encoder.requires_idf:
            document_frequencies = Counter(
                term for vector in self._vectors for term in vector
            )
            total = max(len(self._vectors), 1)
            self._inverse_document_frequencies = {
                term: math.log(1.0 + (total - count + 0.5) / (count + 0.5))
                for term, count in document_frequencies.items()
            }

    def search(
        self,
        query: str,
        *,
        top_k: int,
        filters: Mapping[str, object] | None = None,
    ) -> tuple[ScoredChunk, ...]:
        raw_query_vector = self._encoder.encode_query(query)
        query_vector = {
            term: value * self._inverse_document_frequencies.get(term, 0.0)
            for term, value in raw_query_vector.items()
        }
        scored = [
            (_sparse_dot(query_vector, vector), chunk)
            for chunk, vector in zip(self._chunks, self._vectors, strict=True)
            if _matches_filters(chunk, filters)
        ]
        return _rank(scored, top_k=top_k, component="sparse")


class HybridRetriever:
    def __init__(
        self,
        lexical: ExperimentRetriever,
        semantic: ExperimentRetriever,
        *,
        fusion: FusionMethod,
        alpha: float | None,
        rrf_k: int,
    ) -> None:
        self._lexical = lexical
        self._semantic = semantic
        self._fusion = fusion
        self._alpha = alpha
        self._rrf_k = rrf_k

    @property
    def method(self) -> RetrievalMethod:
        return RetrievalMethod.HYBRID

    def index(self, chunks: Sequence[Chunk]) -> None:
        self._lexical.index(chunks)
        self._semantic.index(chunks)

    def search(
        self,
        query: str,
        *,
        top_k: int,
        filters: Mapping[str, object] | None = None,
    ) -> tuple[ScoredChunk, ...]:
        candidate_k = max(top_k * 4, 20)
        lexical = self._lexical.search(query, top_k=candidate_k, filters=filters)
        semantic = self._semantic.search(query, top_k=candidate_k, filters=filters)
        chunks = {hit.chunk.chunk_id: hit.chunk for hit in (*lexical, *semantic)}
        lexical_by_id = {hit.chunk.chunk_id: hit for hit in lexical}
        semantic_by_id = {hit.chunk.chunk_id: hit for hit in semantic}
        if self._fusion == FusionMethod.RRF:
            scores = {
                chunk_id: (
                    (1.0 / (self._rrf_k + lexical_by_id[chunk_id].rank))
                    if chunk_id in lexical_by_id
                    else 0.0
                )
                + (
                    (1.0 / (self._rrf_k + semantic_by_id[chunk_id].rank))
                    if chunk_id in semantic_by_id
                    else 0.0
                )
                for chunk_id in chunks
            }
        else:
            alpha = self._alpha if self._alpha is not None else 0.5
            lexical_scores = _min_max(lexical)
            semantic_scores = _min_max(semantic)
            scores = {
                chunk_id: (1.0 - alpha) * lexical_scores.get(chunk_id, 0.0)
                + alpha * semantic_scores.get(chunk_id, 0.0)
                for chunk_id in chunks
            }
        ranked = sorted(scores, key=lambda item: (-scores[item], item))[:top_k]
        return tuple(
            ScoredChunk(
                chunk=chunks[chunk_id],
                score=scores[chunk_id],
                rank=rank,
                component_scores={
                    "bm25": lexical_by_id.get(chunk_id).score
                    if chunk_id in lexical_by_id
                    else 0.0,
                    self._semantic.method.value: semantic_by_id.get(chunk_id).score
                    if chunk_id in semantic_by_id
                    else 0.0,
                },
            )
            for rank, chunk_id in enumerate(ranked, start=1)
        )


class RerankingRetriever:
    def __init__(self, base: ExperimentRetriever, reranker: Reranker) -> None:
        self._base = base
        self._reranker = reranker

    @property
    def method(self) -> RetrievalMethod:
        return self._base.method

    def index(self, chunks: Sequence[Chunk]) -> None:
        self._base.index(chunks)

    def search(
        self,
        query: str,
        *,
        top_k: int,
        filters: Mapping[str, object] | None = None,
    ) -> tuple[ScoredChunk, ...]:
        candidates = self._base.search(
            query,
            top_k=max(top_k * 4, 20),
            filters=filters,
        )
        if not candidates:
            return ()
        scores = self._reranker.score(
            query, [candidate.chunk.text for candidate in candidates]
        )
        minimum = min(scores)
        maximum = max(scores)
        if maximum == minimum:
            normalized_reranker = [0.0 for _ in scores]
        else:
            normalized_reranker = [
                (float(score) - minimum) / (maximum - minimum) for score in scores
            ]
        normalized_base = _min_max(candidates)
        combined = [
            0.75 * reranker_score
            + 0.25 * normalized_base.get(candidate.chunk.chunk_id, 0.0)
            for candidate, reranker_score in zip(
                candidates, normalized_reranker, strict=True
            )
        ]
        reranked = sorted(
            zip(candidates, scores, combined, strict=True),
            key=lambda item: (-float(item[2]), item[0].chunk.chunk_id),
        )[:top_k]
        return tuple(
            ScoredChunk(
                chunk=candidate.chunk,
                score=float(combined_score),
                rank=rank,
                component_scores={
                    **candidate.component_scores,
                    "reranker": float(score),
                },
            )
            for rank, (candidate, score, combined_score) in enumerate(reranked, start=1)
        )


class RetrieverFactory:
    def __init__(
        self,
        *,
        dense_encoder: DenseEncoder | None = None,
        sparse_encoder: SparseEncoder | None = None,
        reranker: Reranker | None = None,
    ) -> None:
        self._dense_encoder = dense_encoder
        self._sparse_encoder = sparse_encoder
        self._reranker = reranker

    @property
    def dense_encoder(self) -> DenseEncoder | None:
        return self._dense_encoder

    def build(self, config: RetrievalConfig) -> ExperimentRetriever:
        if config.method == RetrievalMethod.BM25:
            retriever: ExperimentRetriever = BM25Retriever()
        elif config.method == RetrievalMethod.DENSE:
            retriever = DenseRetriever(self._require_dense(config))
        elif config.method == RetrievalMethod.SPARSE:
            retriever = SparseRetriever(self._require_sparse(config))
        elif config.method == RetrievalMethod.HYBRID:
            semantic: ExperimentRetriever
            if config.provider == "sparse":
                semantic = SparseRetriever(self._require_sparse(config))
            else:
                semantic = DenseRetriever(self._require_dense(config))
            retriever = HybridRetriever(
                BM25Retriever(),
                semantic,
                fusion=config.fusion or FusionMethod.RRF,
                alpha=config.alpha,
                rrf_k=config.rrf_k,
            )
        else:
            raise ValueError(f"unsupported retrieval method: {config.method}")
        if config.reranker:
            if self._reranker is None:
                raise ExperimentDependencyUnavailable(
                    f"reranker adapter is not configured: {config.reranker}"
                )
            retriever = RerankingRetriever(retriever, self._reranker)
        return retriever

    def _require_dense(self, config: RetrievalConfig) -> DenseEncoder:
        if self._dense_encoder is None:
            raise ExperimentDependencyUnavailable(
                f"dense encoder adapter is not configured: {config.provider or 'unspecified'}"
            )
        return self._dense_encoder

    def _require_sparse(self, config: RetrievalConfig) -> SparseEncoder:
        if self._sparse_encoder is None:
            raise ExperimentDependencyUnavailable(
                f"sparse encoder adapter is not configured: {config.provider or 'unspecified'}"
            )
        return self._sparse_encoder


def _analyze(text: str) -> list[str]:
    terms = [term.lower() for term in _TERM_PATTERN.findall(text)]
    expanded = list(terms)
    for term in terms:
        if re.search(r"[가-힣]", term) and len(term) >= 2:
            expanded.extend(
                f"ko:{term[index : index + 2]}" for index in range(len(term) - 1)
            )
    return expanded


def _cosine(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right):
        raise ValueError("dense vectors must have the same dimensions")
    numerator = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return numerator / (left_norm * right_norm)


def _sparse_dot(left: Mapping[str, float], right: Mapping[str, float]) -> float:
    if len(left) > len(right):
        left, right = right, left
    return sum(value * right.get(term, 0.0) for term, value in left.items())


def _rank(
    scored: Sequence[tuple[float, Chunk]], *, top_k: int, component: str
) -> tuple[ScoredChunk, ...]:
    ranked = sorted(
        (item for item in scored if item[0] > 0.0),
        key=lambda item: (-item[0], item[1].chunk_id),
    )[:top_k]
    return tuple(
        ScoredChunk(
            chunk=chunk,
            score=score,
            rank=rank,
            component_scores={component: score},
        )
        for rank, (score, chunk) in enumerate(ranked, start=1)
    )


def _min_max(hits: Sequence[ScoredChunk]) -> dict[str, float]:
    if not hits:
        return {}
    minimum = min(hit.score for hit in hits)
    maximum = max(hit.score for hit in hits)
    if maximum == minimum:
        return {hit.chunk.chunk_id: 1.0 for hit in hits}
    return {
        hit.chunk.chunk_id: (hit.score - minimum) / (maximum - minimum) for hit in hits
    }


def _matches_filters(chunk: Chunk, filters: Mapping[str, object] | None) -> bool:
    if not filters:
        return True
    return all(chunk.metadata.get(key) == value for key, value in filters.items())
