"""Turn goal selection and dynamic loop budgets."""

from __future__ import annotations

import uuid
from enum import Enum

from pydantic import BaseModel, Field

from app.orchestration.models import TurnContext, TurnDecision
from app.runtime.state import DelegationMode, DeltaIntent, PhaseType


class BudgetProfile(str, Enum):
    INTERACTIVE_QUICK = "interactive_quick"
    STANDARD_ANALYSIS = "standard_analysis"
    DEEP_ANALYSIS = "deep_analysis"
    BACKGROUND_RESEARCH = "background_research"


class RunMode(str, Enum):
    FOREGROUND = "foreground"
    BACKGROUND = "background"


class GoalKind(str, Enum):
    ANSWER_QUESTION = "answer_question"
    RUN_PHASE = "run_phase"
    REVISE_ARTIFACT = "revise_artifact"
    APPROVAL_ACTION = "approval_action"
    CLARIFY = "clarify"


class GoalBudget(BaseModel):
    max_steps: int
    max_llm_calls: int
    max_phase_runs: int
    max_repairs: int
    max_seconds: int


class TurnGoal(BaseModel):
    goal_id: str = Field(default_factory=lambda: f"goal_{uuid.uuid4().hex[:10]}")
    kind: GoalKind
    user_request: str
    target_phase: PhaseType
    selected_artifact_ids: list[str] = Field(default_factory=list)
    requested_depth: str = "normal"
    run_mode: RunMode = RunMode.FOREGROUND
    budget_profile: BudgetProfile
    budgets: GoalBudget
    completion_criteria: list[str] = Field(default_factory=list)


class GoalController:
    """Convert an interpreted turn into an explicit, budgeted objective."""

    def create(self, turn: TurnContext, decision: TurnDecision) -> TurnGoal:
        profile = self._profile_for(turn, decision)
        return TurnGoal(
            kind=self._kind_for(decision),
            user_request=turn.content,
            target_phase=decision.delegation.target_phase,
            selected_artifact_ids=decision.delta.referenced_artifact_ids,
            requested_depth=self._requested_depth(turn.content),
            run_mode=RunMode.BACKGROUND
            if profile == BudgetProfile.BACKGROUND_RESEARCH
            else RunMode.FOREGROUND,
            budget_profile=profile,
            budgets=self._budget_for(profile),
            completion_criteria=self._criteria_for(decision),
        )

    def _kind_for(self, decision: TurnDecision) -> GoalKind:
        if decision.delegation.mode == DelegationMode.CLARIFY:
            return GoalKind.CLARIFY
        if decision.delegation.mode == DelegationMode.DELEGATE:
            return GoalKind.REVISE_ARTIFACT
        if decision.delegation.mode == DelegationMode.RERUN:
            return GoalKind.RUN_PHASE
        if decision.delta.intent in {DeltaIntent.APPROVE, DeltaIntent.REJECT, DeltaIntent.CANCEL}:
            return GoalKind.APPROVAL_ACTION
        return GoalKind.ANSWER_QUESTION

    def _profile_for(self, turn: TurnContext, decision: TurnDecision) -> BudgetProfile:
        depth = self._requested_depth(turn.content)
        if "background" in turn.content.lower():
            return BudgetProfile.BACKGROUND_RESEARCH
        if depth == "deep":
            return BudgetProfile.DEEP_ANALYSIS
        if decision.delegation.mode == DelegationMode.RERUN:
            return BudgetProfile.STANDARD_ANALYSIS
        return BudgetProfile.INTERACTIVE_QUICK

    def _requested_depth(self, content: str) -> str:
        lowered = content.lower()
        deep_markers = (
            "deep",
            "thorough",
            "detailed",
            "as much",
            "comprehensive",
            "자세",
            "풍부",
            "최대한",
            "깊",
            "많이",
            "수십",
        )
        if any(marker in lowered for marker in deep_markers):
            return "deep"
        return "normal"

    def _budget_for(self, profile: BudgetProfile) -> GoalBudget:
        budgets = {
            BudgetProfile.INTERACTIVE_QUICK: GoalBudget(
                max_steps=6,
                max_llm_calls=3,
                max_phase_runs=1,
                max_repairs=1,
                max_seconds=60,
            ),
            BudgetProfile.STANDARD_ANALYSIS: GoalBudget(
                max_steps=15,
                max_llm_calls=8,
                max_phase_runs=2,
                max_repairs=2,
                max_seconds=180,
            ),
            BudgetProfile.DEEP_ANALYSIS: GoalBudget(
                max_steps=40,
                max_llm_calls=20,
                max_phase_runs=4,
                max_repairs=4,
                max_seconds=600,
            ),
            BudgetProfile.BACKGROUND_RESEARCH: GoalBudget(
                max_steps=80,
                max_llm_calls=40,
                max_phase_runs=8,
                max_repairs=8,
                max_seconds=1800,
            ),
        }
        return budgets[profile]

    def _criteria_for(self, decision: TurnDecision) -> list[str]:
        if decision.delegation.mode == DelegationMode.RERUN:
            return [
                f"Run the {decision.delegation.target_phase.value} phase.",
                "Persist generated artifacts in runtime state.",
                "Explain the result and next useful action from the full thread context.",
            ]
        if decision.delegation.mode == DelegationMode.DIRECT:
            return [
                "Answer from the full conversation transcript and all saved artifacts.",
                "Avoid one-shot acknowledgements when the user asked for explanation or analysis.",
            ]
        if decision.delegation.mode == DelegationMode.CLARIFY:
            return ["Ask the smallest clarifying question needed to proceed."]
        return ["Acknowledge the requested workflow action and preserve state consistency."]
