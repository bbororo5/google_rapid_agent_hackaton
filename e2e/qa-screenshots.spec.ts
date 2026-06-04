import { expect, test } from "@playwright/test";
import { mkdirSync } from "node:fs";
import path from "node:path";

const root = path.resolve(import.meta.dirname, "..");
const sampleMetricsCsv = path.join(root, "apps/frontend/fixtures/sample-channel-metrics.csv");
const screenshotDir = path.join(root, "test-results/qa-screenshots");

test.describe("visual qa screenshot flow", () => {
  test("runs through the application taking screenshots", async ({ page }) => {
    test.setTimeout(90000);
    mkdirSync(screenshotDir, { recursive: true });

    // 1. Initial State
    await page.goto("/campaigns/comeback-teaser/planner");
    await page.waitForTimeout(500);
    await page.screenshot({ path: path.join(screenshotDir, "01-initial-state.png"), fullPage: true });

    // 2. CSV Selected State
    await page.locator("#csv-input").setInputFiles(sampleMetricsCsv);
    await page.waitForTimeout(500);
    await page.screenshot({ path: path.join(screenshotDir, "02-csv-selected.png"), fullPage: true });

    // 3. Trigger analysis and observe the streamed checklist state.
    await page.getByRole("button", { name: /send|analy[sz]e|run analysis/i }).click();
    await expect(page.getByRole("region", { name: /agent session status/i }).getByText(/analyze signal/i).first()).toBeVisible();
    await page.screenshot({ path: path.join(screenshotDir, "03-loading-checklist.png"), fullPage: true });

    // 4. Wait for evidence and the markdown output panel.
    await expect(page.getByText("BTS shorts outperformed recent baseline").first()).toBeVisible({ timeout: 15000 });
    await expect(page.getByRole("button", { name: /markdown document evidence notes/i })).toBeVisible();
    await page.screenshot({ path: path.join(screenshotDir, "04-results-ready.png"), fullPage: true });

    // 5. Confirm the signal and capture the saved signal output card.
    await page.getByRole("button", { name: /use this signal/i }).click();
    await expect(page.getByRole("button", { name: /confirmed signal bts shorts outperformed recent baseline/i })).toBeVisible();
    await page.screenshot({ path: path.join(screenshotDir, "05-signal-output-saved.png"), fullPage: true });

    // 6. Edit the experiment title and approve experiments.
    await expect(page.getByRole("button", { name: /approve experiments|approve/i })).toBeVisible({ timeout: 15000 });
    const titleInput = page.getByRole("textbox", { name: /experiment title|title/i });
    await titleInput.fill("BTS face-first hook test edited");
    await page.getByRole("button", { name: /approve experiments|approve/i }).click();

    // 7. Capture the approval receipt and saved approval output card.
    await expect(page.getByText("BTS face-first hook test edited").first()).toBeVisible({ timeout: 10000 });
    await expect(page.getByRole("button", { name: /approved output approval complete/i })).toBeVisible();
    await page.screenshot({ path: path.join(screenshotDir, "06-approved-receipt.png"), fullPage: true });
  });
});
