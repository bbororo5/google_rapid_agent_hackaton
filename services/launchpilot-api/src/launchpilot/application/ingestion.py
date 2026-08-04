from __future__ import annotations

from dataclasses import dataclass, replace
from uuid import UUID, uuid4

import httpx

from launchpilot.application.ports import AdsConnector
from launchpilot.domain.integrations import (
    CampaignMetricRequest,
    ExternalCampaignBinding,
)
from launchpilot.domain.models import (
    CampaignObservation,
    Completeness,
    CompletenessStatus,
    DateRange,
)

from .services import ObservationService


@dataclass(frozen=True, slots=True)
class IngestionSource:
    binding: ExternalCampaignBinding
    connector: AdsConnector
    access_token: str


@dataclass(frozen=True, slots=True)
class IngestionOutcome:
    observation: CampaignObservation
    warnings: tuple[str, ...]


class AllSourcesFailedError(RuntimeError):
    def __init__(self, reasons: tuple[str, ...]) -> None:
        super().__init__("all advertising data sources failed")
        self.reasons = reasons


class MultiPlatformIngestionService:
    """Fault-isolation boundary that builds one immutable multi-platform snapshot."""

    def __init__(self, observations: ObservationService) -> None:
        self._observations = observations

    def collect(
        self,
        *,
        campaign_id: UUID,
        period: DateRange,
        sources: tuple[IngestionSource, ...],
        preflight_failures: tuple[str, ...] = (),
    ) -> IngestionOutcome:
        slices = []
        warnings: list[str] = []
        missing_reasons = list(preflight_failures)
        for source in sources:
            provider = source.binding.provider.value
            try:
                if source.connector.provider != source.binding.provider:
                    raise RuntimeError("connector provider does not match binding")
                result = source.connector.fetch_campaign_metrics(
                    access_token=source.access_token,
                    request=CampaignMetricRequest(
                        account_ref=source.binding.external_account_ref,
                        campaign_ref=source.binding.external_campaign_ref,
                        period=period,
                        fetch_run_ref=f"{provider.lower()}-{uuid4()}",
                    ),
                )
                slices.append(
                    replace(
                        result.platform_slice,
                        currency_code=(
                            result.platform_slice.currency_code
                            or source.binding.currency_code
                        ),
                        timezone=(
                            result.platform_slice.timezone or source.binding.timezone
                        ),
                        attribution_setting=(
                            result.platform_slice.attribution_setting
                            or source.binding.attribution_setting
                        ),
                    )
                )
                warnings.extend(f"{provider}: {item}" for item in result.warnings)
            except (httpx.HTTPError, RuntimeError, KeyError, ValueError) as error:
                # A tool boundary isolates one provider failure from other providers.
                missing_reasons.append(
                    f"{provider} fetch failed: {type(error).__name__}"
                )
        if not slices:
            raise AllSourcesFailedError(tuple(missing_reasons))
        completeness = (
            Completeness(
                status=CompletenessStatus.PARTIAL,
                missing_reasons=tuple(missing_reasons),
            )
            if missing_reasons
            else Completeness(status=CompletenessStatus.COMPLETE)
        )
        observation = self._observations.record(
            CampaignObservation(
                id=uuid4(),
                campaign_id=campaign_id,
                period=period,
                platform_slices=tuple(slices),
                completeness=completeness,
            )
        )
        return IngestionOutcome(observation=observation, warnings=tuple(warnings))
