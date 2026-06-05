import { expect, test } from "@playwright/test";
import path from "node:path";

const root = path.resolve(import.meta.dirname, "..");
const sampleMetricsCsv = path.join(root, "apps/frontend/fixtures/sample-channel-metrics.csv");

test.describe("main analysis approval happy path", () => {
  test("uploads CSV, reviews generated experiments, and approves them", async ({ page }) => {
    await page.goto("/campaigns/comeback-teaser/planner");

    await page.locator("#csv-input").setInputFiles(sampleMetricsCsv);
    await page.getByRole("button", { name: /send|analy[sz]e|run analysis/i }).click();

    await expect(page.getByRole("region", { name: /agent session status/i }).getByText(/analyze signal/i).first()).toBeVisible();
    await expect(page.getByText(/save-rate lift looks repeatable/i).first()).toBeVisible();
    await expect(page.getByText(/prepared evidence notes/i).first()).toBeVisible();
    await expect(page.getByText(/two BTS shorts that outperformed/i).first()).toBeVisible();

    await page.getByRole("button", { name: /open evidence notes/i }).click();
    await expect(page.getByRole("complementary", { name: /output panel/i })).toContainText("Evidence notes");

    await page.getByRole("button", { name: /use this signal/i }).click();
    await expect(page.getByText(/raw behind-the-scenes clips may be converting/i)).toBeVisible();
    await expect(page.getByText("BTS face-first hook test").first()).toBeVisible();

    const titleInput = page.getByRole("textbox", { name: /experiment title|title/i });
    await titleInput.fill("BTS face-first hook test edited");

    await page.getByRole("button", { name: /approve experiments|approve/i }).click();

    await expect(page.getByText("BTS face-first hook test edited").first()).toBeVisible();
    await expect(page.getByText(/human approval processed|approved|calendar/i).first()).toBeVisible();
    await expect(page.locator(".thread-gate-inline", { hasText: /Experiment Approval/ }).filter({ hasText: /Completed/ })).toBeVisible();
    await expect(page.getByRole("button", { name: /approved output approval complete/i })).toBeVisible();
    await page.getByRole("button", { name: /approved output approval complete/i }).click();
    await expect(page.getByRole("complementary", { name: /output panel/i })).toContainText("Growth brief");
  });
});
