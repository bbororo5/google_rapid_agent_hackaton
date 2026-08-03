from __future__ import annotations

from threading import RLock
from uuid import UUID

from launchpilot.domain.models import Campaign, CampaignObservation, Conversation


class InMemoryRepositories:
    """Phase 1 adapter: process-local storage behind application repository ports."""

    def __init__(self) -> None:
        self._campaigns: dict[UUID, Campaign] = {}
        self._conversations: dict[UUID, Conversation] = {}
        self._observations: dict[UUID, CampaignObservation] = {}
        self._lock = RLock()

    def add(self, entity: Campaign | Conversation | CampaignObservation) -> None:
        with self._lock:
            if isinstance(entity, Campaign):
                self._campaigns[entity.id] = entity
            elif isinstance(entity, Conversation):
                self._conversations[entity.id] = entity
            else:
                self._observations[entity.id] = entity

    def get(self, campaign_id: UUID) -> Campaign | None:
        with self._lock:
            return self._campaigns.get(campaign_id)

    def list(self) -> list[Campaign]:
        with self._lock:
            return sorted(self._campaigns.values(), key=lambda item: item.created_at)

    def list_by_campaign(self, campaign_id: UUID) -> list[Conversation] | list[CampaignObservation]:
        with self._lock:
            conversations = [item for item in self._conversations.values() if item.campaign_id == campaign_id]
            observations = [item for item in self._observations.values() if item.campaign_id == campaign_id]
            # The port used decides the expected item type. This adapter shares one store deliberately.
            return sorted(conversations or observations, key=lambda item: item.created_at if hasattr(item, "created_at") else item.captured_at)


class InMemoryConversationRepository:
    def __init__(self, store: InMemoryRepositories) -> None:
        self._store = store

    def add(self, conversation: Conversation) -> None:
        self._store.add(conversation)

    def list_by_campaign(self, campaign_id: UUID) -> list[Conversation]:
        with self._store._lock:
            return sorted(
                (item for item in self._store._conversations.values() if item.campaign_id == campaign_id),
                key=lambda item: item.created_at,
            )


class InMemoryObservationRepository:
    def __init__(self, store: InMemoryRepositories) -> None:
        self._store = store

    def add(self, observation: CampaignObservation) -> None:
        self._store.add(observation)

    def list_by_campaign(self, campaign_id: UUID) -> list[CampaignObservation]:
        with self._store._lock:
            return sorted(
                (item for item in self._store._observations.values() if item.campaign_id == campaign_id),
                key=lambda item: item.captured_at,
            )
