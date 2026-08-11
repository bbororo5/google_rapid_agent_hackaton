"""Public collection and retrieval messages owned by the performance module."""

from launchpilot.shared import PlatformProvider

from .catalog import (
    AdvertisingCatalogService,
    ListAdvertisingAccounts,
    ListAdvertisingCampaigns,
)
from .contracts import (
    CampaignMetricRequest,
    ConnectorFetchResult,
    ExternalAccount,
    ExternalCampaign,
)
from .ingestion import (
    AdsConnectorUnavailable,
    AdsIngestionSourcePlanner,
    AllSourcesFailedError,
    IngestionOutcome,
    MultiPlatformIngestionService,
    PlatformAccess,
    PlatformAccessError,
    PlatformAccessUnavailable,
    PlatformAuthorizationExpired,
    PlatformConnectionNotFound,
    PlatformProviderMismatch,
    PlatformTokenRefreshFailed,
    PlatformTokenUnavailable,
    UnsupportedAdsProvider,
)
from .models import CampaignObservation
from .observation_service import ObservationService
from .ports import AdsConnector
from .retrieval import (
    CampaignMetricQuery,
    CampaignPerformance,
    StructuredRetrievalService,
)

__all__ = [
    "AdsConnector",
    "AdsConnectorUnavailable",
    "AdsIngestionSourcePlanner",
    "AdvertisingCatalogService",
    "AllSourcesFailedError",
    "CampaignMetricQuery",
    "CampaignMetricRequest",
    "CampaignObservation",
    "CampaignPerformance",
    "ConnectorFetchResult",
    "ExternalAccount",
    "ExternalCampaign",
    "IngestionOutcome",
    "ListAdvertisingAccounts",
    "ListAdvertisingCampaigns",
    "MultiPlatformIngestionService",
    "ObservationService",
    "PlatformAccess",
    "PlatformAccessError",
    "PlatformAccessUnavailable",
    "PlatformAuthorizationExpired",
    "PlatformConnectionNotFound",
    "PlatformProvider",
    "PlatformProviderMismatch",
    "PlatformTokenRefreshFailed",
    "PlatformTokenUnavailable",
    "StructuredRetrievalService",
    "UnsupportedAdsProvider",
]
