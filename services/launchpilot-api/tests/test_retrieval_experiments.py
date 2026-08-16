from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from launchpilot.evaluation.experiments.chunking import chunk_documents
from launchpilot.evaluation.experiments.contracts import (
    Chunk,
    ChunkingConfig,
    ChunkingMethod,
    EvaluationCase,
    EvaluationDocument,
    ExperimentManifest,
    ExperimentStatus,
    GoldEvidence,
    RetrievalConfig,
    ScoredChunk,
)
from launchpilot.evaluation.experiments.local_adapters import (
    KoreanTfidfSparseEncoder,
    MarketingCrossFeatureReranker,
    MarketingDenseEncoder,
)
from launchpilot.evaluation.experiments.matrix import expand_matrix, load_matrix
from launchpilot.evaluation.experiments.metrics import retrieval_metrics
from launchpilot.evaluation.experiments.postgres import (
    PostgresExperimentResultRepository,
)
from launchpilot.evaluation.experiments.retrievers import (
    BM25Retriever,
    DenseEncoder,
    Reranker,
    RetrieverFactory,
    SparseEncoder,
)
from launchpilot.evaluation.experiments.runner import RetrievalExperimentRunner
from launchpilot.knowledge.contracts.search_profile import RetrievalMethod
from launchpilot.persistence.postgres import PostgresDatabase


def test_chunkers_preserve_document_offsets_and_cover_the_source() -> None:
    document = EvaluationDocument(
        document_ref="memo:fatigue",
        title="소재 피로 메모",
        text=(
            "# 관찰\n소재 A의 CTR이 3주 연속 하락했습니다. 빈도가 상승했습니다.\n\n"
            "# 조치\n신규 소재를 제작하고 기존 소재의 예산을 줄입니다."
        ),
    )
    for method in (
        ChunkingMethod.WHOLE_DOCUMENT,
        ChunkingMethod.FIXED_TOKEN,
        ChunkingMethod.SENTENCE,
        ChunkingMethod.RECURSIVE,
    ):
        chunks = chunk_documents(
            [document],
            ChunkingConfig(
                method=method,
                version=f"{method.value}-test",
                max_tokens=16 if method != ChunkingMethod.WHOLE_DOCUMENT else 8192,
                overlap_tokens=4 if method != ChunkingMethod.WHOLE_DOCUMENT else 0,
            ),
        )

        assert chunks
        assert len({chunk.chunk_id for chunk in chunks}) == len(chunks)
        assert all(
            document.text[chunk.char_start : chunk.char_end].strip() == chunk.text
            for chunk in chunks
        )
        assert min(chunk.char_start for chunk in chunks) == 0
        assert max(chunk.char_end for chunk in chunks) == len(document.text)


def test_bm25_and_dense_backends_are_interchangeable() -> None:
    chunks = _chunks()
    bm25 = BM25Retriever()
    bm25.index(chunks)
    dense = RetrieverFactory(dense_encoder=_KeywordDenseEncoder()).build(
        RetrievalConfig(
            method=RetrievalMethod.DENSE,
            version="dense-test",
            provider="fake",
            top_k=2,
        )
    )
    dense.index(chunks)

    assert bm25.search("소재 피로 CTR 하락", top_k=2)[0].chunk.document_ref == (
        "memo:fatigue"
    )
    assert dense.search("소재 성과가 떨어짐", top_k=2)[0].chunk.document_ref == (
        "memo:fatigue"
    )


def test_local_dense_sparse_hybrid_and_reranker_backends_complete() -> None:
    chunks = _chunks()
    factory = RetrieverFactory(
        dense_encoder=_KeywordDenseEncoder(),
        sparse_encoder=_KeywordSparseEncoder(),
        reranker=_KeywordReranker(),
    )
    configs = (
        RetrievalConfig(
            method=RetrievalMethod.DENSE,
            version="dense-test",
            provider="fake",
            top_k=2,
        ),
        RetrievalConfig(
            method=RetrievalMethod.SPARSE,
            version="sparse-test",
            provider="fake",
            top_k=2,
        ),
        RetrievalConfig(
            method=RetrievalMethod.HYBRID,
            version="hybrid-test",
            provider="dense",
            fusion="rrf",
            reranker="fake-reranker",
            top_k=2,
        ),
    )
    for config in configs:
        retriever = factory.build(config)
        retriever.index(chunks)
        assert retriever.search("소재 피로 CTR 하락", top_k=2)[
            0
        ].chunk.document_ref == ("memo:fatigue")


def test_local_marketing_adapters_normalize_korean_metric_synonyms() -> None:
    dense = MarketingDenseEncoder()
    sparse = KoreanTfidfSparseEncoder()
    reranker = MarketingCrossFeatureReranker()

    ctr = dense.encode_query("CTR이 하락한 원인")
    click_rate = dense.encode_query("클릭률 감소 이유")
    budget = dense.encode_query("예산 증액")
    assert _dot(ctr, click_rate) > _dot(ctr, budget)
    assert "concept:metric:ctr" in sparse.encode_query("클릭률을 보여줘")
    assert (
        reranker.score(
            "CTR 하락 원인",
            ["클릭률 감소 원인은 소재 피로입니다.", "예산을 증액합니다."],
        )[0]
        > reranker.score(
            "CTR 하락 원인",
            ["클릭률 감소 원인은 소재 피로입니다.", "예산을 증액합니다."],
        )[1]
    )


def test_semantic_chunker_uses_dense_adapter_and_preserves_offsets() -> None:
    document = EvaluationDocument(
        document_ref="analysis:semantic",
        text=(
            "CTR이 하락했고 소재 피로가 관찰됩니다. 클릭률 개선이 필요합니다. "
            "예산은 계획대로 소진 중입니다. 지출 변동은 안정적입니다. "
            "신규 소재를 투입하고 기존 소재 비중을 줄입니다."
        ),
    )
    chunks = chunk_documents(
        [document],
        ChunkingConfig(
            method=ChunkingMethod.SEMANTIC,
            version="semantic-test",
            max_tokens=16,
            overlap_tokens=4,
        ),
        semantic_encoder=MarketingDenseEncoder(),
    )

    assert chunks
    assert all(
        document.text[chunk.char_start : chunk.char_end].strip() == chunk.text
        for chunk in chunks
    )


def test_metrics_use_span_overlap_and_do_not_reward_duplicate_chunks() -> None:
    evidence = (
        GoldEvidence(
            document_ref="memo:fatigue", relevance=3, char_start=10, char_end=30
        ),
        GoldEvidence(
            document_ref="brief:budget", relevance=2, char_start=0, char_end=20
        ),
    )
    hits = (
        _hit(_chunks()[0], rank=1),
        _hit(_chunks()[0].model_copy(update={"chunk_id": "fatigue-duplicate"}), rank=2),
    )

    metrics = retrieval_metrics(hits, evidence, top_k=2)

    assert metrics.recall_at_k == 0.5
    assert metrics.reciprocal_rank == 1.0
    assert metrics.context_precision_at_k == 0.5
    assert 0.0 < metrics.ndcg_at_k < 1.0


def test_runner_blocks_missing_corpus_and_completes_available_bm25() -> None:
    manifest = _manifest()
    case = EvaluationCase(
        case_id="semantic.fatigue",
        query="CTR 하락 소재 피로",
        query_profile="semantic",
        split="tune",
        campaign_ref="C0001",
        evidence=(GoldEvidence(document_ref="memo:fatigue"),),
        taxonomy={"analysis_task": "causal_diagnosis"},
    )
    runner = RetrievalExperimentRunner()

    blocked = runner.run(manifest, [], [case])
    completed = runner.run(
        manifest,
        [
            EvaluationDocument(
                document_ref="memo:fatigue",
                text="소재 피로 때문에 CTR이 하락했다.",
                campaign_ref="C0001",
            ),
            EvaluationDocument(
                document_ref="brief:budget",
                text="소재 피로 때문에 CTR이 하락했다. 인지도 예산도 증액한다.",
                campaign_ref="C0002",
            ),
        ],
        [case],
    )

    assert blocked.status == ExperimentStatus.BLOCKED
    assert blocked.block_reason == "document corpus is empty"
    assert completed.status == ExperimentStatus.COMPLETED
    assert completed.aggregate_metrics["recall_at_k"] == 1.0
    assert completed.aggregate_metrics["mrr_at_k"] == 1.0
    assert any(
        item.dimension == "analysis_task" and item.value == "causal_diagnosis"
        for item in completed.slice_metrics
    )


def test_matrix_is_explicit_and_persistable(
    postgres_database: PostgresDatabase,
) -> None:
    matrix_path = (
        Path(__file__).parents[1] / "evals" / "experiments" / "retrieval-matrix-v1.yaml"
    )
    matrix = load_matrix(matrix_path)
    manifests = expand_matrix(
        matrix, golden_version="golden-v1", corpus_version="corpus-v1"
    )
    execution_id = manifests[0].execution_id
    result = RetrievalExperimentRunner().run(
        manifests[0],
        [
            EvaluationDocument(
                document_ref="memo:fatigue",
                text="소재 피로 때문에 CTR이 하락했다.",
                campaign_ref="C0001",
            )
        ],
        [
            EvaluationCase(
                case_id="semantic.fatigue",
                query="소재 피로 CTR 하락",
                query_profile="semantic",
                split="tune",
                campaign_ref="C0001",
                evidence=(GoldEvidence(document_ref="memo:fatigue"),),
                taxonomy={"analysis_task": "causal_diagnosis"},
            )
        ],
    )
    repository = PostgresExperimentResultRepository(postgres_database)

    repository.save(result)
    rows = repository.matrix_summary("retrieval-matrix-v1")

    assert len(manifests) == 70
    assert {manifest.execution_id for manifest in manifests} == {execution_id}
    assert len(rows) == 1
    assert rows[0]["execution_id"] == execution_id
    assert rows[0]["status"] == "completed"
    assert rows[0]["block_reason"] is None
    assert (
        repository.best_runs(
            matrix_version="retrieval-matrix-v1", metric_name="ndcg_at_k"
        )[0]["metric_value"]
        == 1.0
    )


class _KeywordDenseEncoder(DenseEncoder):
    @property
    def version(self) -> str:
        return "keyword-dense-test"

    def encode_documents(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        return [self._encode(text) for text in texts]

    def encode_query(self, text: str) -> Sequence[float]:
        return self._encode(text)

    @staticmethod
    def _encode(text: str) -> list[float]:
        return [
            float(any(term in text for term in ("소재", "피로", "CTR", "떨어"))),
            float(any(term in text for term in ("예산", "인지도"))),
        ]


class _KeywordSparseEncoder(SparseEncoder):
    @property
    def version(self) -> str:
        return "keyword-sparse-test"

    @property
    def requires_idf(self) -> bool:
        return True

    def encode_documents(self, texts: Sequence[str]) -> Sequence[dict[str, float]]:
        return [self._encode(text) for text in texts]

    def encode_query(self, text: str) -> dict[str, float]:
        return self._encode(text)

    @staticmethod
    def _encode(text: str) -> dict[str, float]:
        return {
            term: 1.0
            for term in ("소재", "피로", "CTR", "하락", "예산", "인지도")
            if term in text
        }


class _KeywordReranker(Reranker):
    @property
    def version(self) -> str:
        return "keyword-reranker-test"

    def score(self, query: str, texts: Sequence[str]) -> Sequence[float]:
        return [float(sum(term in text for term in query.split())) for text in texts]


def _chunks() -> tuple[Chunk, ...]:
    return (
        Chunk(
            chunk_id="fatigue",
            document_ref="memo:fatigue",
            text="소재 피로로 CTR이 하락했다.",
            char_start=0,
            char_end=30,
        ),
        Chunk(
            chunk_id="budget",
            document_ref="brief:budget",
            text="브랜드 인지도를 위해 예산을 확대한다.",
            char_start=0,
            char_end=30,
        ),
    )


def _hit(chunk: Chunk, *, rank: int) -> ScoredChunk:
    return ScoredChunk(chunk=chunk, score=1.0 / rank, rank=rank)


def _manifest() -> ExperimentManifest:
    return ExperimentManifest(
        matrix_version="test-matrix-v1",
        golden_version="golden-v1",
        corpus_version="corpus-v1",
        split="tune",
        chunker=ChunkingConfig(
            method=ChunkingMethod.WHOLE_DOCUMENT,
            version="whole-document-test",
            max_tokens=8192,
        ),
        retriever=RetrievalConfig(
            method=RetrievalMethod.BM25,
            version="bm25-test",
            top_k=2,
        ),
    )


def _dot(left: Sequence[float], right: Sequence[float]) -> float:
    return sum(a * b for a, b in zip(left, right, strict=True))
