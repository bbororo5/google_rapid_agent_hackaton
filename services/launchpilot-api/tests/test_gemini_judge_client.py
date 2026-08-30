from __future__ import annotations

from dataclasses import dataclass, field

import pytest
from pydantic import BaseModel

from launchpilot.evaluation.judging import GeminiJudgeClient, GeminiJudgeSettings


class _Verdict(BaseModel):
    accepted: bool


@dataclass
class _Usage:
    prompt_token_count: int = 120
    candidates_token_count: int = 20
    thoughts_token_count: int = 40


@dataclass
class _Response:
    text: str = '{"accepted":true}'
    response_id: str = "response-1"
    model_version: str = "gemini-3.7-flash"
    model_status: str = "completed"
    usage_metadata: _Usage = field(default_factory=_Usage)


class _Models:
    def __init__(self, responses: list[object]) -> None:
        self.responses = responses
        self.calls: list[dict[str, object]] = []

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        result = self.responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


class _Client:
    def __init__(self, responses: list[object]) -> None:
        self.models = _Models(responses)


def _settings(**updates) -> GeminiJudgeSettings:
    return GeminiJudgeSettings(project="project-1", **updates)


def test_settings_are_eval_specific_and_pin_gemini_37_medium() -> None:
    settings = _settings()
    assert settings.model == "gemini-3.7-flash"
    assert settings.thinking_level == "medium"
    assert settings.location == "global"
    with pytest.raises(ValueError, match="must be gemini-3.7-flash"):
        _settings(model="gemini-3.6-flash")
    with pytest.raises(ValueError, match="low, medium, or high"):
        _settings(thinking_level="minimal")


def test_client_uses_structured_output_medium_thinking_and_no_sampling_params() -> None:
    fake = _Client([_Response()])
    judge = GeminiJudgeClient(_settings(), client=fake)

    result = judge.judge(
        input_text="evaluate",
        system_instruction="judge carefully",
        response_model=_Verdict,
        requested_seed=17,
        labels={"run_id": "run-1"},
    )

    assert result.payload.accepted is True
    assert result.metadata.request_id == "response-1"
    assert result.metadata.thought_tokens == 40
    call = fake.models.calls[0]
    assert call["model"] == "gemini-3.7-flash"
    config = call["config"]
    assert config.thinking_config.thinking_level.value == "MEDIUM"
    assert config.thinking_config.include_thoughts is False
    assert config.max_output_tokens == 8192
    assert config.seed == 17
    assert config.temperature is None
    assert config.top_p is None
    assert config.top_k is None
    assert config.response_mime_type == "application/json"
    assert config.response_json_schema == _Verdict.model_json_schema()


def test_invalid_structured_response_is_retried() -> None:
    fake = _Client([_Response(text="not-json"), _Response()])
    sleeps: list[float] = []
    judge = GeminiJudgeClient(
        _settings(max_retries=1), client=fake, sleeper=sleeps.append
    )

    result = judge.judge(
        input_text="evaluate",
        system_instruction="judge carefully",
        response_model=_Verdict,
    )

    assert result.metadata.retry_count == 1
    assert sleeps == [0.25]
    assert len(fake.models.calls) == 2
