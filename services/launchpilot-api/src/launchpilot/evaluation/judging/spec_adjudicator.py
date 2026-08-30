from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

from launchpilot.evaluation.contracts import (
    Answerability,
    EvalSpecification,
    EvidenceJudgment,
    ProblemRecord,
)

from .contracts import (
    JudgeCall,
    SpecificationAdjudication,
    SpecificationAdjudicationVerdict,
)
from .gemini_client import GeminiJudgeClient
from .world_evidence import WorldEvidenceResolver


class AdjudicationDecision(StrEnum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    NEEDS_REVIEW = "needs_review"


class SpecificationAdjudicationRubric(BaseModel):
    model_config = ConfigDict(frozen=True)

    rubric_version: str = Field(min_length=1)
    response_schema_version: str = Field(min_length=1)
    system_instruction: str = Field(min_length=1)

    @classmethod
    def load(cls, path: Path) -> SpecificationAdjudicationRubric:
        return cls.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


class AdjudicationPass(BaseModel):
    model_config = ConfigDict(frozen=True)

    pass_number: int = Field(ge=1)
    call: JudgeCall[SpecificationAdjudication]


class SpecificationAdjudicationRecord(BaseModel):
    """Append-only machine review record; never presented as human review."""

    model_config = ConfigDict(frozen=True)

    problem_id: str = Field(min_length=1)
    spec_id: str = Field(min_length=1)
    source_spec_version: str = Field(min_length=1)
    source_spec_fingerprint: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    policy_version: str = "two-pass-consensus-v1"
    rubric_version: str = Field(min_length=1)
    response_schema_version: str = Field(min_length=1)
    decision: AdjudicationDecision
    passes: tuple[AdjudicationPass, ...] = Field(min_length=2, max_length=2)
    decision_reason: str = Field(min_length=1)


class GeminiSpecificationAdjudicator:
    """Audit a success definition twice before allowing machine adjudication."""

    def __init__(
        self,
        *,
        client: GeminiJudgeClient,
        resolver: WorldEvidenceResolver,
        rubric: SpecificationAdjudicationRubric,
    ) -> None:
        self._client = client
        self._resolver = resolver
        self._rubric = rubric

    def adjudicate(
        self,
        *,
        problem: ProblemRecord,
        specification: EvalSpecification,
        base_seed: int | None = None,
    ) -> SpecificationAdjudicationRecord:
        if problem.problem_id != specification.problem_id:
            raise ValueError("problem and specification ids differ")
        if specification.answerability != Answerability.ANSWERABLE:
            raise ValueError(
                "non-answerability requires exhaustive-world adjudication; "
                "empty qrels cannot prove absence"
            )
        known_relevant_refs = tuple(
            item.evidence_ref
            for item in specification.evidence_assessments
            if item.judgment == EvidenceJudgment.KNOWN_RELEVANT
        )
        if not known_relevant_refs:
            raise ValueError("answerable specification has no known relevant evidence")
        evidence = self._resolver.resolve(known_relevant_refs)
        input_payload = {
            "problem": problem.model_dump(mode="json"),
            "candidate_success_specification": specification.model_dump(mode="json"),
            "known_relevant_evidence": [
                item.model_dump(mode="json") for item in evidence
            ],
            "scope_note": (
                "Known relevant evidence is a positive seed, not a complete qrel set. "
                "Unlisted evidence remains unjudged."
            ),
        }
        passes = tuple(
            AdjudicationPass(
                pass_number=pass_number,
                call=self._call(
                    input_payload,
                    pass_number=pass_number,
                    seed=(base_seed + pass_number if base_seed is not None else None),
                    specification=specification,
                ),
            )
            for pass_number in (1, 2)
        )
        decision, reason = _consensus(tuple(item.call.payload for item in passes))
        canonical_spec = json.dumps(
            specification.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return SpecificationAdjudicationRecord(
            problem_id=problem.problem_id,
            spec_id=specification.spec_id,
            source_spec_version=specification.spec_version,
            source_spec_fingerprint=(
                "sha256:" + hashlib.sha256(canonical_spec).hexdigest()
            ),
            rubric_version=self._rubric.rubric_version,
            response_schema_version=self._rubric.response_schema_version,
            decision=decision,
            passes=passes,
            decision_reason=reason,
        )

    def _call(
        self,
        input_payload: dict[str, object],
        *,
        pass_number: int,
        seed: int | None,
        specification: EvalSpecification,
    ) -> JudgeCall[SpecificationAdjudication]:
        call = self._client.judge(
            input_text=json.dumps(input_payload, ensure_ascii=False, sort_keys=True),
            system_instruction=self._rubric.system_instruction,
            response_model=SpecificationAdjudication,
            requested_seed=seed,
            labels={
                "purpose": "eval-spec-adjudication",
                "pass": str(pass_number),
            },
        )
        expected_fact_ids = {fact.fact_id for fact in specification.required_facts}
        foreign = set(call.payload.unsupported_fact_ids) - expected_fact_ids
        if foreign:
            raise ValueError(f"judge returned foreign unsupported fact ids: {foreign}")
        return call


def _consensus(
    verdicts: tuple[SpecificationAdjudication, SpecificationAdjudication],
) -> tuple[AdjudicationDecision, str]:
    if all(item.verdict == SpecificationAdjudicationVerdict.ACCEPT for item in verdicts):
        signatures = {
            (
                item.problem_spec_aligned,
                item.required_facts_supported,
                item.answerability_consistent,
                item.behavior_consistent,
                item.tool_independent,
            )
            for item in verdicts
        }
        if len(signatures) == 1:
            return AdjudicationDecision.ACCEPTED, "two independent passes accepted"
    if all(item.verdict == SpecificationAdjudicationVerdict.REJECT for item in verdicts):
        return AdjudicationDecision.REJECTED, "two independent passes rejected"
    return (
        AdjudicationDecision.NEEDS_REVIEW,
        "passes disagreed or at least one verdict was indeterminate",
    )
