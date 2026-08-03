from functools import lru_cache

from launchpilot.application.services import CampaignService, ConversationService, ObservationService
from launchpilot.infrastructure.in_memory import (
    InMemoryConversationRepository,
    InMemoryObservationRepository,
    InMemoryRepositories,
)


@lru_cache
def repository_store() -> InMemoryRepositories:
    return InMemoryRepositories()


def campaign_service() -> CampaignService:
    return CampaignService(repository_store())


def conversation_service() -> ConversationService:
    store = repository_store()
    return ConversationService(store, InMemoryConversationRepository(store))


def observation_service() -> ObservationService:
    store = repository_store()
    return ObservationService(store, InMemoryObservationRepository(store))

