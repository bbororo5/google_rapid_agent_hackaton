from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from math import isfinite
from uuid import UUID

from launchpilot.shared import DateRange, DomainError, utc_now


class CompletenessStatus(StrEnum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"


@dataclass(frozen=True, slots=True)
class Completeness:
    status: CompletenessStatus
    missing_reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if any(not reason.strip() for reason in self.missing_reasons):
            raise DomainError("missing reason must not be blank")
        if self.status == CompletenessStatus.COMPLETE and self.missing_reasons:
            raise DomainError("complete observation cannot have missing reasons")
        if self.status == CompletenessStatus.PARTIAL and not self.missing_reasons:
            raise DomainError("partial observation requires a missing reason")


@dataclass(frozen=True, slots=True)
class MetricObservation:
    subject_ref: str
    subject_level: str
    metric_key: str
    value: float
    unit: str
    period: DateRange
    provenance_ref: str
    calculation: str | None = None

    def __post_init__(self) -> None:
        if not isfinite(self.value):
            raise DomainError("metric observation value must be finite")
        identity = (
            self.subject_ref,
            self.subject_level,
            self.metric_key,
            self.unit,
            self.provenance_ref,
        )
        if not all(value.strip() for value in identity):
            raise DomainError(
                "metric observation identity and provenance must not be blank"
            )


@dataclass(frozen=True, slots=True)
class PlatformSlice:
    surface: str
    connector: str
    account_ref: str
    fetch_run_ref: str
    metrics: tuple[MetricObservation, ...]
    external_campaign_ref: str | None = None
    currency_code: str | None = None
    timezone: str | None = None
    attribution_setting: str | None = None

    def __post_init__(self) -> None:
        source = (self.surface, self.connector, self.account_ref, self.fetch_run_ref)
        if not all(value.strip() for value in source):
            raise DomainError("platform slice source fields must not be blank")
        context = (
            self.external_campaign_ref,
            self.currency_code,
            self.timezone,
            self.attribution_setting,
        )
        if any(value is not None and not value.strip() for value in context):
            raise DomainError("platform slice context must not be blank")


@dataclass(frozen=True, slots=True)
class CampaignObservation:
    id: UUID
    campaign_id: UUID
    period: DateRange
    platform_slices: tuple[PlatformSlice, ...]
    completeness: Completeness
    captured_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        if not self.platform_slices:
            raise DomainError("observation requires at least one platform slice")
        for slice_ in self.platform_slices:
            for metric in slice_.metrics:
                if metric.period != self.period:
                    raise DomainError("metric period must match its observation period")
