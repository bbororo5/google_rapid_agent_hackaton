from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, field_validator

from launchpilot.application.analysis import (
    AnalyzeCampaign,
    CampaignAnalysisResult,
    CampaignAnalysisService,
)
from launchpilot.domain.errors import NotFoundError

from .campaign_context import UserDependency
from .dependencies import campaign_analysis_service

router = APIRouter(prefix="/campaigns", tags=["campaign-analysis"])
AnalysisDependency = Annotated[
    CampaignAnalysisService, Depends(campaign_analysis_service)
]


class CampaignAnalysisInput(BaseModel):
    question: str

    @field_validator("question")
    @classmethod
    def strip_question(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("question must not be blank")
        return value


@router.post("/{campaign_id}/analysis", response_model=CampaignAnalysisResult)
def analyze_campaign(
    campaign_id: UUID,
    payload: CampaignAnalysisInput,
    user: UserDependency,
    analysis: AnalysisDependency,
) -> CampaignAnalysisResult:
    try:
        return analysis.handle(
            AnalyzeCampaign(
                user_id=UUID(user.id),
                campaign_id=campaign_id,
                question=payload.question,
            )
        )
    except NotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(error)
        ) from error
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Campaign analysis failed.",
        ) from error
