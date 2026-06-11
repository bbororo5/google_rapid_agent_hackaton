"""Real-mode smoke: one analysis round with tracing on.

Run from apps/agent with the repo-root .env present (GEMINI + PHOENIX keys):
    PYTHONPATH=. python scripts/smoke_real.py

Prints the resolved modes, processes one analysis request, and reports emitted
block kinds plus signal artifact count. Exits non-zero on failure.
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
    print(f"llm={'gemini' if s.use_real_llm else 'missing'} "
          f"evidence={'elastic' if s.use_real_elastic else 'missing'} "
          f"tracing={'on' if s.phoenix_api_key else 'off'}")

    init_tracing()

    record = ThreadStore().get_or_create("thread_smoke01")
    record.set_context("demo_workspace", "camp_comeback_teaser")
    await process_turn(record, "Analyze this campaign's recent metrics.")

    all_blocks = [b for m in record.messages for b in m.blocks]
    kinds = {b["kind"] for b in all_blocks}
    print(f"messages={len(record.messages)} blocks={len(all_blocks)} kinds={sorted(kinds)}")

    signals = [b for b in all_blocks if b.get("kind") == "artifact" and b.get("artifactKind") == "signal"]
    print(f"signal_artifacts={len(signals)}")

    error = next((b for b in all_blocks if b["kind"] == "error"), None)
    if error:
        print(f"error={error['detail']}")

    ok = bool(signals) and error is None
    print("RESULT:", "OK" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
