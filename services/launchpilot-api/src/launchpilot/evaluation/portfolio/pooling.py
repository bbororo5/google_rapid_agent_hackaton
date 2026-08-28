from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from collections.abc import Iterable
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from launchpilot.evaluation.contracts.architecture_eval import EvidenceJudgment

SCHEMA_VERSION = "judgment-pool/v1"


def _grade(judgment: EvidenceJudgment, grade: int | None) -> int | None:
    return 0 if judgment == EvidenceJudgment.KNOWN_IRRELEVANT else grade


def _check_grade(
    judgment: EvidenceJudgment, grade: int | None, *, human: bool = False
) -> None:
    if judgment == EvidenceJudgment.KNOWN_RELEVANT and grade not in (1, 2, 3):
        raise ValueError("known relevant evidence requires grade 1..3")
    if judgment == EvidenceJudgment.KNOWN_IRRELEVANT and grade not in (None, 0):
        raise ValueError("known irrelevant evidence can only have grade 0")
    if judgment == EvidenceJudgment.UNJUDGED and (human or grade is not None):
        raise ValueError("human adjudication must make a known judgment")


class RetrievedHit(BaseModel):
    """One JSONL row from a versioned system's top-k output."""

    model_config = ConfigDict(frozen=True)

    run_id: str = Field(min_length=1)
    system_version: str = Field(min_length=1)
    corpus_version: str = Field(min_length=1)
    index_version: str = Field(min_length=1)
    query_id: str = Field(min_length=1)
    corpus_ref: str = Field(min_length=1)
    rank: int = Field(ge=1)
    score: float | None = Field(default=None, allow_inf_nan=False)
    top_k: int = Field(ge=1)

    @model_validator(mode="after")
    def validate_rank(self) -> RetrievedHit:
        if self.rank > self.top_k:
            raise ValueError("rank cannot exceed top_k")
        return self


class ExistingQrel(BaseModel):
    model_config = ConfigDict(frozen=True)

    query_id: str = Field(min_length=1)
    corpus_ref: str = Field(min_length=1)
    judgment: EvidenceJudgment
    relevance_grade: int | None = Field(default=None, ge=0, le=3)
    corpus_version: str = Field(min_length=1)
    qrel_version: str = Field(min_length=1)
    provenance: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_grade(self) -> ExistingQrel:
        _check_grade(self.judgment, self.relevance_grade)
        return self


class HumanAdjudication(BaseModel):
    model_config = ConfigDict(frozen=True)

    query_id: str = Field(min_length=1)
    corpus_ref: str = Field(min_length=1)
    judgment: EvidenceJudgment
    relevance_grade: int | None = Field(default=None, ge=0, le=3)
    reviewer_id: str = Field(min_length=1)
    provenance: str = Field(min_length=1)
    adjudicated_at: datetime
    rationale: str | None = None
    pool_fingerprint: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")

    @field_validator("adjudicated_at")
    @classmethod
    def validate_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("adjudicated_at must include a timezone")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_grade(self) -> HumanAdjudication:
        _check_grade(self.judgment, self.relevance_grade, human=True)
        return self


class PoolCandidate(BaseModel):
    """One deduplicated query/corpus pair and every system that contributed it."""

    model_config = ConfigDict(frozen=True)

    query_id: str
    corpus_ref: str
    state: EvidenceJudgment
    relevance_grade: int | None = Field(default=None, ge=0, le=3)
    contributions: tuple[RetrievedHit, ...] = Field(min_length=1)
    existing_qrel: ExistingQrel | None = None
    adjudications: tuple[HumanAdjudication, ...] = ()


class AdjudicationConflict(BaseModel):
    model_config = ConfigDict(frozen=True)

    query_id: str
    corpus_ref: str
    reason: str
    reviewer_ids: tuple[str, ...]


class JudgmentConflictError(ValueError):
    def __init__(self, conflicts: tuple[AdjudicationConflict, ...]) -> None:
        self.conflicts = conflicts
        super().__init__(
            "adjudication conflicts detected: "
            + ", ".join(
                f"{item.query_id}/{item.corpus_ref}:{item.reason}" for item in conflicts
            )
        )


class JudgmentPool(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: str = SCHEMA_VERSION
    pool_version: str = Field(min_length=1)
    corpus_version: str = Field(min_length=1)
    qrel_version: str | None = None
    parent_fingerprint: str | None = None
    candidates: tuple[PoolCandidate, ...]
    fingerprint: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_fingerprint(self) -> JudgmentPool:
        if self.fingerprint != _fingerprint(
            self.model_dump(mode="json", exclude={"fingerprint"})
        ):
            raise ValueError("judgment pool fingerprint does not match content")
        return self


def _fingerprint(payload: dict[str, object]) -> str:
    content = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    return f"sha256:{hashlib.sha256(content).hexdigest()}"


def _pool(
    version: str,
    corpus_version: str,
    candidates: tuple[PoolCandidate, ...],
    qrel_version: str | None,
    parent: str | None = None,
) -> JudgmentPool:
    payload: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "pool_version": version,
        "corpus_version": corpus_version,
        "qrel_version": qrel_version,
        "parent_fingerprint": parent,
        "candidates": [item.model_dump(mode="json") for item in candidates],
    }
    return JudgmentPool(**payload, fingerprint=_fingerprint(payload))


def build_judgment_pool(
    hits: Iterable[RetrievedHit],
    existing_qrels: Iterable[ExistingQrel] = (),
    *,
    pool_version: str,
) -> JudgmentPool:
    """Pool top-k hits; absence from qrels always means UNJUDGED, never irrelevant."""

    rows = tuple(hits)
    corpus_versions = {row.corpus_version for row in rows}
    if not rows:
        raise ValueError("at least one retrieved hit is required")
    if len(corpus_versions) != 1:
        raise ValueError("a pool cannot mix corpus versions")

    seen_runs: dict[str, tuple[str, str, str, int]] = {}
    seen_ranks: set[tuple[str, str, int]] = set()
    seen_refs: set[tuple[str, str, str]] = set()
    grouped: dict[tuple[str, str], list[RetrievedHit]] = defaultdict(list)
    for row in rows:
        metadata = (
            row.system_version,
            row.corpus_version,
            row.index_version,
            row.top_k,
        )
        if row.run_id in seen_runs and seen_runs[row.run_id] != metadata:
            raise ValueError(f"inconsistent metadata for run {row.run_id}")
        seen_runs[row.run_id] = metadata
        rank_key = (row.run_id, row.query_id, row.rank)
        ref_key = (row.run_id, row.query_id, row.corpus_ref)
        if rank_key in seen_ranks or ref_key in seen_refs:
            raise ValueError(
                f"duplicate rank or corpus_ref in {row.run_id}/{row.query_id}"
            )
        seen_ranks.add(rank_key)
        seen_refs.add(ref_key)
        grouped[(row.query_id, row.corpus_ref)].append(row)

    qrel_rows = tuple(existing_qrels)
    qrel_corpus_versions = {qrel.corpus_version for qrel in qrel_rows}
    if qrel_corpus_versions and qrel_corpus_versions != corpus_versions:
        raise ValueError("qrels and retrieved hits must use the same corpus version")
    qrel_versions = {qrel.qrel_version for qrel in qrel_rows}
    if len(qrel_versions) > 1:
        raise ValueError("a pool cannot mix qrel versions")

    qrels: dict[tuple[str, str], ExistingQrel] = {}
    for qrel in qrel_rows:
        key = (qrel.query_id, qrel.corpus_ref)
        if key in qrels:
            raise ValueError(f"duplicate existing qrel: {key}")
        qrels[key] = qrel

    candidates = []
    for key in sorted(grouped):
        qrel = qrels.get(key)
        state = qrel.judgment if qrel else EvidenceJudgment.UNJUDGED
        candidates.append(
            PoolCandidate(
                query_id=key[0],
                corpus_ref=key[1],
                state=state,
                relevance_grade=_grade(state, qrel.relevance_grade) if qrel else None,
                contributions=tuple(
                    sorted(
                        grouped[key],
                        key=lambda row: (
                            row.system_version,
                            row.index_version,
                            row.run_id,
                            row.rank,
                        ),
                    )
                ),
                existing_qrel=qrel,
            )
        )
    return _pool(
        pool_version,
        corpus_versions.pop(),
        tuple(candidates),
        next(iter(qrel_versions), None),
    )


def detect_adjudication_conflicts(
    pool: JudgmentPool, adjudications: Iterable[HumanAdjudication]
) -> tuple[AdjudicationConflict, ...]:
    candidates = {(item.query_id, item.corpus_ref): item for item in pool.candidates}
    grouped: dict[tuple[str, str], list[HumanAdjudication]] = defaultdict(list)
    for item in adjudications:
        if item.pool_fingerprint != pool.fingerprint:
            raise ValueError("adjudication targets a different judgment pool")
        grouped[(item.query_id, item.corpus_ref)].append(item)

    conflicts = []
    for key in sorted(grouped):
        candidate, reviews = candidates.get(key), grouped[key]
        decisions = {
            (review.judgment, _grade(review.judgment, review.relevance_grade))
            for review in reviews
        }
        if candidate and candidate.state != EvidenceJudgment.UNJUDGED:
            decisions.add((candidate.state, candidate.relevance_grade))
        states = {decision[0] for decision in decisions}
        reason = (
            "unknown_candidate"
            if candidate is None
            else "judgment_disagreement"
            if len(states) > 1
            else "relevance_grade_disagreement"
            if len(decisions) > 1
            else ""
        )
        if reason:
            conflicts.append(
                AdjudicationConflict(
                    query_id=key[0],
                    corpus_ref=key[1],
                    reason=reason,
                    reviewer_ids=tuple(
                        sorted({review.reviewer_id for review in reviews})
                    ),
                )
            )
    return tuple(conflicts)


def merge_adjudications(
    pool: JudgmentPool,
    adjudications: Iterable[HumanAdjudication],
    *,
    output_version: str,
) -> JudgmentPool:
    """Atomically merge a conflict-free human review batch into a new snapshot."""

    incoming = tuple(adjudications)
    if not incoming:
        raise ValueError("at least one adjudication is required")
    conflicts = detect_adjudication_conflicts(pool, incoming)
    if conflicts:
        raise JudgmentConflictError(conflicts)
    grouped: dict[tuple[str, str], list[HumanAdjudication]] = defaultdict(list)
    for review in incoming:
        grouped[(review.query_id, review.corpus_ref)].append(review)

    candidates = []
    for candidate in pool.candidates:
        key = (candidate.query_id, candidate.corpus_ref)
        deduped = {
            item.model_dump_json(): item
            for item in (*candidate.adjudications, *grouped.get(key, ()))
        }
        reviews = tuple(
            sorted(
                deduped.values(),
                key=lambda item: (
                    item.adjudicated_at,
                    item.reviewer_id,
                    item.provenance,
                    item.judgment.value,
                    _grade(item.judgment, item.relevance_grade),
                    item.rationale or "",
                ),
            )
        )
        state = candidate.state if not reviews else reviews[0].judgment
        grade = (
            candidate.relevance_grade
            if not reviews
            else _grade(state, reviews[0].relevance_grade)
        )
        candidates.append(
            candidate.model_copy(
                update={
                    "state": state,
                    "relevance_grade": grade,
                    "adjudications": reviews,
                }
            )
        )
    return _pool(
        output_version,
        pool.corpus_version,
        tuple(candidates),
        pool.qrel_version,
        parent=pool.fingerprint,
    )
