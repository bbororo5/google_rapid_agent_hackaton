from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from enum import StrEnum
from uuid import UUID, uuid4

from .errors import DomainError


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


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
        name: str,
        goal: str,
        period: DateRange,
        target_metrics: tuple[str, ...] = (),
        resource_bindings: tuple[CampaignResourceBinding, ...] = (),
    ) -> Campaign:
        return cls(
            id=uuid4(),
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
        if not all(
            value.strip()
            for value in (self.subject_ref, self.subject_level, self.metric_key, self.unit, self.provenance_ref)
        ):
            raise DomainError("metric observation identity and provenance must not be blank")


@dataclass(frozen=True, slots=True)
class PlatformSlice:
    surface: str
    connector: str
    account_ref: str
    fetch_run_ref: str
    metrics: tuple[MetricObservation, ...]

    def __post_init__(self) -> None:
        if not all(value.strip() for value in (self.surface, self.connector, self.account_ref, self.fetch_run_ref)):
            raise DomainError("platform slice source fields must not be blank")


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

