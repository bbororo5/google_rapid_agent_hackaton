"""Golden path end-to-end in STUB mode (no LLM, no Elastic).

Drives the orchestrator like the turn API would and asserts the thread reaches
an approval block carrying a contract-valid payload, with contract-valid blocks.
"""
from __future__ import annotations

import pytest

from app import orchestrator
from app.contracts import AgentResultPayload, InternalStreamMessage, StreamRole
from app.runtime.thread_store import ThreadStore


def _blocks(record):
    return [b for m in record.messages for b in m.blocks]


@pytest.mark.asyncio
async def test_first_turn_reaches_approval() -> None:
    store = ThreadStore()
    record = store.get_or_create("thread_test123")
    record.set_context("demo_workspace", "camp_comeback_teaser")

    await orchestrator.process_turn(record, "What should we test next week?")

    # Sequence is monotonic from 1.
    seqs = [m.sequence for m in record.messages]
    assert seqs == list(range(1, len(seqs) + 1))

    # Every message is contract-valid.
    for m in record.messages:
        InternalStreamMessage.model_validate(m.model_dump(mode="json"))

    kinds = {b["kind"] for b in _blocks(record)}
    assert "activity" in kinds
    assert "artifact" in kinds
    assert "approval" in kinds

    # The approval block carries a contract-valid payload and a plan target.
    approval = next(b for b in _blocks(record) if b["kind"] == "approval")
    assert approval["target_id"].startswith("plan_")
    payload = AgentResultPayload.model_validate(approval["payload"])
    assert payload.signals
    assert payload.hypotheses
    assert payload.experiment_plan.items


@pytest.mark.asyncio
async def test_second_turn_is_free_chat() -> None:
    store = ThreadStore()
    record = store.get_or_create("thread_test456")
    record.set_context("demo_workspace", "camp_comeback_teaser")  # data present -> analyze

    await orchestrator.process_turn(record, "Find the signal.")
    first_count = len(record.messages)
    await orchestrator.process_turn(record, "고마워, 다른 건 없어?")

    # The follow-up turn adds a single assistant text reply (no new pipeline).
    extra = record.messages[first_count:]
    assert len(extra) == 1
    assert extra[0].role == StreamRole.assistant
    assert extra[0].blocks[0]["kind"] == "text"
    assert not any(b["kind"] == "approval" for b in extra[0].blocks)


@pytest.mark.asyncio
async def test_chat_without_data_steers_to_csv() -> None:
    store = ThreadStore()
    record = store.get_or_create("thread_chat1")

    # No data, no analysis keyword -> chat reply that steers to uploading a CSV.
    await orchestrator.process_turn(record, "안녕하세요")

    assert len(record.messages) == 1
    block = record.messages[0].blocks[0]
    assert block["kind"] == "text"
    assert "CSV" in block["text"]
    assert not record.pipeline_started  # chat must not start the pipeline


@pytest.mark.asyncio
async def test_analyze_without_csv_runs_pipeline_on_baseline() -> None:
    store = ThreadStore()
    record = store.get_or_create("thread_chat2")

    # CSV is new data; with no fresh upload, analysis still runs on the existing
    # baseline data already in Elastic.
    await orchestrator.process_turn(record, "분석해줘")

    assert record.pipeline_started
    assert any(
        b["kind"] == "approval" for m in record.messages for b in m.blocks
    )


@pytest.mark.asyncio
async def test_cancel_between_stages() -> None:
    store = ThreadStore()
    record = store.get_or_create("thread_cancel")
    record.set_context("demo_workspace", "camp_comeback_teaser")  # data present -> analyze
    record.cancelled = True

    await orchestrator.process_turn(record, "Analyze this.")

    # A cancel before the first stage yields a single system result block.
    assert len(record.messages) == 1
    assert record.messages[0].role == StreamRole.system
    assert record.messages[0].blocks[0]["kind"] == "result"
