from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from enum import StrEnum
from math import isfinite
from uuid import UUID, uuid4

from .errors import DomainError


def utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class DateRange:
    start: date
    end: date

    def __post_init__(self) -> None:
        if self.start > self.end:
            raise DomainError("period start must be on or before end")


@dataclass(frozen=True, slots=True)
class CampaignResourceBinding:
    connection_id: UUID
    resource_ref: str
    label: str | None = None

    def __post_init__(self) -> None:
        if not self.resource_ref.strip():
            raise DomainError("resource_ref must not be blank")


@dataclass(frozen=True, slots=True)
class Campaign:
    id: UUID
    workspace_id: UUID
    name: str
    goal: str
    period: DateRange
    target_metrics: tuple[str, ...] = ()
    resource_bindings: tuple[CampaignResourceBinding, ...] = ()
    created_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        if not self.name.strip() or not self.goal.strip():
            raise DomainError("campaign name and goal must not be blank")
        if any(not metric.strip() for metric in self.target_metrics):
            raise DomainError("target metric must not be blank")

    @classmethod
    def create(
        cls,
        *,
        workspace_id: UUID,
        name: str,
        goal: str,
        period: DateRange,
        target_metrics: tuple[str, ...] = (),
        resource_bindings: tuple[CampaignResourceBinding, ...] = (),
    ) -> Campaign:
        return cls(
            id=uuid4(),
            workspace_id=workspace_id,
            name=name,
            goal=goal,
            period=period,
            target_metrics=target_metrics,
            resource_bindings=resource_bindings,
        )


class TurnRole(StrEnum):
    USER = "USER"
    ASSISTANT = "ASSISTANT"
    SYSTEM = "SYSTEM"


@dataclass(frozen=True, slots=True)
class Turn:
    id: UUID
    conversation_id: UUID
    role: TurnRole
    content: str
    created_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        if not self.content.strip():
            raise DomainError("turn content must not be blank")


@dataclass(frozen=True, slots=True)
class Conversation:
    id: UUID
    campaign_id: UUID
    title: str
    created_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        if not self.title.strip():
            raise DomainError("conversation title must not be blank")

    @classmethod
    def create(cls, *, campaign_id: UUID, title: str) -> Conversation:
        return cls(id=uuid4(), campaign_id=campaign_id, title=title)


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
        if not all(
            value.strip()
            for value in (
                self.subject_ref,
                self.subject_level,
                self.metric_key,
                self.unit,
                self.provenance_ref,
            )
        ):
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
        if not all(
            value.strip()
            for value in (
                self.surface,
                self.connector,
                self.account_ref,
                self.fetch_run_ref,
            )
        ):
            raise DomainError("platform slice source fields must not be blank")
        optional_context = (
            self.external_campaign_ref,
            self.currency_code,
            self.timezone,
            self.attribution_setting,
        )
        if any(value is not None and not value.strip() for value in optional_context):
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
