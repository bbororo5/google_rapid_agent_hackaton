"""Evaluation contracts shared by dataset authoring and future eval runners."""

from .golden_dataset import (
    ExpectedEvidence,
    ExpectedFact,
    GoldenRetrievalCase,
    RetrievalTaskType,
    load_golden_dataset,
)

__all__ = [
    "ExpectedEvidence",
    "ExpectedFact",
    "GoldenRetrievalCase",
    "RetrievalTaskType",
    "load_golden_dataset",
]
