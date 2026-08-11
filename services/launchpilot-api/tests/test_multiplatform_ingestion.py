from datetime import date
from uuid import uuid4

import pytest

from launchpilot.campaigns.contracts.bindings import ExternalCampaignBinding
from launchpilot.campaigns.models import Campaign
from launchpilot.campaigns.service import CampaignService
from launchpilot.devtools.in_memory import (
    InMemoryObservationRepository,
    InMemoryRepositories,
)
from launchpilot.performance.contracts.platform import (
    CampaignMetricRequest,
    ConnectorFetchResult,
)
from launchpilot.performance.ingestion import (
    AllSourcesFailedError,
    IngestionSource,
    MultiPlatformIngestionService,
)
from launchpilot.performance.models import MetricObservation, PlatformSlice
from launchpilot.performance.observation_service import ObservationService
from launchpilot.shared import DateRange, PlatformProvider


class SuccessfulConnector:
    def __init__(self, provider: PlatformProvider) -> None:
        self._provider = provider

    @property
    def provider(self) -> PlatformProvider:
        return self._provider

    def list_accounts(self, *, access_token: str):
        return ()

    def list_campaigns(self, *, access_token: str, account_ref: str):
        return ()

    def fetch_campaign_metrics(
        self, *, access_token: str, request: CampaignMetricRequest
    ) -> ConnectorFetchResult:
        return ConnectorFetchResult(
            platform_slice=PlatformSlice(
                surface=self.provider,
                connector=f"{self.provider.lower()}-fixture",
                account_ref=request.account_ref,
                external_campaign_ref=request.campaign_ref,
                fetch_run_ref=request.fetch_run_ref,
                metrics=(
                    MetricObservation(
                        subject_ref=request.campaign_ref,
                        subject_level="CAMPAIGN",
                        metric_key="spend",
                        value=10,
                        unit="currency:KRW",
                        period=request.period,
                        provenance_ref=request.fetch_run_ref,
                    ),
                ),
            )
        )


class FailingConnector(SuccessfulConnector):
    def fetch_campaign_metrics(
        self, *, access_token: str, request: CampaignMetricRequest
    ) -> ConnectorFetchResult:
        raise RuntimeError("fixture failure")


def services() -> tuple[Campaign, MultiPlatformIngestionService]:
    store = InMemoryRepositories()
    campaign = Campaign.create(
        workspace_id=uuid4(),
        name="Launch",
        goal="Compare ads",
        period=DateRange(date(2026, 7, 1), date(2026, 7, 31)),
    )
    campaigns = CampaignService(store)
    campaigns.create(campaign)
    observations = ObservationService(
        campaigns, InMemoryObservationRepository(store)
    )
    return campaign, MultiPlatformIngestionService(observations)


def source(
    campaign: Campaign, provider: PlatformProvider, connector: SuccessfulConnector
) -> IngestionSource:
    return IngestionSource(
        binding=ExternalCampaignBinding.create(
            campaign_id=campaign.id,
            connection_id=f"{provider}-connection",
            provider=provider,
            external_account_ref=f"{provider}-account",
            external_campaign_ref=f"{provider}-campaign",
            display_name=f"{provider} campaign",
            currency_code="KRW",
            timezone="Asia/Seoul",
        ),
        connector=connector,
        access_token="token",
    )


def test_multiplatform_collection_keeps_success_when_one_provider_fails() -> None:
    campaign, service = services()

    outcome = service.collect(
        campaign_id=campaign.id,
        period=campaign.period,
        sources=(
            source(
                campaign,
                PlatformProvider.GOOGLE_ADS,
                SuccessfulConnector(PlatformProvider.GOOGLE_ADS),
            ),
            source(
                campaign,
                PlatformProvider.META_ADS,
                FailingConnector(PlatformProvider.META_ADS),
            ),
        ),
    )

    assert outcome.observation.completeness.status == "PARTIAL"
    assert len(outcome.observation.platform_slices) == 1
    assert outcome.observation.platform_slices[0].currency_code == "KRW"
    assert outcome.observation.platform_slices[0].timezone == "Asia/Seoul"
    assert outcome.observation.completeness.missing_reasons == (
        "META_ADS fetch failed: RuntimeError",
    )


def test_multiplatform_collection_rejects_an_all_provider_failure() -> None:
    campaign, service = services()

    with pytest.raises(AllSourcesFailedError) as captured:
        service.collect(
            campaign_id=campaign.id,
            period=campaign.period,
            sources=(
                source(
                    campaign,
                    PlatformProvider.GOOGLE_ADS,
                    FailingConnector(PlatformProvider.GOOGLE_ADS),
                ),
            ),
            preflight_failures=("META_ADS: authorization expired",),
        )

    assert len(captured.value.reasons) == 2
