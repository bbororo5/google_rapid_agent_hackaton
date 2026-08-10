from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Protocol
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


@dataclass(frozen=True, slots=True)
class PlatformAccess:
    provider: str
    access_token: str


class PlatformAccessError(RuntimeError):
    pass


class PlatformAccessUnavailable(PlatformAccessError):
    pass


class PlatformConnectionNotFound(PlatformAccessError):
    pass


class PlatformProviderMismatch(PlatformAccessError):
    pass


class PlatformAuthorizationExpired(PlatformAccessError):
    pass


class PlatformTokenRefreshFailed(PlatformAccessError):
    pass


class PlatformTokenUnavailable(PlatformAccessError):
    pass


class UnsupportedAdsProvider(PlatformAccessError):
    pass


class AdsConnectorUnavailable(PlatformAccessError):
    pass


class AccessTokenProvider(Protocol):
    def resolve(
        self,
        *,
        connection_id: str,
        user_id: str,
        allowed_providers: frozenset[str],
    ) -> PlatformAccess: ...


class AdsConnectorProvider(Protocol):
    def create(self, provider: str) -> AdsConnector: ...


@dataclass(frozen=True, slots=True)
class IngestionPlan:
    sources: tuple[IngestionSource, ...]
    failures: tuple[str, ...]


class AdsIngestionSourcePlanner:
    """Asks collaborators for tokens and connectors, isolating preflight failures."""

    _advertising_providers = frozenset({"GOOGLE_ADS", "META_ADS"})

    def __init__(
        self,
        access_tokens: AccessTokenProvider,
        connectors: AdsConnectorProvider,
    ) -> None:
        self._access_tokens = access_tokens
        self._connectors = connectors

    def plan(
        self, *, user_id: str, bindings: tuple[ExternalCampaignBinding, ...]
    ) -> IngestionPlan:
        sources: list[IngestionSource] = []
        failures: list[str] = []
        for binding in bindings:
            try:
                access = self._access_tokens.resolve(
                    connection_id=binding.connection_id,
                    user_id=user_id,
                    allowed_providers=self._advertising_providers,
                )
                sources.append(
                    IngestionSource(
                        binding=binding,
                        connector=self._connectors.create(access.provider),
                        access_token=access.access_token,
                    )
                )
            except PlatformAccessError as error:
                failures.append(f"{binding.provider.value}: {error}")
        return IngestionPlan(sources=tuple(sources), failures=tuple(failures))


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
