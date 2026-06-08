"""Real-mode smoke: one full pipeline turn with tracing on.

Run from apps/agent with the repo-root .env present (GEMINI + PHOENIX keys):
    PYTHONPATH=. python scripts/smoke_real.py

Prints the resolved modes, processes one turn end-to-end, and reports the
emitted block summary + final approval payload. Exits non-zero on failure.
"""
from __future__ import annotations

import asyncio
import sys

from app.config import get_settings
from app.observability import init_tracing
from app.orchestrator import process_turn
from app.runtime.thread_store import ThreadStore


async def main() -> int:
    s = get_settings()
    print(f"llm={'gemini' if s.use_real_llm else 'stub'} "
          f"evidence={'elastic' if s.use_real_elastic else 'stub'} "
          f"tracing={'on' if s.phoenix_api_key else 'off'}")

    init_tracing()

    record = ThreadStore().get_or_create("thread_smoke01")
    record.set_context("demo_workspace", "camp_comeback_teaser")
    await process_turn(record, "What should we test next week?")

    all_blocks = [b for m in record.messages for b in m.blocks]
    kinds = {b["kind"] for b in all_blocks}
    print(f"messages={len(record.messages)} blocks={len(all_blocks)} kinds={sorted(kinds)}")

    approval = next((b for b in all_blocks if b["kind"] == "approval"), None)
    if approval:
        payload = approval["payload"]
        print(f"signals={len(payload['signals'])} "
              f"hypotheses={len(payload['hypotheses'])} "
              f"experiments={len(payload['experiment_plan']['items'])}")
        print("first experiment:", payload["experiment_plan"]["items"][0]["title"])

    error = next((b for b in all_blocks if b["kind"] == "error"), None)
    if error:
        print(f"error={error['detail']}")

    ok = approval is not None and error is None
    print("RESULT:", "OK" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
