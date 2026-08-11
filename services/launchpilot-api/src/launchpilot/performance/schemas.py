from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field

from .models import CampaignObservation


class PeriodOutput(BaseModel):
    start: date
    end: date


class ObservationSummaryOutput(BaseModel):
    id: UUID
    campaign_id: UUID
    captured_at: datetime
    period: PeriodOutput
    completeness: str
    platform_slice_count: int
    missing_reasons: list[str] = Field(default_factory=list)

    @classmethod
    def from_domain(
        cls, observation: CampaignObservation
    ) -> "ObservationSummaryOutput":
        return cls(
            id=observation.id,
            campaign_id=observation.campaign_id,
            captured_at=observation.captured_at,
            period=PeriodOutput(
                start=observation.period.start, end=observation.period.end
            ),
            completeness=observation.completeness.status,
            platform_slice_count=len(observation.platform_slices),
            missing_reasons=list(observation.completeness.missing_reasons),
        )
