import type { ImportCsvResponse } from "@contracts/frontend-types";
import importFixture from "../../../../../../contracts/01-frontend-java/examples/import-csv-response.json";
import type { ExperimentPlannerApi } from "./experimentPlannerApi";

export function createMockExperimentPlannerApi(): ExperimentPlannerApi {
  return {
    async importCsv() {
      return importFixture as ImportCsvResponse;
    },
  };
}
