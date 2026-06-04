"""Real-mode smoke: one full pipeline run with tracing on.

Run from apps/agent with the repo-root .env present (GEMINI + PHOENIX keys):
    PYTHONPATH=. python scripts/smoke_real.py

Prints the resolved modes, runs the orchestrator end-to-end, and reports the
final status + payload summary. Exits non-zero on failure.
"""
from __future__ import annotations

import asyncio
import sys

from app.config import get_settings
from app.contracts import DateRange, InternalAgentRunRequest, TraceContext
from app.observability import init_tracing
from app.orchestrator import execute
from app.runtime.store import RunStore


async def main() -> int:
    s = get_settings()
    print(f"llm={'gemini' if s.use_real_llm else 'stub'} "
          f"evidence={'elastic' if s.use_real_elastic else 'stub'} "
          f"tracing={'on' if s.phoenix_api_key else 'off'}")

    init_tracing()

    req = InternalAgentRunRequest(
        agent_run_id="run_smoke01",
        workspace_id="demo_workspace",
        campaign_id="camp_comeback_teaser",
        question="What should we test next week?",
        date_range=DateRange(start="2026-05-25", end="2026-05-31"),
        trace_context=TraceContext(request_id="req_smoke", source="java-backend"),
    )
    record = RunStore().create(req)
    await execute(record)

    print(f"status={record.status.value} validator_passed={record.validator_passed} "
          f"backtracks={record.backtrack_count}")
    if record.error_message:
        print(f"error={record.error_message}")
    if record.payload:
        print(f"signals={len(record.payload.signals)} "
              f"hypotheses={len(record.payload.hypotheses)} "
              f"experiments={len(record.payload.experiment_plan.items)}")
        print("first experiment:", record.payload.experiment_plan.items[0].title)

    ok = record.status.value == "WAITING_FOR_APPROVAL"
    print("RESULT:", "OK" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
