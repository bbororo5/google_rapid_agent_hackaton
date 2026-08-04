from functools import lru_cache

from launchpilot.application.services import (
    CampaignService,
    ConversationService,
    ObservationService,
)
from launchpilot.config import Settings
from launchpilot.infrastructure.control_plane import SqliteControlPlane
from launchpilot.infrastructure.google_oauth import GoogleOAuthClient
from launchpilot.infrastructure.meta_oauth import MetaOAuthClient
from launchpilot.infrastructure.security import (
    BrowserStateManager,
    SessionManager,
    SignedTokenCodec,
)
from launchpilot.infrastructure.sqlite_domain import (
    SqliteCampaignRepository,
    SqliteConversationRepository,
    SqliteDomainDatabase,
    SqliteObservationRepository,
)


@lru_cache
def repository_store() -> SqliteDomainDatabase:
    return SqliteDomainDatabase(settings().database_path)


def campaign_service() -> CampaignService:
    return CampaignService(SqliteCampaignRepository(repository_store()))


def conversation_service() -> ConversationService:
    database = repository_store()
    return ConversationService(
        SqliteCampaignRepository(database), SqliteConversationRepository(database)
    )


def observation_service() -> ObservationService:
    database = repository_store()
    return ObservationService(
        SqliteCampaignRepository(database), SqliteObservationRepository(database)
    )


@lru_cache
def settings() -> Settings:
    return Settings.from_environment()


@lru_cache
def control_plane() -> SqliteControlPlane:
    config = settings()
    return SqliteControlPlane(config.database_path, config.token_encryption_key)


def google_oauth_client() -> GoogleOAuthClient:
    config = settings()
    try:
        config.require_google_oauth()
    except RuntimeError as error:
        from fastapi import HTTPException, status

        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)
        ) from error
    return GoogleOAuthClient(
        client_id=config.google_client_id or "",
        client_secret=config.google_client_secret or "",
        public_base_url=config.public_base_url,
    )


def meta_oauth_client() -> MetaOAuthClient:
    config = settings()
    try:
        app_id, app_secret = config.require_meta_oauth()
    except RuntimeError as error:
        from fastapi import HTTPException, status

        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)
        ) from error
    return MetaOAuthClient(
        app_id=app_id,
        app_secret=app_secret,
        public_base_url=config.public_base_url,
        api_version=config.meta_graph_api_version,
    )


def signed_token_codec() -> SignedTokenCodec:
    config = settings()
    try:
        secret = config.require_session_secret()
    except RuntimeError as error:
        from fastapi import HTTPException, status

        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)
        ) from error
    return SignedTokenCodec(secret)


def browser_state_manager() -> BrowserStateManager:
    return BrowserStateManager(signed_token_codec())


def session_manager() -> SessionManager:
    return SessionManager(signed_token_codec())
