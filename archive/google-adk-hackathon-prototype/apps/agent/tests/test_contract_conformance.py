"""The contract example JSONs must validate against our Pydantic models.

This is the enforcement net: if a contract changes and schemas.py drifts, these
fail. Uses the shipped examples under contracts/ as the source of truth.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.contracts import (
    AgentResultPayload,
    ExperimentPlanDraftOutput,
    HypothesisDraftOutput,
    InternalAgentTurn,
    InternalStreamMessage,
    SignalDraftOutput,
    ValidationReport,
)

CONTRACTS = Path(__file__).resolve().parents[3] / "contracts"


def _load(rel: str) -> dict:
    return json.loads((CONTRACTS / rel).read_text(encoding="utf-8"))


CASES = [
    ("05-agent-output/examples/signal-draft-output.json", SignalDraftOutput),
    ("05-agent-output/examples/hypothesis-draft-output.json", HypothesisDraftOutput),
    ("05-agent-output/examples/experiment-plan-draft-output.json", ExperimentPlanDraftOutput),
    ("05-agent-output/examples/validation-report-fail.json", ValidationReport),
    ("05-agent-output/examples/validation-report-pass.json", ValidationReport),
    ("05-agent-output/examples/final-agent-payload.json", AgentResultPayload),
    ("02-java-python-agent/examples/internal-agent-turn.json", InternalAgentTurn),
    ("02-java-python-agent/examples/internal-stream-message.json", InternalStreamMessage),
]


@pytest.mark.parametrize("rel,model", CASES)
def test_example_validates(rel: str, model) -> None:
    path = CONTRACTS / rel
    if not path.exists():
        pytest.skip(f"example not shipped: {rel}")
    model.model_validate(_load(rel))
