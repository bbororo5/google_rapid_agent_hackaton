from __future__ import annotations

import os
from dataclasses import dataclass

_SUPPORTED_THINKING_LEVELS = {"low", "medium", "high"}


@dataclass(frozen=True, slots=True)
class GeminiJudgeSettings:
    """Evaluation-only Gemini settings; never inherited from the agent model."""

    project: str
    model: str = "gemini-3.7-flash"
    thinking_level: str = "medium"
    location: str = "global"
    timeout_seconds: float = 60.0
    max_retries: int = 2
    max_output_tokens: int = 8192

    def __post_init__(self) -> None:
        if not self.project.strip():
            raise ValueError("Gemini judge requires a Google Cloud project")
        if self.model != "gemini-3.7-flash":
            raise ValueError("Gemini judge model must be gemini-3.7-flash")
        if self.thinking_level not in _SUPPORTED_THINKING_LEVELS:
            raise ValueError(
                "Gemini 3.7 Flash thinking level must be low, medium, or high"
            )
        if self.timeout_seconds <= 0:
            raise ValueError("judge timeout must be positive")
        if self.max_retries < 0:
            raise ValueError("judge max_retries cannot be negative")
        if self.max_output_tokens < 1:
            raise ValueError("judge max_output_tokens must be positive")

    @classmethod
    def from_environment(cls) -> GeminiJudgeSettings:
        project = os.getenv("GOOGLE_CLOUD_PROJECT", "")
        return cls(
            project=project,
            model=os.getenv("EVAL_JUDGE_MODEL", "gemini-3.7-flash"),
            thinking_level=os.getenv("EVAL_JUDGE_THINKING_LEVEL", "medium").lower(),
            location=os.getenv("EVAL_JUDGE_LOCATION", "global"),
            timeout_seconds=float(os.getenv("EVAL_JUDGE_TIMEOUT_SECONDS", "60")),
            max_retries=int(os.getenv("EVAL_JUDGE_MAX_RETRIES", "2")),
            max_output_tokens=int(os.getenv("EVAL_JUDGE_MAX_OUTPUT_TOKENS", "8192")),
        )
