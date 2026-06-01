import { expect, test } from "@playwright/test";
import { readFile } from "node:fs/promises";
import path from "node:path";

type JsonObject = Record<string, unknown>;

const root = path.resolve(import.meta.dirname, "..");

async function fixture<T extends JsonObject>(relativePath: string): Promise<T> {
  const text = await readFile(path.join(root, relativePath), "utf8");
  return JSON.parse(text) as T;
}

test.describe("main analysis approval happy path", () => {
  test("uploads CSV, reviews generated experiments, and approves them", async ({ page }) => {
    const importCsv = await fixture("contracts/01-frontend-java/examples/import-csv-response.json");
    const agentRunAccepted = await fixture("contracts/01-frontend-java/examples/agent-run-accepted-response.json");
    const agentRunning = await fixture("contracts/01-frontend-java/examples/agent-run-running-response.json");
    const agentReady = await fixture("contracts/01-frontend-java/examples/agent-run-waiting-for-approval-response.json");
    const approvalResponse = await fixture("contracts/01-frontend-java/examples/approve-experiment-plan-response.json");

    let pollCount = 0;

    await page.route("**/api/import/csv", async (route) => {
      await route.fulfill({
        status: 201,
        contentType: "application/json",
        body: JSON.stringify(importCsv),
      });
    });

    await page.route("**/api/agent/run", async (route) => {
      await route.fulfill({
        status: 202,
        contentType: "application/json",
        body: JSON.stringify(agentRunAccepted),
      });
    });

    await page.route("**/api/agent/runs/run_20260601_001", async (route) => {
      pollCount += 1;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(pollCount === 1 ? agentRunning : agentReady),
      });
    });

    await page.route("**/api/agent/actions/run_20260601_001/approve", async (route) => {
      const requestBody = route.request().postDataJSON() as JsonObject;
      expect(requestBody.experiment_plan_id).toBe("plan_001");
      expect(Array.isArray(requestBody.final_experiments)).toBe(true);

      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(approvalResponse),
      });
    });

    await page.goto("/");

    await page.getByLabel(/csv/i).setInputFiles({
      name: "channel_metrics.csv",
      mimeType: "text/csv",
      buffer: Buffer.from("post_id,published_at,channel,views,save_rate\npost_014,2026-05-27,tiktok,120000,0.074\n"),
    });

    await page.getByRole("button", { name: /analy[sz]e|run analysis/i }).click();

    await expect(page.getByText(/analyzing|running evidence|searching evidence/i)).toBeVisible();
    await expect(page.getByText("BTS shorts outperformed recent baseline")).toBeVisible();
    await expect(page.getByText(/raw behind-the-scenes clips may be converting/i)).toBeVisible();
    await expect(page.getByText("BTS face-first hook test")).toBeVisible();

    const titleInput = page.getByRole("textbox", { name: /experiment title|title/i });
    await titleInput.fill("BTS face-first hook test edited");

    await page.getByRole("button", { name: /approve experiments|approve/i }).click();

    await expect(page.getByText("BTS face-first hook test edited")).toBeVisible();
    await expect(page.getByText(/human approval processed|approved|calendar/i)).toBeVisible();
  });
});
