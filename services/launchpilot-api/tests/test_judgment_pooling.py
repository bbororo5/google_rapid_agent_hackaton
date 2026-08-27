from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from launchpilot.evaluation.contracts.architecture_eval import EvidenceJudgment
from launchpilot.evaluation.portfolio.pooling import (
    ExistingQrel,
    HumanAdjudication,
    JudgmentConflictError,
    JudgmentPool,
    PoolCandidate,
    RetrievedHit,
    build_judgment_pool,
    detect_adjudication_conflicts,
    merge_adjudications,
)


def _hits() -> tuple[RetrievedHit, ...]:
    common = {"corpus_version": "corpus-v4", "query_id": "query-1", "top_k": 2}
    return (
        RetrievedHit(
            **common,
            run_id="run-v0",
            system_version="sql-bm25-v0",
            index_version="bm25-v2",
            corpus_ref="document-1",
            rank=1,
            score=8.2,
        ),
        RetrievedHit(
            **common,
            run_id="run-v0",
            system_version="sql-bm25-v0",
            index_version="bm25-v2",
            corpus_ref="document-2",
            rank=2,
            score=4.1,
        ),
        RetrievedHit(
            **common,
            run_id="run-v1",
            system_version="sql-bm25-dense-v1",
            index_version="hybrid-v3",
            corpus_ref="document-2",
            rank=1,
            score=0.91,
        ),
        RetrievedHit(
            **common,
            run_id="run-v1",
            system_version="sql-bm25-dense-v1",
            index_version="hybrid-v3",
            corpus_ref="document-3",
            rank=2,
            score=0.74,
        ),
    )


def _qrels() -> tuple[ExistingQrel, ...]:
    common = {
        "query_id": "query-1",
        "corpus_version": "corpus-v4",
        "qrel_version": "qrels-v2",
        "provenance": "expert-seed",
    }
    return (
        ExistingQrel(
            **common,
            corpus_ref="document-1",
            judgment=EvidenceJudgment.KNOWN_RELEVANT,
            relevance_grade=3,
        ),
        ExistingQrel(
            **common,
            corpus_ref="document-2",
            judgment=EvidenceJudgment.KNOWN_IRRELEVANT,
        ),
    )


def _pool() -> JudgmentPool:
    return build_judgment_pool(_hits(), _qrels(), pool_version="pool-v1")


def _candidate(pool: JudgmentPool, ref: str) -> PoolCandidate:
    return next(item for item in pool.candidates if item.corpus_ref == ref)


def test_pool_deduplicates_and_preserves_contributing_system_rank_and_score() -> None:
    pool = _pool()
    assert [item.corpus_ref for item in pool.candidates] == [
        "document-1",
        "document-2",
        "document-3",
    ]
    shared = _candidate(pool, "document-2")
    assert [item.system_version for item in shared.contributions] == [
        "sql-bm25-dense-v1",
        "sql-bm25-v0",
    ]
    assert [(item.rank, item.score) for item in shared.contributions] == [
        (1, 0.91),
        (2, 4.1),
    ]


def test_absent_qrel_is_unjudged_not_irrelevant() -> None:
    pool = _pool()
    assert _candidate(pool, "document-1").state == EvidenceJudgment.KNOWN_RELEVANT
    assert _candidate(pool, "document-2").state == EvidenceJudgment.KNOWN_IRRELEVANT
    discovered = _candidate(pool, "document-3")
    assert discovered.existing_qrel is None
    assert discovered.state == EvidenceJudgment.UNJUDGED
    assert discovered.relevance_grade is None


def test_pool_is_deterministic_and_jsonl_friendly() -> None:
    pool = _pool()
    reordered = build_judgment_pool(
        reversed(_hits()), reversed(_qrels()), pool_version="pool-v1"
    )
    assert reordered == pool
    assert JudgmentPool.model_validate_json(pool.model_dump_json()) == pool
    assert all(
        PoolCandidate.model_validate_json(item.model_dump_json()) == item
        for item in pool.candidates
    )


def test_human_adjudication_preserves_provenance_and_versions_output() -> None:
    pool = _pool()
    review = HumanAdjudication(
        query_id="query-1",
        corpus_ref="document-3",
        judgment=EvidenceJudgment.KNOWN_RELEVANT,
        relevance_grade=2,
        reviewer_id="reviewer-c",
        provenance="adjudication-ui/batch-7",
        adjudicated_at=datetime(
            2026, 8, 27, 15, 30, tzinfo=timezone(timedelta(hours=9))
        ),
        pool_fingerprint=pool.fingerprint,
    )
    merged = merge_adjudications(pool, (review,), output_version="pool-v2")
    decided = _candidate(merged, "document-3")

    assert (merged.pool_version, merged.parent_fingerprint) == (
        "pool-v2",
        pool.fingerprint,
    )
    assert merged.fingerprint != pool.fingerprint
    assert (decided.state, decided.relevance_grade) == (
        EvidenceJudgment.KNOWN_RELEVANT,
        2,
    )
    assert decided.adjudications[0].reviewer_id == "reviewer-c"
    assert decided.adjudications[0].provenance == "adjudication-ui/batch-7"
    assert decided.adjudications[0].adjudicated_at == datetime(
        2026, 8, 27, 6, 30, tzinfo=UTC
    )

    second_review = review.model_copy(
        update={
            "reviewer_id": "reviewer-d",
            "adjudicated_at": datetime(2026, 8, 27, 7, 30, tzinfo=UTC),
        }
    )
    assert merge_adjudications(
        pool, (review, second_review), output_version="pool-v3"
    ) == merge_adjudications(pool, (second_review, review), output_version="pool-v3")


@pytest.mark.parametrize(
    ("ref", "decisions", "reason"),
    [
        (
            "document-1",
            ((EvidenceJudgment.KNOWN_IRRELEVANT, None),),
            "judgment_disagreement",
        ),
        (
            "document-3",
            (
                (EvidenceJudgment.KNOWN_RELEVANT, 2),
                (EvidenceJudgment.KNOWN_RELEVANT, 3),
            ),
            "relevance_grade_disagreement",
        ),
        ("missing", ((EvidenceJudgment.KNOWN_RELEVANT, 1),), "unknown_candidate"),
    ],
)
def test_conflicting_adjudication_batches_are_rejected_atomically(
    ref: str,
    decisions: tuple[tuple[EvidenceJudgment, int | None], ...],
    reason: str,
) -> None:
    pool = _pool()
    reviews = tuple(
        HumanAdjudication(
            query_id="query-1",
            corpus_ref=ref,
            judgment=judgment,
            relevance_grade=grade,
            reviewer_id=f"reviewer-{index}",
            provenance="double-review",
            adjudicated_at=datetime(2026, 8, 27, tzinfo=UTC),
            pool_fingerprint=pool.fingerprint,
        )
        for index, (judgment, grade) in enumerate(decisions)
    )
    conflicts = detect_adjudication_conflicts(pool, reviews)
    assert [conflict.reason for conflict in conflicts] == [reason]
    with pytest.raises(JudgmentConflictError) as error:
        merge_adjudications(pool, reviews, output_version="pool-v2")
    assert error.value.conflicts == conflicts


def test_rejects_mixed_corpus_tampering_and_weak_adjudication_metadata() -> None:
    mixed = (
        *_hits(),
        _hits()[0].model_copy(update={"corpus_version": "v5", "run_id": "other"}),
    )
    with pytest.raises(ValueError, match="cannot mix corpus"):
        build_judgment_pool(mixed, pool_version="bad")

    mismatched_qrels = tuple(
        item.model_copy(update={"corpus_version": "corpus-v5"}) for item in _qrels()
    )
    with pytest.raises(ValueError, match="same corpus version"):
        build_judgment_pool(_hits(), mismatched_qrels, pool_version="bad-qrels")

    data = _pool().model_dump(mode="json")
    data["pool_version"] = "tampered"
    with pytest.raises(ValidationError, match="fingerprint does not match"):
        JudgmentPool.model_validate(data)

    with pytest.raises(ValidationError, match="must include a timezone"):
        HumanAdjudication(
            query_id="query-1",
            corpus_ref="document-3",
            judgment=EvidenceJudgment.KNOWN_RELEVANT,
            relevance_grade=2,
            reviewer_id="reviewer-c",
            provenance="manual-review",
            adjudicated_at=datetime(2026, 8, 27),  # noqa: DTZ001 - invalid by design
            pool_fingerprint=_pool().fingerprint,
        )


def test_rejects_stale_or_empty_adjudication_batches() -> None:
    pool = _pool()
    stale_review = HumanAdjudication(
        query_id="query-1",
        corpus_ref="document-3",
        judgment=EvidenceJudgment.KNOWN_RELEVANT,
        relevance_grade=2,
        reviewer_id="reviewer-c",
        provenance="manual-review",
        adjudicated_at=datetime(2026, 8, 27, tzinfo=UTC),
        pool_fingerprint="sha256:" + "0" * 64,
    )

    with pytest.raises(ValueError, match="different judgment pool"):
        merge_adjudications(pool, (stale_review,), output_version="pool-v2")
    with pytest.raises(ValueError, match="at least one adjudication"):
        merge_adjudications(pool, (), output_version="pool-v2")
