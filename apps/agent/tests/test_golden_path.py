"""Golden scenario tests for the Orchestrator Component.

These tests intentionally verify observable full-path outcomes instead of
fine-grained reducer/repository internals. Behavioral quality and drift are
tracked through Phoenix traces and ADK eval scenarios.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from app import orchestrator
from app.contracts import AgentResultPayload, InternalStreamMessage
from app.runtime.thread_store import ThreadStore


SCENARIOS = Path(__file__).parents[1] / "app/eval/dataset/scenarios.json"


def _load_scenarios() -> list[dict[str, Any]]:
    return json.loads(SCENARIOS.read_text())


def _blocks(record):
    return [block for message in record.messages for block in message.blocks]


def _blocks_since(record, index: int):
    return [block for message in record.messages[index:] for block in message.blocks]


def _kinds(blocks):
    return [block["kind"] for block in blocks]


@pytest.mark.asyncio
@pytest.mark.parametrize("scenario", _load_scenarios(), ids=lambda item: item["id"])
async def test_golden_orchestrator_scenarios(scenario: dict[str, Any]) -> None:
    store = ThreadStore()
    record = store.get_or_create(f"thread_{scenario['id']}")
    record.set_context(scenario.get("workspace_id"), scenario.get("campaign_id"))

    turn_boundaries: list[int] = []
    for turn in scenario["turns"]:
        turn_boundaries.append(len(record.messages))
        await orchestrator.process_turn(record, turn)

    for message in record.messages:
        InternalStreamMessage.model_validate(message.model_dump(mode="json"))

    expected = scenario["expected"]
    all_blocks = _blocks(record)
    final_block = all_blocks[-1]

    if expected.get("final_block"):
        assert final_block["kind"] == expected["final_block"]

    if expected.get("requires_artifact"):
        assert any(block["kind"] == "artifact" for block in all_blocks)

    if expected.get("retryable") is not None:
        assert final_block["retryable"] is expected["retryable"]

    if expected.get("second_turn_blocks") is not None:
        second_blocks = _blocks_since(record, turn_boundaries[1])
        assert _kinds(second_blocks) == expected["second_turn_blocks"]

    if expected.get("second_turn_excludes"):
        second_kinds = set(_kinds(_blocks_since(record, turn_boundaries[1])))
        assert not second_kinds.intersection(expected["second_turn_excludes"])

    if expected.get("reply_contains"):
        second_blocks = _blocks_since(record, turn_boundaries[1])
        assert expected["reply_contains"] in second_blocks[-1]["text"]

    if expected.get("second_turn_includes"):
        second_kinds = set(_kinds(_blocks_since(record, turn_boundaries[1])))
        assert set(expected["second_turn_includes"]).issubset(second_kinds)

    if expected.get("requires_new_plan"):
        first_blocks = _blocks_since(record, turn_boundaries[0])
        second_blocks = _blocks_since(record, turn_boundaries[1])
        first_plan = next(block for block in first_blocks if block["kind"] == "approval")["target_id"]
        second_plan = next(block for block in second_blocks if block["kind"] == "approval")["target_id"]
        assert second_plan != first_plan

    approval_blocks = [block for block in all_blocks if block["kind"] == "approval"]
    for block in approval_blocks:
        AgentResultPayload.model_validate(block["payload"])
