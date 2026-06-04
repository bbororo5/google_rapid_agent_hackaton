import { expect, test } from "@playwright/test";
import path from "node:path";

const root = path.resolve(import.meta.dirname, "..");
const sampleMetricsCsv = path.join(root, "apps/frontend/fixtures/sample-channel-metrics.csv");

test.describe("main analysis approval happy path", () => {
  test("keeps the composer available as a text chat surface before evidence is attached", async ({ page }) => {
    await page.goto("/campaigns/comeback-teaser/planner");

    await page.getByRole("textbox", { name: /agent instructions/i }).fill("I want to focus on retention instead of reach.");
    await page.getByRole("button", { name: /^send$/i }).click();

    await expect(page.getByText(/i want to focus on retention/i)).toBeVisible();
    await expect(page.getByRole("button", { name: /^send$/i })).toBeDisabled();
  });

  test("keeps streamed timeline visible after stopping a run", async ({ page }) => {
    await page.goto("/campaigns/comeback-teaser/planner");

    await page.locator("#csv-input").setInputFiles(sampleMetricsCsv);
    await page.getByRole("button", { name: /send|analy[sz]e|run analysis/i }).click();

    await expect(page.getByText(/checked metric baseline/i).first()).toBeVisible();
    await page.getByRole("button", { name: /stop/i }).click();

    await expect(page.getByText(/what should we test next week/i).first()).toBeVisible();
    await expect(page.getByText(/checked metric baseline/i).first()).toBeVisible();
    await expect(page.getByText(/agent session cancelled|user cancelled/i).first()).toBeVisible();
    await expect(page.getByText(/find the signal in this campaign/i)).toHaveCount(0);
  });

  test("uploads CSV, reviews generated experiments, and approves them", async ({ page }) => {
    await page.goto("/campaigns/comeback-teaser/planner");

    await page.locator("#csv-input").setInputFiles(sampleMetricsCsv);

    await page.getByRole("button", { name: /send|analy[sz]e|run analysis/i }).click();

    await expect(page.getByRole("region", { name: /agent session status/i }).getByText(/analyze signal/i).first()).toBeVisible();
    await expect(page.getByText(/save-rate lift looks repeatable/i).first()).toBeVisible();
    await expect(page.getByText(/checked metric baseline/i).first()).toBeVisible();
    await expect(page.getByText(/checked supporting posts/i).first()).toBeVisible();
    await expect(page.getByText(/prepared evidence notes/i).first()).toBeVisible();
    await expect(page.getByText(/two BTS shorts that outperformed/i).first()).toBeVisible();

    await page.getByRole("button", { name: /open evidence notes/i }).click();
    await expect(page.getByRole("region", { name: /stream documents/i })).toBeVisible();
    await expect(page.getByRole("button", { name: /evidence notes evidence scan/i })).toBeVisible();
    await expect(page.getByRole("button", { name: /use this signal/i })).toBeVisible();

    await page.getByRole("textbox", { name: /agent instructions/i }).fill("Please keep the signal grounded in short-form content.");
    await page.getByRole("button", { name: /^send$/i }).click();
    await expect(page.getByText(/please keep the signal grounded/i)).toBeVisible();
    await expect(page.getByRole("button", { name: /use this signal/i })).toBeVisible();

    await page.getByRole("button", { name: /use this signal/i }).click();

    await expect(page.getByText(/checked team context/i).first()).toBeVisible();
    await expect(page.getByText(/raw behind-the-scenes clips may be converting/i)).toBeVisible();
    await expect(page.getByText("BTS face-first hook test").first()).toBeVisible();

    const titleInput = page.getByRole("textbox", { name: /experiment title|title/i });
    await titleInput.fill("BTS face-first hook test edited");

    await page.getByRole("button", { name: /approve experiments|approve/i }).click();

    await expect(page.getByText("BTS face-first hook test edited").first()).toBeVisible();
    await expect(page.getByText(/human approval processed|approved|calendar/i).first()).toBeVisible();

  });
});
