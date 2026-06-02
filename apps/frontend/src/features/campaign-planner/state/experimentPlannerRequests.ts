import type { AgentRunRequest, ApproveExperimentPlanRequest } from "@contracts/frontend-types";
import type { ExperimentPlannerState } from "./experimentPlannerTypes";

const defaultDateRange = {
  start: "2026-05-25",
  end: "2026-06-01",
};

export function buildAgentRunRequest(state: ExperimentPlannerState): AgentRunRequest {
  if (state.tag !== "starting_analysis") {
    throw new Error("Agent run request can only be built while starting analysis.");
  }

  if (state.source.kind === "continued_brief") {
    return {
      workspace_id: "demo_workspace",
      campaign_id: "camp_comeback_teaser",
      question: state.source.continuityPrompt,
      date_range: defaultDateRange,
      parent_brief_id: state.source.parentBriefId,
    };
  }

  return {
    workspace_id: state.source.importResult.workspace_id,
    campaign_id: state.source.importResult.campaign_id,
    question: state.source.question,
    date_range: defaultDateRange,
    parent_brief_id: null,
  };
}

export function buildApprovalRequest(state: ExperimentPlannerState): ApproveExperimentPlanRequest {
  if (state.tag !== "approving") {
    throw new Error("Approval request can only be built while approving.");
  }

  const finalExperiments = state.draftExperiments.filter((experiment) => state.selectedExperimentIds.includes(experiment.id));

  return {
    experiment_plan_id: state.payload.experiment_plan.id,
    approved_by: "demo_user",
    final_experiments: finalExperiments,
  };
}
