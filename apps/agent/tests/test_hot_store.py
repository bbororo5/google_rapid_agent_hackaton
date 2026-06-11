"""Phase 1 (ADR-005): Redis hot tier for live SharedStateVector.

Covers the in-process fallback store and the turn-load wiring: a hot hit must
avoid the Elastic read, and a hot miss must rehydrate from the repository and
repopulate the hot store.
"""
from __future__ import annotations

from app.orchestration.context import LoadPersistedState
from app.orchestration.emitter import StreamEmitter
from app.orchestration.models import TurnContext
from app.runtime.hot_store import InMemoryHotStore, get_hot_store
from app.runtime.state import PhaseType, ScopeContext, SharedStateVector
from app.runtime.thread_store import ThreadRecord


def _state(thread_id: str, revision: int) -> SharedStateVector:
    return SharedStateVector(
        scope=ScopeContext(workspace_id="demo_workspace", campaign_id="camp_1", thread_id=thread_id),
        current_phase=PhaseType.HYPOTHESIS_GEN,
        revision=revision,
    )


class _CountingRepo:
    backend_name = "counting"

    def __init__(self, state: SharedStateVector | None) -> None:
        self._state = state
        self.load_calls = 0

    async def load_state(self, thread_id: str) -> SharedStateVector | None:
        self.load_calls += 1
        return self._state


async def test_in_memory_hot_store_roundtrip() -> None:
    hot = InMemoryHotStore()
    assert await hot.get_state("t1") is None
    await hot.put_state("t1", _state("t1", 3))
    loaded = await hot.get_state("t1")
    assert loaded is not None and loaded.revision == 3
    await hot.drop_state("t1")
    assert await hot.get_state("t1") is None


async def test_in_memory_hot_store_returns_isolated_copies() -> None:
    hot = InMemoryHotStore()
    await hot.put_state("t1", _state("t1", 1))
    first = await hot.get_state("t1")
    first.revision = 99  # mutating the returned object must not affect the store
    second = await hot.get_state("t1")
    assert second.revision == 1


def test_get_hot_store_defaults_to_memory_without_redis_url() -> None:
    # No REDIS_URL in the test environment => in-process fallback.
    assert get_hot_store().backend_name == "memory"


async def test_load_prefers_hot_and_skips_elastic_on_hit() -> None:
    hot = InMemoryHotStore()
    await hot.put_state("thread_001", _state("thread_001", 7))
    repo = _CountingRepo(state=_state("thread_001", 0))
    record = ThreadRecord(thread_id="thread_001")
    turn = TurnContext(record=record, content="hi", attachments=(), repository=repo, hot_store=hot)

    await LoadPersistedState(StreamEmitter()).apply(turn)

    assert record.state.revision == 7
    assert repo.load_calls == 0  # hot hit: no Elastic round-trip
    assert turn.expected_revision == 7


async def test_load_miss_rehydrates_from_repo_and_populates_hot() -> None:
    hot = InMemoryHotStore()
    repo = _CountingRepo(state=_state("thread_002", 4))
    record = ThreadRecord(thread_id="thread_002")
    turn = TurnContext(record=record, content="hi", attachments=(), repository=repo, hot_store=hot)

    await LoadPersistedState(StreamEmitter()).apply(turn)

    assert record.state.revision == 4
    assert repo.load_calls == 1  # miss: one Elastic read
    rehydrated = await hot.get_state("thread_002")
    assert rehydrated is not None and rehydrated.revision == 4  # hot repopulated
