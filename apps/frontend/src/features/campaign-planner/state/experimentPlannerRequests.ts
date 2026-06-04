import type { AgentRunRequest, ApproveExperimentPlanRequest } from "@contracts/frontend-types";
import type { ExperimentItem, ImportCsvResponse } from "./experimentPlannerTypes";

const defaultDateRange = {
  start: "2026-05-25",
  end: "2026-06-01",
};

const defaultAgentInstruction = "Analyze the uploaded campaign metrics and identify the strongest next experiment opportunity.";

export type AgentRunRequestInput =
  | { kind: "csv_import"; importResult: ImportCsvResponse; question: string }
  | { kind: "continued_brief"; parentBriefId: string; continuityPrompt: string };

export interface ApprovalRequestInput {
  experimentPlanId: string;
  draftExperiments: ExperimentItem[];
  selectedExperimentIds: string[];
}

export function buildAgentRunRequest(input: AgentRunRequestInput): AgentRunRequest {
  if (input.kind === "continued_brief") {
    return {
      workspace_id: "demo_workspace",
      campaign_id: "camp_comeback_teaser",
      question: input.continuityPrompt,
      date_range: defaultDateRange,
      parent_brief_id: input.parentBriefId,
    };
  }

  return {
    workspace_id: input.importResult.workspace_id,
    campaign_id: input.importResult.campaign_id,
    question: input.question.trim() || defaultAgentInstruction,
    date_range: defaultDateRange,
    parent_brief_id: null,
  };
}

export function buildApprovalRequest(input: ApprovalRequestInput): ApproveExperimentPlanRequest {
  const finalExperiments = input.draftExperiments.filter((experiment) => input.selectedExperimentIds.includes(experiment.id));

  return {
    experiment_plan_id: input.experimentPlanId,
    approved_by: "demo_user",
    final_experiments: finalExperiments,
  };
}
