"""Backtrack feedback: the root-cause worker is told why the review failed."""
import pytest

from app.agents import workers
from app.contracts import DateRange


def test_with_feedback_appends_review_failure():
    p = workers._with_feedback("base prompt", "signal sig_1 lift mismatch")
    assert p.startswith("base prompt")
    assert "FAILED deterministic review" in p
    assert "signal sig_1 lift mismatch" in p


def test_with_feedback_none_is_unchanged():
    assert workers._with_feedback("base", None) == "base"
    assert workers._with_feedback("base", "") == "base"


@pytest.mark.asyncio
async def test_stub_workers_accept_feedback():
    # Stub path ignores feedback but must accept the kwarg (orchestrator passes
    # it on every backtrack regardless of mode).
    r = DateRange(start="2026-06-04", end="2026-06-10")
    signals = (await workers.run_analyst("analyze", r, feedback="x")).signals
    hypotheses = (await workers.run_strategist("analyze", signals, feedback="x")).hypotheses
    plan = (await workers.run_writer("analyze", r, hypotheses, feedback="x")).experiment_plan
    assert signals and hypotheses and plan.items
