from __future__ import annotations

from datetime import date
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator


class RetrievalTaskType(StrEnum):
    STRUCTURED = "structured"
    TEXTUAL = "textual"
    RELATIONAL = "relational"


class GoldenScope(BaseModel):
    """Stable logical scope; the eval runner resolves it to environment UUIDs."""

    model_config = ConfigDict(frozen=True)

    scenario_id: str = Field(min_length=1)
    campaign_ref: str = Field(min_length=1)
    start_date: date | None = None
    end_date: date | None = None
    platforms: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_period(self) -> GoldenScope:
        if (self.start_date is None) != (self.end_date is None):
            raise ValueError("start_date and end_date must be supplied together")
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValueError("start_date must be on or before end_date")
        return self


class ExpectedEvidence(BaseModel):
    model_config = ConfigDict(frozen=True)

    source_ref: str = Field(min_length=1)
    passage: str = Field(min_length=1)
    document_ref: str | None = None


class ExpectedFact(BaseModel):
    model_config = ConfigDict(frozen=True)

    key: str = Field(min_length=1)
    value: str = Field(min_length=1)
    unit: str | None = None
    provenance_prefixes: tuple[str, ...] = Field(min_length=1)


class GoldenRetrievalCase(BaseModel):
    """One human-reviewed query and the evidence or facts it must retrieve."""

    model_config = ConfigDict(frozen=True)

    dataset_version: str = Field(default="v1", pattern=r"^v[1-9][0-9]*$")
    case_id: str = Field(min_length=1, pattern=r"^[a-z0-9][a-z0-9._-]*$")
    query: str = Field(min_length=1)
    task_type: RetrievalTaskType
    scope: GoldenScope
    expected_evidence: tuple[ExpectedEvidence, ...] = ()
    expected_facts: tuple[ExpectedFact, ...] = ()
    tags: tuple[str, ...] = ()

    @model_validator(mode="after")
    def require_task_ground_truth(self) -> GoldenRetrievalCase:
        if self.task_type == RetrievalTaskType.STRUCTURED:
            if not self.expected_facts:
                raise ValueError("structured cases require expected_facts")
        elif not self.expected_evidence:
            raise ValueError("textual and relational cases require expected_evidence")
        return self


def load_golden_dataset(path: Path) -> tuple[GoldenRetrievalCase, ...]:
    cases = tuple(
        GoldenRetrievalCase.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    )
    case_ids = [case.case_id for case in cases]
    if len(case_ids) != len(set(case_ids)):
        raise ValueError("golden dataset case_id values must be unique")
    return cases
