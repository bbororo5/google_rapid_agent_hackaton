"""Redis hot tier for the live ConversationState (ADR-005).

The live working copy of per-thread state lives here so a turn does not pay an
Elastic round-trip to read state. Elastic stays authoritative: this store is a
volatile cache and must always be reconstructable from `agent_thread_states` (or
the latest episode snapshot). On a Redis miss the caller rehydrates from the
runtime repository and re-populates the hot store.

Keyed by `thread_id` to mirror the Elastic `agent_thread_states` document id. The
resolved scope (workspace_id + campaign_id) is carried inside the stored state.

When `REDIS_URL` is unset the app falls back to an in-process store so the whole
service still runs offline, matching the existing real/stub gating pattern.
"""
from __future__ import annotations

from typing import Optional, Protocol

from app.config import get_settings
from app.runtime.state import ConversationState

_KEY_PREFIX = "lp:rt"
_DEFAULT_TTL_SECONDS = 60 * 60 * 24  # 24h, aligned with agent_thread_states retention


def _state_key(thread_id: str) -> str:
    return f"{_KEY_PREFIX}:{thread_id}:state"


class StateCache(Protocol):
    backend_name: str

    async def get_state(self, thread_id: str) -> ConversationState | None:
        ...

    async def put_state(self, thread_id: str, state: ConversationState) -> None:
        ...

    async def drop_state(self, thread_id: str) -> None:
        ...


class InMemoryHotStore:
    """Process-local fallback. Singleton so it survives across turns in tests."""

    backend_name = "memory"

    def __init__(self) -> None:
        self._states: dict[str, str] = {}

    async def get_state(self, thread_id: str) -> ConversationState | None:
        raw = self._states.get(thread_id)
        return ConversationState.model_validate_json(raw) if raw else None

    async def put_state(self, thread_id: str, state: ConversationState) -> None:
        # Store JSON so a returned object is never an aliased mutable reference.
        self._states[thread_id] = state.model_dump_json()

    async def drop_state(self, thread_id: str) -> None:
        self._states.pop(thread_id, None)


class RedisHotStore:
    backend_name = "redis"

    def __init__(self, url: str, ttl_seconds: int = _DEFAULT_TTL_SECONDS) -> None:
        # Lazy import so `redis` is only required when REDIS_URL is configured.
        from redis import asyncio as redis_asyncio

        self._client = redis_asyncio.from_url(url, decode_responses=True)
        self._ttl = ttl_seconds

    async def get_state(self, thread_id: str) -> ConversationState | None:
        raw = await self._client.get(_state_key(thread_id))
        return ConversationState.model_validate_json(raw) if raw else None

    async def put_state(self, thread_id: str, state: ConversationState) -> None:
        await self._client.set(_state_key(thread_id), state.model_dump_json(), ex=self._ttl)

    async def drop_state(self, thread_id: str) -> None:
        await self._client.delete(_state_key(thread_id))


_memory_state_cache = InMemoryHotStore()
_redis_state_cache: Optional[RedisHotStore] = None


def get_state_cache() -> StateCache:
    global _redis_state_cache
    settings = get_settings()
    if settings.use_redis and settings.redis_url:
        if _redis_state_cache is None:
            _redis_state_cache = RedisHotStore(settings.redis_url)
        return _redis_state_cache
    return _memory_state_cache
