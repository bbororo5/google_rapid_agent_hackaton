from __future__ import annotations

import hashlib
import time
from collections.abc import Callable, Mapping
from typing import Any, TypeVar

from google import genai
from google.genai import types
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
            http_options=types.HttpOptions(api_version="v1"),
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
                response = self._client.models.generate_content(
                    model=self.settings.model,
                    contents=input_text,
                    config=types.GenerateContentConfig(
                        system_instruction=system_instruction,
                        thinking_config=types.ThinkingConfig(
                            thinking_level=self.settings.thinking_level,
                            include_thoughts=False,
                        ),
                        max_output_tokens=self.settings.max_output_tokens,
                        seed=requested_seed,
                        response_mime_type="application/json",
                        response_json_schema=response_model.model_json_schema(),
                        labels=dict(labels or {}),
                        http_options=types.HttpOptions(
                            timeout=int(self.settings.timeout_seconds * 1000)
                        ),
                    ),
                )
                output_text = response.text or ""
                payload = response_model.model_validate_json(output_text)
                usage = getattr(response, "usage_metadata", None)
                metadata = JudgeCallMetadata(
                    model=(
                        getattr(response, "model_version", None) or self.settings.model
                    ),
                    thinking_level=self.settings.thinking_level,
                    request_id=getattr(response, "response_id", None),
                    requested_seed=requested_seed,
                    latency_ms=(time.perf_counter() - started) * 1000,
                    input_tokens=getattr(usage, "prompt_token_count", None),
                    output_tokens=getattr(usage, "candidates_token_count", None),
                    thought_tokens=getattr(usage, "thoughts_token_count", None),
                    retry_count=attempt,
                    response_fingerprint=(
                        "sha256:" + hashlib.sha256(output_text.encode()).hexdigest()
                    ),
                    response_status=str(
                        getattr(response, "model_status", None) or "completed"
                    ),
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
