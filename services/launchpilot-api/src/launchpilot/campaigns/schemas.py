from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from launchpilot.campaigns.models import Campaign, Conversation
from launchpilot.shared import DateRange


class PeriodInput(BaseModel):
    start: date
    end: date

    @model_validator(mode="after")
    def validate_range(self) -> "PeriodInput":
        if self.start > self.end:
            raise ValueError("start must be on or before end")
        return self


class CampaignCreateInput(BaseModel):
    workspace_id: UUID
    name: str = Field(min_length=1, max_length=120)
    goal: str = Field(min_length=1, max_length=500)
    period: PeriodInput
    target_metrics: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("name", "goal")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value

    @field_validator("target_metrics")
    @classmethod
    def strip_metrics(cls, values: list[str]) -> list[str]:
        normalized = [value.strip() for value in values]
        if any(not value for value in normalized):
            raise ValueError("target metric must not be blank")
        return normalized

    def to_domain(self) -> Campaign:
        return Campaign.create(
            workspace_id=self.workspace_id,
            name=self.name,
            goal=self.goal,
            period=DateRange(start=self.period.start, end=self.period.end),
            target_metrics=tuple(self.target_metrics),
        )


class CampaignOutput(BaseModel):
    id: UUID
    workspace_id: UUID
    name: str
    goal: str
    period: PeriodInput
    target_metrics: list[str]
    created_at: datetime

    @classmethod
    def from_domain(cls, campaign: Campaign) -> "CampaignOutput":
        return cls(
            id=campaign.id,
            workspace_id=campaign.workspace_id,
            name=campaign.name,
            goal=campaign.goal,
            period=PeriodInput(start=campaign.period.start, end=campaign.period.end),
            target_metrics=list(campaign.target_metrics),
            created_at=campaign.created_at,
        )


class ConversationCreateInput(BaseModel):
    title: str = Field(min_length=1, max_length=200)

    @field_validator("title")
    @classmethod
    def strip_title(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


class ConversationOutput(BaseModel):
    id: UUID
    campaign_id: UUID
    title: str
    created_at: datetime

    @classmethod
    def from_domain(cls, conversation: Conversation) -> "ConversationOutput":
        return cls(
            id=conversation.id,
            campaign_id=conversation.campaign_id,
            title=conversation.title,
            created_at=conversation.created_at,
        )
