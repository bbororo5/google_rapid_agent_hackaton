import type { ApproveExperimentPlanRequest } from "@contracts/frontend-types";
import type { ExperimentItem } from "./experimentPlannerTypes";

export interface ApprovalRequestInput {
  experimentPlanId: string;
  draftExperiments: ExperimentItem[];
  selectedExperimentIds: string[];
}

export function buildApprovalRequest(input: ApprovalRequestInput): ApproveExperimentPlanRequest {
  const finalExperiments = input.draftExperiments.filter((experiment) => input.selectedExperimentIds.includes(experiment.id));

  return {
    experiment_plan_id: input.experimentPlanId,
    approved_by: "demo_user",
    final_experiments: finalExperiments,
  };
}
