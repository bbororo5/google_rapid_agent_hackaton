"""Machine adjudication and answer grading for architecture evaluations."""

from .config import GeminiJudgeSettings
from .contracts import (
    BehaviorJudgment,
    ClaimJudgment,
    ConfidenceLevel,
    FactJudgment,
    JudgeCall,
    JudgeCallMetadata,
    JudgeVerdict,
    RelevanceJudgment,
    TaskJudgment,
)
from .gemini_client import GeminiJudgeClient, JudgeProviderError
from .policy import TaskGradingPolicy, retrieval_diagnostics
from .task_grader import GeminiTaskTrialGrader, TaskAnswerRubric
from .world_evidence import EvidenceResolution, ResolvedEvidence, WorldEvidenceResolver

__all__ = [
    "BehaviorJudgment",
    "ClaimJudgment",
    "ConfidenceLevel",
    "EvidenceResolution",
    "FactJudgment",
    "GeminiJudgeClient",
    "GeminiJudgeSettings",
    "GeminiTaskTrialGrader",
    "JudgeCall",
    "JudgeCallMetadata",
    "JudgeProviderError",
    "JudgeVerdict",
    "RelevanceJudgment",
    "ResolvedEvidence",
    "TaskAnswerRubric",
    "TaskGradingPolicy",
    "TaskJudgment",
    "WorldEvidenceResolver",
    "retrieval_diagnostics",
]
