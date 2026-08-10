from functools import lru_cache

from langchain_core.language_models import BaseChatModel
from langchain_google_genai import ChatGoogleGenerativeAI

from launchpilot.application.retrieval import StructuredRetrievalService
from launchpilot.application.services import (
    CampaignService,
    ConversationService,
    ObservationService,
)
from launchpilot.application.text_retrieval import TextRetrievalService
from launchpilot.config import Settings
from launchpilot.infrastructure.control_plane import PostgresControlPlane
from launchpilot.infrastructure.elasticsearch_documents import (
    ElasticsearchCampaignDocumentSearch,
)
from launchpilot.infrastructure.google_oauth import GoogleOAuthClient
from launchpilot.infrastructure.meta_oauth import MetaOAuthClient
from launchpilot.infrastructure.postgres_database import PostgresDatabase
from launchpilot.infrastructure.postgres_documents import (
    PostgresCampaignDocumentRepository,
)
from launchpilot.infrastructure.postgres_domain import (
    PostgresCampaignRepository,
    PostgresConversationRepository,
    PostgresObservationRepository,
)
from launchpilot.infrastructure.postgres_retrieval import (
    PostgresStructuredRetrievalRepository,
)
from launchpilot.infrastructure.security import (
    BrowserStateManager,
    SessionManager,
    SignedTokenCodec,
)


@lru_cache
def repository_store() -> PostgresDatabase:
    return PostgresDatabase(settings().database_url)


def campaign_service() -> CampaignService:
    return CampaignService(PostgresCampaignRepository(repository_store()))


def conversation_service() -> ConversationService:
    database = repository_store()
    return ConversationService(
        PostgresCampaignRepository(database), PostgresConversationRepository(database)
    )


def observation_service() -> ObservationService:
    database = repository_store()
    return ObservationService(
        PostgresCampaignRepository(database), PostgresObservationRepository(database)
    )


def structured_retrieval_service() -> StructuredRetrievalService:
    return StructuredRetrievalService(
        PostgresStructuredRetrievalRepository(repository_store())
    )


def text_retrieval_service() -> TextRetrievalService:
    config = settings()
    return TextRetrievalService(
        PostgresCampaignDocumentRepository(repository_store()),
        ElasticsearchCampaignDocumentSearch(
            config.elasticsearch_url, config.elasticsearch_index
        ),
    )


@lru_cache
def agent_model() -> BaseChatModel:
    config = settings()
    try:
        config.require_google_ai()
    except RuntimeError as error:
        from fastapi import HTTPException, status

        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)
        ) from error
    model_options = {
        "model": config.llm_model,
        "max_retries": 2,
        "vertexai": config.google_genai_use_vertexai,
    }
    if config.google_genai_use_vertexai:
        model_options.update(
            project=config.google_cloud_project,
            location=config.google_cloud_location,
        )
    else:
        model_options["api_key"] = config.google_api_key
    return ChatGoogleGenerativeAI(**model_options)


@lru_cache
def settings() -> Settings:
    return Settings.from_environment()


@lru_cache
def control_plane() -> PostgresControlPlane:
    config = settings()
    return PostgresControlPlane(repository_store(), config.token_encryption_key)


def google_oauth_client() -> GoogleOAuthClient:
    config = settings()
    mock_base_url = config.platform_mock_base_url
    if not mock_base_url:
        try:
            config.require_google_oauth()
        except RuntimeError as error:
            from fastapi import HTTPException, status

            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)
            ) from error
    return GoogleOAuthClient(
        client_id="mock-google-client"
        if mock_base_url
        else config.google_client_id or "",
        client_secret=(
            "mock-google-secret" if mock_base_url else config.google_client_secret or ""
        ),
        public_base_url=config.public_base_url,
        authorize_url=(
            f"{mock_base_url}/google/o/oauth2/v2/auth"
            if mock_base_url
            else "https://accounts.google.com/o/oauth2/v2/auth"
        ),
        token_url=(
            f"{mock_base_url}/google/token"
            if mock_base_url
            else "https://oauth2.googleapis.com/token"
        ),
        userinfo_url=(
            f"{mock_base_url}/google/userinfo"
            if mock_base_url
            else "https://openidconnect.googleapis.com/v1/userinfo"
        ),
    )


def meta_oauth_client() -> MetaOAuthClient:
    config = settings()
    if config.platform_mock_base_url:
        app_id, app_secret = "mock-meta-app", "mock-meta-secret"
    else:
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
        authorize_base_url=(
            f"{config.platform_mock_base_url}/meta"
            if config.platform_mock_base_url
            else "https://www.facebook.com"
        ),
        graph_base_url=(
            f"{config.platform_mock_base_url}/meta"
            if config.platform_mock_base_url
            else "https://graph.facebook.com"
        ),
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
