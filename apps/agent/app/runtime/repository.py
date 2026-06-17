"""Agent runtime repository.

Business documents stay in contract 03 and are owned by Java. This repository is
Python Agent Core runtime coordination only: state snapshots, delta logs,
runtime-only artifacts, and read-only conversation memory.
"""
from __future__ import annotations

import time
import uuid
from typing import Any, Protocol

import httpx
from pydantic import BaseModel, Field

from app.config import get_settings
from app.runtime.episode import Episode, EpisodeOutcome
from app.runtime.state import ScopeContext, ConversationState, ProposedChange


class RepositoryConflict(RuntimeError):
    """Raised when optimistic concurrency detects a stale state write."""


class CampaignContext(BaseModel):
    workspace_id: str
    campaign_id: str
    name: str | None = None
    summary: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RuntimeArtifact(BaseModel):
    artifact_id: str = Field(default_factory=lambda: f"runtime_art_{uuid.uuid4().hex[:12]}")
    artifact_type: str
    phase: str
    payload: dict[str, Any]
    runtime_only: bool = True
    ttl_seconds: int = 60 * 60 * 24
    created_at: float = Field(default_factory=time.time)


class ChangeLogEntry(BaseModel):
    delta_id: str = Field(default_factory=lambda: f"delta_{uuid.uuid4().hex[:12]}")
    scope: ScopeContext
    proposal: ProposedChange
    reducer_decision: dict[str, Any]
    created_at: float = Field(default_factory=time.time)


class ThreadMessage(BaseModel):
    role: str
    content: str
    created_at: float = Field(default_factory=time.time)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentRuntimeRepository(Protocol):
    backend_name: str

    async def load_state(self, thread_id: str) -> ConversationState | None:
        ...

    async def create_or_load_state(self, scope: ScopeContext) -> ConversationState:
        ...

    async def commit_state(
        self,
        expected_revision: int,
        new_state: ConversationState,
        delta_event: ChangeLogEntry,
    ) -> None:
        ...

    async def load_campaign_context(self, scope: ScopeContext) -> CampaignContext | None:
        ...

    async def load_recent_messages(self, scope: ScopeContext, limit: int) -> list[ThreadMessage]:
        ...

    async def save_runtime_artifact(self, scope: ScopeContext, artifact: RuntimeArtifact) -> str:
        ...

    async def load_runtime_artifacts(self, refs: list[str]) -> list[RuntimeArtifact]:
        ...

    async def save_episode(self, episode: Episode) -> str:
        ...

    async def query_episodes(
        self,
        scope: ScopeContext,
        *,
        phase: str | None = None,
        outcome: EpisodeOutcome | None = None,
        run_id: str | None = None,
        limit: int = 5,
    ) -> list[Episode]:
        ...

    async def get_episode(self, episode_id: str) -> Episode | None:
        ...


class InMemoryAgentRuntimeRepository:
    backend_name = "memory"

    def __init__(self) -> None:
        self._states: dict[str, ConversationState] = {}
        self._deltas: list[ChangeLogEntry] = []
        self._artifacts: dict[str, RuntimeArtifact] = {}
        self._messages: dict[tuple[str, str, str], list[ThreadMessage]] = {}
        self._campaigns: dict[tuple[str, str], CampaignContext] = {}
        self._episodes: list[Episode] = []

    async def load_state(self, thread_id: str) -> ConversationState | None:
        state = self._states.get(thread_id)
        return state.model_copy(deep=True) if state else None

    async def create_or_load_state(self, scope: ScopeContext) -> ConversationState:
        existing = self._states.get(scope.thread_id)
        if existing:
            state = existing.model_copy(deep=True)
            state.scope = state.scope or scope
            return state
        state = ConversationState(scope=scope)
        self._states[scope.thread_id] = state.model_copy(deep=True)
        return state

    async def commit_state(
        self,
        expected_revision: int,
        new_state: ConversationState,
        delta_event: ChangeLogEntry,
    ) -> None:
        current = self._states.get(delta_event.scope.thread_id)
        current_revision = current.revision if current else 0
        if current_revision != expected_revision:
            raise RepositoryConflict(
                f"stale revision: expected {expected_revision}, current {current_revision}"
            )
        self._states[delta_event.scope.thread_id] = new_state.model_copy(deep=True)
        self._deltas.append(delta_event)

    async def load_campaign_context(self, scope: ScopeContext) -> CampaignContext | None:
        return self._campaigns.get((scope.workspace_id, scope.campaign_id)) or CampaignContext(
            workspace_id=scope.workspace_id,
            campaign_id=scope.campaign_id,
            summary="Local fallback campaign context.",
        )

    async def load_recent_messages(self, scope: ScopeContext, limit: int) -> list[ThreadMessage]:
        key = (scope.workspace_id, scope.campaign_id, scope.thread_id)
        return self._messages.get(key, [])[-limit:]

    async def save_runtime_artifact(self, scope: ScopeContext, artifact: RuntimeArtifact) -> str:
        self._artifacts[artifact.artifact_id] = artifact
        return artifact.artifact_id

    async def load_runtime_artifacts(self, refs: list[str]) -> list[RuntimeArtifact]:
        return [self._artifacts[ref] for ref in refs if ref in self._artifacts]

    async def save_episode(self, episode: Episode) -> str:
        self._episodes.append(episode.model_copy(deep=True))
        return episode.episode_id

    async def query_episodes(
        self,
        scope: ScopeContext,
        *,
        phase: str | None = None,
        outcome: EpisodeOutcome | None = None,
        run_id: str | None = None,
        limit: int = 5,
    ) -> list[Episode]:
        matched = [
            ep
            for ep in self._episodes
            if ep.workspace_id == scope.workspace_id
            and ep.campaign_id == scope.campaign_id
            and (phase is None or ep.phase.value == phase)
            and (outcome is None or ep.outcome == outcome)
            and (run_id is None or ep.run_id == run_id)
        ]
        matched.sort(key=lambda ep: ep.created_at, reverse=True)
        return [ep.model_copy(deep=True) for ep in matched[:limit]]

    async def get_episode(self, episode_id: str) -> Episode | None:
        for ep in self._episodes:
            if ep.episode_id == episode_id:
                return ep.model_copy(deep=True)
        return None

    def set_messages_for_local_test(self, scope: ScopeContext, messages: list[ThreadMessage]) -> None:
        self._messages[(scope.workspace_id, scope.campaign_id, scope.thread_id)] = messages


class ElasticAgentRuntimeRepository:
    backend_name = "elastic"

    state_index = "agent_thread_states"
    delta_index = "agent_state_deltas"
    artifact_index = "agent_runtime_artifacts"
    message_index = "agent_thread_messages"
    episode_index = "agent_episodes"
    campaign_index = "campaigns"

    def __init__(self, url: str, api_key: str) -> None:
        self._url = url.rstrip("/")
        self._headers = {"Authorization": f"ApiKey {api_key}"}

    async def load_state(self, thread_id: str) -> ConversationState | None:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{self._url}/{self.state_index}/_doc/{thread_id}",
                headers=self._headers,
            )
        if response.status_code == 404:
            return None
        response.raise_for_status()
        source = response.json().get("_source", {})
        return ConversationState.model_validate(source["state"])

    async def create_or_load_state(self, scope: ScopeContext) -> ConversationState:
        existing = await self.load_state(scope.thread_id)
        if existing:
            existing.scope = existing.scope or scope
            return existing
        return ConversationState(scope=scope)

    async def commit_state(
        self,
        expected_revision: int,
        new_state: ConversationState,
        delta_event: ChangeLogEntry,
    ) -> None:
        # 1) 저장할 상태 문서를 조립한다.
        doc = {
            "thread_id": delta_event.scope.thread_id,
            "workspace_id": delta_event.scope.workspace_id,
            "campaign_id": delta_event.scope.campaign_id,
            "revision": new_state.revision,
            "state": new_state.model_dump(mode="json"),
            "updated_at": time.time(),
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            # 2) 같은 thread의 현재 문서를 먼저 읽는다 (남이 먼저 바꿨는지 확인용).
            current = await client.get(
                f"{self._url}/{self.state_index}/_doc/{delta_event.scope.thread_id}",
                headers=self._headers,
            )
            if current.status_code == 404:
                # 2-a) 문서가 아직 없음 = 첫 저장. 그렇다면 revision은 0이어야 맞다.
                if expected_revision != 0:
                    raise RepositoryConflict("missing state for non-zero revision")
                state_response = await client.put(
                    f"{self._url}/{self.state_index}/_doc/{delta_event.scope.thread_id}?op_type=create",
                    headers=self._headers,
                    json=doc,
                )
            else:
                # 2-b) 이미 있음 = 내가 본 revision과 같을 때만 덮어쓴다.
                #      (그 사이 다른 턴이 먼저 갱신했으면 revision이 달라 충돌)
                current.raise_for_status()
                body = current.json()
                source = body.get("_source", {})
                if source.get("revision") != expected_revision:
                    raise RepositoryConflict(
                        f"stale revision: expected {expected_revision}, current {source.get('revision')}"
                    )
                # if_seq_no/if_primary_term = Elastic의 "내가 읽은 그 버전일 때만 써라" 잠금.
                state_response = await client.put(
                    (
                        f"{self._url}/{self.state_index}/_doc/{delta_event.scope.thread_id}"
                        f"?if_seq_no={body['_seq_no']}&if_primary_term={body['_primary_term']}"
                    ),
                    headers=self._headers,
                    json=doc,
                )
            # 3) 쓰는 순간 다른 턴이 끼어들었으면(409) 충돌로 처리한다.
            if state_response.status_code == 409:
                raise RepositoryConflict("elastic optimistic concurrency conflict")
            state_response.raise_for_status()
            # 4) 마지막으로 변경 이력(delta)을 별도 인덱스에 남긴다.
            delta_response = await client.put(
                f"{self._url}/{self.delta_index}/_doc/{delta_event.delta_id}",
                headers=self._headers,
                json=delta_event.model_dump(mode="json"),
            )
            delta_response.raise_for_status()

    async def load_campaign_context(self, scope: ScopeContext) -> CampaignContext | None:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{self._url}/{self.campaign_index}/_doc/{scope.campaign_id}",
                headers=self._headers,
            )
        if response.status_code == 404:
            return None
        response.raise_for_status()
        source = response.json().get("_source", {})
        if source.get("workspace_id") != scope.workspace_id:
            return None
        return CampaignContext(
            workspace_id=source["workspace_id"],
            campaign_id=source["campaign_id"],
            name=source.get("name"),
            summary=source.get("summary"),
            metadata={k: v for k, v in source.items() if k not in {"workspace_id", "campaign_id", "name", "summary"}},
        )

    async def load_recent_messages(self, scope: ScopeContext, limit: int) -> list[ThreadMessage]:
        query = {
            "size": limit,
            "sort": [{"created_at": {"order": "desc"}}],
            "query": {
                "bool": {
                    "filter": [
                        {"term": {"workspace_id": scope.workspace_id}},
                        {"term": {"campaign_id": scope.campaign_id}},
                        {"term": {"thread_id": scope.thread_id}},
                    ]
                }
            },
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{self._url}/{self.message_index}/_search",
                headers=self._headers,
                json=query,
            )
        if response.status_code == 404:
            return []
        response.raise_for_status()
        hits = response.json().get("hits", {}).get("hits", [])
        return [
            ThreadMessage(
                role=hit["_source"].get("role", "user"),
                content=hit["_source"].get("content", ""),
                created_at=hit["_source"].get("created_at", time.time()),
                metadata=hit["_source"].get("metadata", {}),
            )
            for hit in reversed(hits)
        ]

    async def save_runtime_artifact(self, scope: ScopeContext, artifact: RuntimeArtifact) -> str:
        doc = {
            **artifact.model_dump(mode="json"),
            "workspace_id": scope.workspace_id,
            "campaign_id": scope.campaign_id,
            "thread_id": scope.thread_id,
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.put(
                f"{self._url}/{self.artifact_index}/_doc/{artifact.artifact_id}",
                headers=self._headers,
                json=doc,
            )
        response.raise_for_status()
        return artifact.artifact_id

    async def load_runtime_artifacts(self, refs: list[str]) -> list[RuntimeArtifact]:
        if not refs:
            return []
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{self._url}/{self.artifact_index}/_mget",
                headers=self._headers,
                json={"ids": refs},
            )
        response.raise_for_status()
        docs = response.json().get("docs", [])
        return [
            RuntimeArtifact.model_validate(doc["_source"])
            for doc in docs
            if doc.get("found")
        ]

    async def save_episode(self, episode: Episode) -> str:
        # Interim writer (ADR-005 C4 target is Java): Python writes agent_episodes
        # directly, consistent with the other runtime indices above. Migration to
        # a Java writer is non-breaking (same schema) and tracked as Phase 5.
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.put(
                f"{self._url}/{self.episode_index}/_doc/{episode.episode_id}",
                headers=self._headers,
                json=episode.model_dump(mode="json"),
            )
        response.raise_for_status()
        return episode.episode_id

    async def query_episodes(
        self,
        scope: ScopeContext,
        *,
        phase: str | None = None,
        outcome: EpisodeOutcome | None = None,
        run_id: str | None = None,
        limit: int = 5,
    ) -> list[Episode]:
        # MVP retrieval (ADR-005 C6): hard filter + recency. Hybrid kNN + summary
        # is deferred; the embedding field is reserved on the document.
        filters: list[dict[str, Any]] = [
            {"term": {"workspace_id": scope.workspace_id}},
            {"term": {"campaign_id": scope.campaign_id}},
        ]
        if phase is not None:
            filters.append({"term": {"phase": phase}})
        if outcome is not None:
            filters.append({"term": {"outcome": outcome.value}})
        if run_id is not None:
            filters.append({"term": {"run_id": run_id}})
        query = {
            "size": limit,
            "sort": [{"created_at": {"order": "desc"}}],
            "query": {"bool": {"filter": filters}},
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{self._url}/{self.episode_index}/_search",
                headers=self._headers,
                json=query,
            )
        if response.status_code == 404:
            return []
        response.raise_for_status()
        hits = response.json().get("hits", {}).get("hits", [])
        return [Episode.model_validate(hit["_source"]) for hit in hits]

    async def get_episode(self, episode_id: str) -> Episode | None:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{self._url}/{self.episode_index}/_doc/{episode_id}",
                headers=self._headers,
            )
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return Episode.model_validate(response.json().get("_source", {}))


_memory_repository = InMemoryAgentRuntimeRepository()


def get_runtime_repository() -> AgentRuntimeRepository:
    settings = get_settings()
    if settings.use_real_elastic and settings.elastic_url and settings.elastic_api_key:
        return ElasticAgentRuntimeRepository(settings.elastic_url, settings.elastic_api_key)
    return _memory_repository
