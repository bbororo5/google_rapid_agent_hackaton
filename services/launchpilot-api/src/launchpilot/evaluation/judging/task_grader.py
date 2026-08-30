from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

from launchpilot.evaluation.contracts import (
    EvalSpecification,
    GraderEfficiencyObservation,
    ProblemRecord,
)
from launchpilot.evaluation.controlled_runner import (
    GraderProvenance,
    TrialGrade,
    TrialObservation,
)

from .contracts import TaskJudgment
from .gemini_client import GeminiJudgeClient
from .policy import TaskGradingPolicy, retrieval_diagnostics
from .world_evidence import WorldEvidenceResolver


class TaskAnswerRubric(BaseModel):
    model_config = ConfigDict(frozen=True)

    rubric_version: str = Field(min_length=1)
    response_schema_version: str = Field(min_length=1)
    system_instruction: str = Field(min_length=1)

    @classmethod
    def load(cls, path: Path) -> TaskAnswerRubric:
        return cls.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


class GeminiTaskTrialGrader:
    """Grade one completed system trial without exposing privileged gold answers."""

    def __init__(
        self,
        *,
        client: GeminiJudgeClient,
        resolver: WorldEvidenceResolver,
        rubric: TaskAnswerRubric,
        policy: TaskGradingPolicy | None = None,
    ) -> None:
        self._client = client
        self._resolver = resolver
        self._rubric = rubric
        self._policy = policy or TaskGradingPolicy()

    def grade(
        self,
        *,
        query: ProblemRecord,
        specification: EvalSpecification,
        observation: TrialObservation,
        provenance: GraderProvenance,
        requested_seed: int | None,
    ) -> TrialGrade:
        self._validate_provenance(provenance, specification)
        resolution = self._resolver.resolve_observation(
            observation.retrieved_evidence_refs
        )
        judge_input = {
            "problem": {
                "problem_id": query.problem_id,
                "user_utterance": query.user_utterance,
                "information_need": query.information_need,
                "supplied_context": [
                    item.model_dump(mode="json") for item in query.supplied_context
                ],
            },
            "success_specification": {
                "answerability": specification.answerability.value,
                "required_facts": [
                    {
                        "fact_id": fact.fact_id,
                        "description": fact.description,
                        "unit": fact.unit,
                    }
                    for fact in specification.required_facts
                ],
                "expected_behaviors": [
                    item.value for item in specification.expected_behaviors
                ],
            },
            "run_result": {
                "final_answer": observation.final_answer,
                "retrieved_evidence": [
                    item.model_dump(mode="json") for item in resolution.resolved
                ],
                "unresolved_evidence_refs": resolution.unknown_refs,
            },
        }
        call = self._client.judge(
            input_text=json.dumps(judge_input, ensure_ascii=False, sort_keys=True),
            system_instruction=self._rubric.system_instruction,
            response_model=TaskJudgment,
            requested_seed=requested_seed,
            labels={"purpose": "eval-task-grade"},
        )
        self._validate_judgment(specification, resolution.resolved, call.payload)
        outcome = self._policy.aggregate(specification, call.payload)
        details = {
            "rubric_version": self._rubric.rubric_version,
            "response_schema_version": self._rubric.response_schema_version,
            "policy_version": self._policy.policy_version,
            "judgment": call.payload.model_dump(mode="json"),
            "unknown_evidence_refs": list(resolution.unknown_refs),
            "response_fingerprint": call.metadata.response_fingerprint,
        }
        encoded = json.dumps(
            details, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
        metadata = call.metadata
        return TrialGrade(
            outcome=outcome,
            retrieval=retrieval_diagnostics(
                specification, observation.retrieved_evidence_refs
            ),
            effective_seed=metadata.requested_seed,
            grader_request_id=metadata.request_id,
            grader_efficiency=GraderEfficiencyObservation(
                latency_ms=metadata.latency_ms,
                input_tokens=metadata.input_tokens,
                output_tokens=metadata.output_tokens,
                thought_tokens=metadata.thought_tokens,
                retry_count=metadata.retry_count,
                telemetry_complete=(
                    metadata.input_tokens is not None
                    and metadata.output_tokens is not None
                ),
            ),
            grade_artifact_ref="sha256:" + hashlib.sha256(encoded).hexdigest(),
            grade_details=details,
        )

    def _validate_provenance(
        self,
        provenance: GraderProvenance,
        specification: EvalSpecification,
    ) -> None:
        expected = {
            "model": self._client.settings.model,
            "provider": "vertex_ai",
            "thinking_level": self._client.settings.thinking_level,
            "prompt_version": self._rubric.rubric_version,
            "response_schema_version": self._rubric.response_schema_version,
        }
        mismatches = {
            field: (getattr(provenance, field), value)
            for field, value in expected.items()
            if getattr(provenance, field) != value
        }
        if mismatches:
            raise ValueError(f"grader provenance does not match runtime: {mismatches}")
        if specification.grader_rubric_version != self._rubric.rubric_version:
            raise ValueError("specification and runtime rubric versions differ")

    @staticmethod
    def _validate_judgment(
        specification: EvalSpecification,
        resolved_evidence,
        judgment: TaskJudgment,
    ) -> None:
        expected_fact_ids = {fact.fact_id for fact in specification.required_facts}
        actual_fact_ids = {fact.fact_id for fact in judgment.fact_judgments}
        if expected_fact_ids != actual_fact_ids:
            raise ValueError("judge returned an incomplete or foreign fact-id set")
        allowed_refs = {item.evidence_ref for item in resolved_evidence}
        cited_refs = {
            ref
            for item in (*judgment.fact_judgments, *judgment.claim_judgments)
            for ref in item.evidence_refs
        }
        unknown = cited_refs - allowed_refs
        if unknown:
            raise ValueError(f"judge cited evidence absent from trial context: {unknown}")
