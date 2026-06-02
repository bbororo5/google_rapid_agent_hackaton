import type {
  AgentRunAcceptedResponse,
  AgentRunRequest,
  AgentRunStatusResponse,
  ApproveExperimentPlanRequest,
  ApproveExperimentPlanResponse,
  CancelAgentRunResponse,
  ImportCsvResponse,
} from "@contracts/frontend-types";

export interface ExperimentPlannerApi {
  importCsv(input: { file: File; workspaceId: string; campaignId: string }): Promise<ImportCsvResponse>;
  runAgent(request: AgentRunRequest): Promise<AgentRunAcceptedResponse>;
  getAgentRun(agentRunId: string): Promise<AgentRunStatusResponse>;
  approveExperimentPlan(agentRunId: string, request: ApproveExperimentPlanRequest): Promise<ApproveExperimentPlanResponse>;
  cancelAgentRun(agentRunId: string, reason?: string): Promise<CancelAgentRunResponse>;
}

async function parseJsonResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    throw new Error(`Request failed with ${response.status}`);
  }

  return (await response.json()) as T;
}

export function createFetchExperimentPlannerApi(): ExperimentPlannerApi {
  return {
    async importCsv({ file, workspaceId, campaignId }) {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("workspace_id", workspaceId);
      formData.append("campaign_id", campaignId);
      formData.append("source_platform", "tiktok");

      const response = await fetch("/api/import/csv", {
        method: "POST",
        body: formData,
      });

      return parseJsonResponse<ImportCsvResponse>(response);
    },

    async runAgent(request) {
      const response = await fetch("/api/agent/run", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(request),
      });

      return parseJsonResponse<AgentRunAcceptedResponse>(response);
    },

    async getAgentRun(agentRunId) {
      const response = await fetch(`/api/agent/runs/${agentRunId}`);
      return parseJsonResponse<AgentRunStatusResponse>(response);
    },

    async approveExperimentPlan(agentRunId, request) {
      const response = await fetch(`/api/agent/actions/${agentRunId}/approve`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(request),
      });

      return parseJsonResponse<ApproveExperimentPlanResponse>(response);
    },

    async cancelAgentRun(agentRunId, reason) {
      const response = await fetch(`/api/agent/actions/${agentRunId}/cancel`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ reason }),
      });

      return parseJsonResponse<CancelAgentRunResponse>(response);
    },
  };
}
