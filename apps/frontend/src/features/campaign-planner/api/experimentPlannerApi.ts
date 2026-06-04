import type { ImportCsvResponse } from "@contracts/frontend-types";

export interface ExperimentPlannerApi {
  importCsv(input: { file: File; workspaceId: string; campaignId: string }): Promise<ImportCsvResponse>;
}

async function parseJsonResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    throw new Error(`Request failed with ${response.status}`);
  }

  return (await response.json()) as T;
}

const agentApiBaseUrl = process.env.NEXT_PUBLIC_AGENT_API_BASE_URL ?? "http://localhost:8090";

function apiUrl(path: string) {
  return `${agentApiBaseUrl}${path}`;
}

export function createFetchExperimentPlannerApi(): ExperimentPlannerApi {
  return {
    async importCsv({ file, workspaceId, campaignId }) {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("workspace_id", workspaceId);
      formData.append("campaign_id", campaignId);
      formData.append("source_platform", "tiktok");

      const response = await fetch(apiUrl("/api/import/csv"), {
        method: "POST",
        body: formData,
      });

      return parseJsonResponse<ImportCsvResponse>(response);
    },

  };
}
