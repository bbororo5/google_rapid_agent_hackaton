"""Method-independent retrieval experiment framework."""

from .contracts import (
    ChunkingConfig,
    ChunkingMethod,
    EvaluationCase,
    EvaluationDocument,
    ExperimentManifest,
    ExperimentResult,
    ExperimentStatus,
    FusionMethod,
    GoldEvidence,
    RetrievalConfig,
)
from .runner import RetrievalExperimentRunner

__all__ = [
    "ChunkingConfig",
    "ChunkingMethod",
    "EvaluationCase",
    "EvaluationDocument",
    "ExperimentManifest",
    "ExperimentResult",
    "ExperimentStatus",
    "FusionMethod",
    "GoldEvidence",
    "RetrievalConfig",
    "RetrievalExperimentRunner",
]
