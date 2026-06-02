import type {
  AgentRunAcceptedResponse,
  AgentRunStatusResponse,
  ApproveExperimentPlanRequest,
  ApproveExperimentPlanResponse,
  CancelAgentRunResponse,
  ImportCsvResponse,
} from "@contracts/frontend-types";
import acceptedFixture from "../../../../../../contracts/01-frontend-java/examples/agent-run-accepted-response.json";
import readyFixture from "../../../../../../contracts/01-frontend-java/examples/agent-run-waiting-for-approval-response.json";
import runningFixture from "../../../../../../contracts/01-frontend-java/examples/agent-run-running-response.json";
import approvalFixture from "../../../../../../contracts/01-frontend-java/examples/approve-experiment-plan-response.json";
import importFixture from "../../../../../../contracts/01-frontend-java/examples/import-csv-response.json";
import type { ExperimentPlannerApi } from "./experimentPlannerApi";

export function createMockExperimentPlannerApi(): ExperimentPlannerApi {
  let pollCount = 0;

  return {
    async importCsv() {
      return importFixture as ImportCsvResponse;
    },

    async runAgent() {
      pollCount = 0;
      return acceptedFixture as AgentRunAcceptedResponse;
    },

    async getAgentRun() {
      pollCount += 1;
      return (pollCount === 1 ? runningFixture : readyFixture) as AgentRunStatusResponse;
    },

    async approveExperimentPlan(_agentRunId: string, request: ApproveExperimentPlanRequest) {
      const firstExperiment = request.final_experiments[0];
      return {
        ...(approvalFixture as ApproveExperimentPlanResponse),
        created_calendar_events: (approvalFixture as ApproveExperimentPlanResponse).created_calendar_events.map((event) => ({
          ...event,
          title: firstExperiment?.title ?? event.title,
        })),
      };
    },

    async cancelAgentRun(agentRunId: string) {
      return {
        ok: true,
        agent_run_id: agentRunId,
        status: "CANCELLED",
        cancelled_at: new Date().toISOString(),
      } satisfies CancelAgentRunResponse;
    },
  };
}
