from __future__ import annotations

import hashlib
import time
from collections.abc import Callable, Mapping
from typing import Any, TypeVar

from google import genai
from google.genai.errors import ClientError, ServerError
from pydantic import BaseModel, ValidationError

from .config import GeminiJudgeSettings
from .contracts import JudgeCall, JudgeCallMetadata

ResponseT = TypeVar("ResponseT", bound=BaseModel)


class JudgeProviderError(RuntimeError):
    """The judge provider failed before a valid structured verdict was produced."""


class _PreflightResponse(BaseModel):
    ok: bool


class GeminiJudgeClient:
    """One-shot, tool-free, structured Gemini judge on Vertex AI."""

    def __init__(
        self,
        settings: GeminiJudgeSettings,
        *,
        client: Any | None = None,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.settings = settings
        self._client = client or genai.Client(
            vertexai=True,
            project=settings.project,
            location=settings.location,
        )
        self._sleeper = sleeper

    def judge(
        self,
        *,
        input_text: str,
        system_instruction: str,
        response_model: type[ResponseT],
        requested_seed: int | None = None,
        labels: Mapping[str, str] | None = None,
    ) -> JudgeCall[ResponseT]:
        if not input_text.strip():
            raise ValueError("judge input cannot be empty")
        if not system_instruction.strip():
            raise ValueError("judge system instruction cannot be empty")

        started = time.perf_counter()
        last_error: Exception | None = None
        for attempt in range(self.settings.max_retries + 1):
            try:
                response = self._client.interactions.create(
                    model=self.settings.model,
                    input=input_text,
                    system_instruction=system_instruction,
                    generation_config={
                        "thinking_level": self.settings.thinking_level,
                        "thinking_summaries": "none",
                        "max_output_tokens": self.settings.max_output_tokens,
                        **({"seed": requested_seed} if requested_seed is not None else {}),
                    },
                    response_format={
                        "type": "text",
                        "mime_type": "application/json",
                        "schema": response_model.model_json_schema(),
                    },
                    labels=dict(labels or {}),
                    store=False,
                    timeout=self.settings.timeout_seconds,
                )
                output_text = response.output_text or ""
                payload = response_model.model_validate_json(output_text)
                usage = getattr(response, "usage", None)
                metadata = JudgeCallMetadata(
                    model=getattr(response, "model", None) or self.settings.model,
                    thinking_level=self.settings.thinking_level,
                    request_id=getattr(response, "id", None),
                    requested_seed=requested_seed,
                    latency_ms=(time.perf_counter() - started) * 1000,
                    input_tokens=getattr(usage, "total_input_tokens", None),
                    output_tokens=getattr(usage, "total_output_tokens", None),
                    thought_tokens=getattr(usage, "total_thought_tokens", None),
                    retry_count=attempt,
                    response_fingerprint=(
                        "sha256:" + hashlib.sha256(output_text.encode()).hexdigest()
                    ),
                    response_status=str(getattr(response, "status", "completed")),
                )
                return JudgeCall[ResponseT](payload=payload, metadata=metadata)
            except (ServerError, ValidationError) as error:
                last_error = error
            except ClientError as error:
                if getattr(error, "code", None) not in {408, 429}:
                    raise JudgeProviderError(_safe_provider_message(error)) from error
                last_error = error
            if attempt < self.settings.max_retries:
                self._sleeper(0.25 * (2**attempt))

        assert last_error is not None
        raise JudgeProviderError(_safe_provider_message(last_error)) from last_error

    def preflight(self) -> JudgeCall[_PreflightResponse]:
        return self.judge(
            input_text="Return ok=true.",
            system_instruction="Validate structured judge connectivity only.",
            response_model=_PreflightResponse,
            labels={"purpose": "eval-judge-preflight"},
        )


def _safe_provider_message(error: Exception) -> str:
    message = " ".join(str(error).split())
    return f"Gemini judge request failed: {message[:500]}"
