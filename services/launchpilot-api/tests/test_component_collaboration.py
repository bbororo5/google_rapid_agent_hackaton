from __future__ import annotations

import inspect
from typing import get_type_hints

from launchpilot.analysis.agent import CampaignAgent
from launchpilot.analysis.use_case import CampaignAnalysisService
from launchpilot.campaigns.application.access import CampaignAccessService
from launchpilot.identity.access_tokens import PlatformAccessTokenProvider
from launchpilot.knowledge.service import TextRetrievalService
from launchpilot.performance.catalog import AdvertisingCatalogService
from launchpilot.performance.ingestion import (
    AdsIngestionSourcePlanner,
    MultiPlatformIngestionService,
)
from launchpilot.performance.observation_service import ObservationService
from launchpilot.performance.retrieval import StructuredRetrievalService

COMPONENT_ROLES = {
    CampaignAccessService: {
        "campaigns": "CampaignReader",
        "workspace_access": "WorkspaceAccessReader",
    },
    CampaignAnalysisService: {
        "access": "CampaignScopeResolver",
        "agents": "CampaignAnswererFactory",
    },
    CampaignAgent: {
        "graph": "AnalysisWorkflow",
        "evidence_collector": "EvidenceReader",
    },
    PlatformAccessTokenProvider: {
        "store": "PlatformConnectionStore",
        "google_oauth": "GoogleTokenLifecycle",
    },
    AdvertisingCatalogService: {
        "access_tokens": "AccessTokenProvider",
        "connectors": "AdsConnectorProvider",
    },
    AdsIngestionSourcePlanner: {
        "access_tokens": "AccessTokenProvider",
        "connectors": "AdsConnectorProvider",
    },
    MultiPlatformIngestionService: {"observations": "ObservationRecorder"},
    ObservationService: {
        "campaigns": "CampaignExistenceVerifier",
        "observations": "ObservationRepository",
    },
    StructuredRetrievalService: {"repository": "StructuredRetrievalRepository"},
    TextRetrievalService: {
        "repository": "CampaignDocumentRepository",
        "search": "CampaignDocumentSearch",
    },
}


def test_components_request_roles_instead_of_concrete_collaborators() -> None:
    for component, expected_roles in COMPONENT_ROLES.items():
        signature = inspect.signature(component.__init__)
        annotations = get_type_hints(component.__init__)
        for parameter, role_name in expected_roles.items():
            assert parameter in signature.parameters
            assert annotations[parameter].__name__ == role_name, (
                f"{component.__name__}.{parameter} must depend on {role_name}"
            )
