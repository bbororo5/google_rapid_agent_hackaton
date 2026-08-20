from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID


@dataclass(frozen=True)
class ExecutionScope:
    """Immutable server/routing context injected into the agent workflow."""

    workspace_id: UUID | str
    reference_now: datetime
    campaign_id: UUID | str | None = None
    campaign_code: str | None = None
    user_id: str | None = None

    @classmethod
    def create(
        cls,
        *,
        workspace_id: UUID | str,
        campaign_id: UUID | str | None = None,
        campaign_code: str | None = None,
        user_id: str | None = None,
        reference_now: datetime | None = None,
    ) -> ExecutionScope:
        return cls(
            workspace_id=workspace_id,
            campaign_id=campaign_id,
            campaign_code=campaign_code,
            user_id=user_id,
            reference_now=reference_now or datetime.now(timezone.utc),
        )
