from datetime import date
from uuid import uuid4

import pytest

from launchpilot.domain.errors import DomainError
from launchpilot.domain.models import (
    CampaignObservation,
    Completeness,
    CompletenessStatus,
    DateRange,
    MetricObservation,
    PlatformSlice,
)


def test_observation_rejects_metrics_with_a_different_period() -> None:
    observation_period = DateRange(date(2026, 7, 1), date(2026, 7, 31))
    metric_period = DateRange(date(2026, 7, 1), date(2026, 7, 30))
    metric = MetricObservation(
        subject_ref="channel:mine",
        subject_level="CHANNEL",
        metric_key="views",
        value=120.0,
        unit="count",
        period=metric_period,
        provenance_ref="youtube-analytics:run-1",
    )
    slice_ = PlatformSlice(
        surface="YOUTUBE",
        connector="youtube-analytics",
        account_ref="channel:mine",
        fetch_run_ref="run-1",
        metrics=(metric,),
    )

    with pytest.raises(DomainError, match="metric period"):
        CampaignObservation(
            id=uuid4(),
            campaign_id=uuid4(),
            period=observation_period,
            platform_slices=(slice_,),
            completeness=Completeness(status=CompletenessStatus.COMPLETE),
        )
